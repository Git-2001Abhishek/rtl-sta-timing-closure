#!/usr/bin/env python3
"""
sta.py - a compact static timing analyzer for synthesized gate-level netlists.

Inputs
  * Liberty (.lib) with NLDM tables (delay_model : table_lookup)
  * Yosys JSON netlist (write_json) mapped to that library
  * SDC subset: create_clock, set_clock_uncertainty, set_clock_transition,
    set_input_delay, set_output_delay, set_input_transition, set_load,
    set_false_path -from [get_ports ...], plus `set var value` / $var

Model
  * Single clock, ideal clock network (zero latency, set_clock_transition slew)
  * Rise/fall-aware arrival and slew propagation through unate arcs
  * Cell delay / output slew: bilinear NLDM lookup (input slew x load), with
    linear extrapolation outside the table
  * Net load: sum of sink pin capacitance + wire-load-model capacitance
    (library default_wire_load, fanout -> length) + set_load on output ports
  * Zero wire delay (wire-load mode adds capacitance only)
  * Setup and hold checks on flip-flop data pins (setup_rising / hold_rising
    constraint tables), output-port checks against set_output_delay
  * Asynchronous set/reset pins are not timed (recovery/removal not checked)

This is the same analysis OpenSTA performs in wire-load mode for a simple
single-clock design; see scripts/sta.tcl for the equivalent OpenSTA run.

Usage
  python scripts/sta.py --lib liberty/nangate45_typ.lib --netlist n.json \
      --top dot2_v1 --sdc constraints/dot2.sdc [--report out.rpt] [--paths 3]
"""
import argparse
import bisect
import fnmatch
import json
import re
import sys
from collections import defaultdict

RISE, FALL = 0, 1
RF = (RISE, FALL)
RF_SYM = ("^", "v")
INF = float("inf")


# =============================================================================
# Liberty parser
# =============================================================================
class Group:
    __slots__ = ("type", "args", "attrs", "cattrs", "groups")

    def __init__(self, gtype, args):
        self.type = gtype
        self.args = args
        self.attrs = {}
        self.cattrs = defaultdict(list)
        self.groups = []

    def sub(self, gtype):
        return [g for g in self.groups if g.type == gtype]


_TOKEN_RE = re.compile(r'"(?:[^"\\]|\\.)*"|[^\s{}():;,"]+|[{}():;,]')


def _tokenize(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = text.replace("\\\n", " ").replace("\\\r\n", " ")
    return _TOKEN_RE.findall(text)


def parse_liberty(path):
    with open(path) as f:
        toks = _tokenize(f.read())
    pos = 0
    n = len(toks)
    root = Group("root", [])
    stack = [root]
    while pos < n:
        t = toks[pos]
        if t == "}":
            stack.pop()
            pos += 1
            continue
        if t == ";":
            pos += 1
            continue
        name = t
        nxt = toks[pos + 1]
        if nxt == ":":
            # simple attribute: name : value ;
            val = toks[pos + 2]
            pos += 3
            # values can be split by stray tokens until ';'
            while pos < n and toks[pos] not in (";", "}") and toks[pos + 1] != ":":
                val += " " + toks[pos]
                pos += 1
            stack[-1].attrs[name] = val.strip('"')
            continue
        if nxt == "(":
            j = pos + 2
            args = []
            while toks[j] != ")":
                if toks[j] != ",":
                    args.append(toks[j].strip('"'))
                j += 1
            j += 1
            if j < n and toks[j] == "{":
                g = Group(name, args)
                stack[-1].groups.append(g)
                stack.append(g)
                pos = j + 1
            else:
                stack[-1].cattrs[name].append(args)
                pos = j
            continue
        pos += 1  # stray token
    return root.groups[0]


def _floats(s):
    return [float(x) for x in s.replace('"', " ").replace(",", " ").split()]


class Table:
    """NLDM lookup table. Axis meaning comes from its lu_table_template."""

    def __init__(self, grp, templates):
        tmpl = templates.get(grp.args[0] if grp.args else "scalar", {})
        self.vars = [tmpl.get("variable_1"), tmpl.get("variable_2")]
        idx1 = grp.cattrs.get("index_1") or tmpl.get("index_1")
        idx2 = grp.cattrs.get("index_2") or tmpl.get("index_2")
        self.i1 = _floats(" ".join(idx1[0])) if idx1 else []
        self.i2 = _floats(" ".join(idx2[0])) if idx2 else []
        rows = grp.cattrs["values"][0]
        self.v = [_floats(r) for r in rows]
        if not self.i2 and self.i1 and len(self.v) == 1:
            self.v = [[x] for x in self.v[0]]  # 1-D table stored as one row

    @staticmethod
    def _seg(axis, x):
        if len(axis) == 1:
            return 0, 0, 0.0
        k = bisect.bisect_left(axis, x) - 1
        k = max(0, min(k, len(axis) - 2))
        x0, x1 = axis[k], axis[k + 1]
        return k, k + 1, (x - x0) / (x1 - x0)

    def lookup(self, **kw):
        """kw: input_slew, load, constrained_slew, related_slew."""
        def val_for(var):
            if var in ("input_net_transition", "input_transition_time"):
                return kw.get("input_slew", 0.0)
            if var == "total_output_net_capacitance":
                return kw.get("load", 0.0)
            if var == "constrained_pin_transition":
                return kw.get("constrained_slew", 0.0)
            if var == "related_pin_transition":
                return kw.get("related_slew", 0.0)
            return 0.0

        if not self.i1:
            return self.v[0][0]
        a, b, ta = self._seg(self.i1, val_for(self.vars[0]))
        if not self.i2:
            return self.v[a][0] + ta * (self.v[b][0] - self.v[a][0])
        c, d, tb = self._seg(self.i2, val_for(self.vars[1]))
        v00, v01 = self.v[a][c], self.v[a][d]
        v10, v11 = self.v[b][c], self.v[b][d]
        return (v00 * (1 - ta) * (1 - tb) + v10 * ta * (1 - tb)
                + v01 * (1 - ta) * tb + v11 * ta * tb)


class Arc:
    __slots__ = ("related", "type", "sense", "delay", "slew", "constraint")

    def __init__(self):
        self.delay = [None, None]
        self.slew = [None, None]
        self.constraint = [None, None]


class Pin:
    __slots__ = ("name", "dir", "cap", "arcs", "is_clock")

    def __init__(self, name):
        self.name = name
        self.dir = "input"
        self.cap = 0.0
        self.arcs = []
        self.is_clock = False


class Cell:
    def __init__(self, name):
        self.name = name
        self.pins = {}
        self.area = 0.0
        self.sequential = False


class Library:
    def __init__(self, path):
        lib = parse_liberty(path)
        self.name = lib.args[0]
        self.time_unit = lib.attrs.get("time_unit", "1ns")
        templates = {}
        for g in lib.groups:
            if g.type in ("lu_table_template", "power_lut_template"):
                t = dict(g.attrs)
                for k in ("index_1", "index_2"):
                    if k in g.cattrs:
                        t[k] = g.cattrs[k]
                templates[g.args[0]] = t
        self.wire_loads = {}
        for g in lib.sub("wire_load"):
            fl = sorted((int(float(a[0])), float(a[1])) for a in g.cattrs["fanout_length"])
            self.wire_loads[g.args[0]] = {
                "cap": float(g.attrs.get("capacitance", 0)),
                "slope": float(g.attrs.get("slope", 0)),
                "fl": fl,
            }
        self.default_wire_load = lib.attrs.get("default_wire_load")
        self.cells = {}
        for cg in lib.sub("cell"):
            cell = Cell(cg.args[0])
            cell.area = float(cg.attrs.get("area", 0))
            cell.sequential = bool(cg.sub("ff") or cg.sub("latch"))
            for pg in cg.sub("pin"):
                p = Pin(pg.args[0])
                p.dir = pg.attrs.get("direction", "input")
                p.cap = max(float(pg.attrs.get(k, 0)) for k in
                            ("capacitance", "rise_capacitance", "fall_capacitance"))
                p.is_clock = pg.attrs.get("clock") == "true"
                for tg in pg.sub("timing"):
                    arc = Arc()
                    arc.related = tg.attrs.get("related_pin", "").strip('"')
                    arc.type = tg.attrs.get("timing_type", "combinational")
                    arc.sense = tg.attrs.get("timing_sense", "non_unate")
                    for sub in tg.groups:
                        if sub.type == "cell_rise":
                            arc.delay[RISE] = Table(sub, templates)
                        elif sub.type == "cell_fall":
                            arc.delay[FALL] = Table(sub, templates)
                        elif sub.type == "rise_transition":
                            arc.slew[RISE] = Table(sub, templates)
                        elif sub.type == "fall_transition":
                            arc.slew[FALL] = Table(sub, templates)
                        elif sub.type == "rise_constraint":
                            arc.constraint[RISE] = Table(sub, templates)
                        elif sub.type == "fall_constraint":
                            arc.constraint[FALL] = Table(sub, templates)
                    p.arcs.append(arc)
                cell.pins[p.name] = p
            self.cells[cell.name] = cell

    def wire_cap(self, fanout):
        wl = self.wire_loads.get(self.default_wire_load)
        if not wl or fanout == 0:
            return 0.0
        fl = wl["fl"]
        for f, length in fl:
            if f == fanout:
                return wl["cap"] * length
        if fanout > fl[-1][0]:
            length = fl[-1][1] + (fanout - fl[-1][0]) * wl["slope"]
        else:  # interpolate between table points
            lo = max(p for p in fl if p[0] < fanout)
            hi = min(p for p in fl if p[0] > fanout)
            length = lo[1] + (hi[1] - lo[1]) * (fanout - lo[0]) / (hi[0] - lo[0])
        return wl["cap"] * length


# =============================================================================
# SDC subset
# =============================================================================
class Constraints:
    def __init__(self):
        self.clock_name = None
        self.clock_port = None
        self.period = None
        self.uncertainty = 0.0
        self.clock_slew = 0.0
        self.input_delay = {}      # port -> delay
        self.output_delay = {}     # port -> delay
        self.input_slew = {}       # port -> slew
        self.load = {}             # port -> cap
        self.false_from = set()    # ports


def parse_sdc(path, in_ports, out_ports):
    c = Constraints()
    vars_ = {}
    all_ports = in_ports + out_ports

    def expand(obj):
        obj = obj.strip()
        m = re.fullmatch(r"\[\s*(\w+)\s*(.*?)\s*\]", obj)
        if not m:
            return []
        cmd, arg = m.group(1), m.group(2).strip("{} ")
        if cmd == "all_inputs":
            return list(in_ports)
        if cmd == "all_outputs":
            return list(out_ports)
        if cmd == "get_ports":
            # a pattern matches a bit name ("a[3]") or a whole bus ("a")
            res = []
            for pat in arg.split():
                res += [p for p in all_ports
                        if fnmatch.fnmatchcase(p, pat) or fnmatch.fnmatchcase(p.split("[")[0], pat)]
            return res
        if cmd == "get_clocks":
            return [arg]
        return []

    text = open(path).read()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        line = re.sub(r"\$(\w+)", lambda m: vars_.get(m.group(1), m.group(0)), line)
        # split into words but keep [...] groups intact
        words = re.findall(r"\[[^\]]*\]|\{[^}]*\}|\S+", line)
        cmd, args = words[0], words[1:]
        opts, pos = {}, []
        i = 0
        while i < len(args):
            a = args[i]
            if a.startswith("-") and not re.fullmatch(r"-[\d.]+", a):
                if a in ("-max", "-min", "-add_delay", "-setup", "-hold"):
                    opts[a] = True
                    i += 1
                else:
                    opts[a] = args[i + 1]
                    i += 2
            else:
                pos.append(a)
                i += 1
        if cmd == "set":
            vars_[pos[0]] = pos[1]
            continue
        elif cmd == "create_clock":
            c.period = float(opts["-period"])
            c.clock_name = opts.get("-name", "clk")
            c.clock_port = expand(pos[0])[0]
        elif cmd == "set_clock_uncertainty":
            c.uncertainty = float(pos[0])
        elif cmd == "set_clock_transition":
            c.clock_slew = float(pos[0])
        elif cmd == "set_input_delay":
            for p in expand(pos[1]):
                c.input_delay[p] = float(pos[0])
        elif cmd == "set_output_delay":
            for p in expand(pos[1]):
                c.output_delay[p] = float(pos[0])
        elif cmd == "set_input_transition":
            for p in expand(pos[1]):
                c.input_slew[p] = float(pos[0])
        elif cmd == "set_load":
            for p in expand(pos[1]):
                c.load[p] = float(pos[0])
        elif cmd == "set_false_path" and "-from" in opts:
            c.false_from.update(expand(opts["-from"]))
    return c


# =============================================================================
# Netlist + timing graph
# =============================================================================
class Design:
    def __init__(self, lib, netlist_path, top):
        data = json.load(open(netlist_path))
        mod = data["modules"][top]
        self.lib = lib
        self.top = top
        self.in_ports, self.out_ports = [], []
        self.port_bits = {}          # port bit name -> net id
        for pname, p in mod["ports"].items():
            bits = p["bits"]
            for i, b in enumerate(bits):
                nm = pname if len(bits) == 1 else "%s[%d]" % (pname, i)
                self.port_bits[nm] = b
                (self.in_ports if p["direction"] == "input" else self.out_ports).append(nm)
        self.port_base = {}
        for nm in self.in_ports + self.out_ports:
            self.port_base[nm] = nm.split("[")[0]
        # readable net names
        self.net_name = {}
        # prefer public, top-level, short names when a net has several aliases
        for nn, info in sorted(mod["netnames"].items(),
                               key=lambda kv: (kv[1].get("hide_name", 0), kv[0].count("."), len(kv[0]))):
            bits = info["bits"]
            for i, b in enumerate(bits):
                if isinstance(b, int) and b not in self.net_name:
                    self.net_name[b] = nn if len(bits) == 1 else "%s[%d]" % (nn, i)
        # instances
        self._labels = {}
        self.insts = {}              # inst -> (cell, {pin: net})
        self.driver = {}             # net -> (inst|None, pin|port)
        self.sinks = defaultdict(list)
        for pnm in self.in_ports:
            self.driver[self.port_bits[pnm]] = (None, pnm)
        for pnm in self.out_ports:
            self.sinks[self.port_bits[pnm]].append((None, pnm))
        for iname, ic in mod["cells"].items():
            cell = lib.cells.get(ic["type"])
            if cell is None:
                sys.exit("cell type %s not in library" % ic["type"])
            conns = {}
            for pin, bits in ic["connections"].items():
                if not bits:
                    continue
                net = bits[0]
                conns[pin] = net
                if not isinstance(net, int):
                    continue  # constant
                if cell.pins[pin].dir == "output":
                    self.driver[net] = (iname, pin)
                else:
                    self.sinks[net].append((iname, pin))
            self.insts[iname] = (cell, conns)

    def net_load(self, net, sdc):
        cap = 0.0
        sinks = self.sinks.get(net, [])
        for inst, pin in sinks:
            if inst is None:
                cap += sdc.load.get(pin, 0.0)
            else:
                cap += self.insts[inst][0].pins[pin].cap
        return cap + self.lib.wire_cap(len(sinks))

    def inst_label(self, inst):
        """Readable instance name: flops are named after the net on their
        Q output (e.g. y_reg[5]); generated gates are shortened to g<N>."""
        if inst in self._labels:
            return self._labels[inst]
        cell, conns = self.insts[inst]
        label = inst
        if cell.sequential:
            for pname in ("Q", "QN"):
                net = conns.get(pname)
                nm = self.net_name.get(net, "") if isinstance(net, int) else ""
                if nm and not nm.startswith("$"):
                    k = nm.rfind("[")
                    label = nm + "_reg" if k < 0 else nm[:k] + "_reg" + nm[k:]
                    break
        if label.startswith("$"):
            m = re.search(r"(\d+)$", label)
            label = "g" + m.group(1) if m else label
        self._labels[inst] = label
        return label

    def pin_desc(self, node):
        inst, pin = node
        if inst is None:
            return "%s (port)" % pin
        return "%s/%s (%s)" % (self.inst_label(inst), pin, self.insts[inst][0].name)


class Timer:
    """Arrival / slew propagation and checks."""

    def __init__(self, design, sdc):
        self.d = design
        self.sdc = sdc
        # node = (inst, pin) or (None, port); values indexed by RISE/FALL
        self.at_max = {}
        self.at_min = {}
        self.slew_max = {}
        self.slew_min = {}
        self.prev_max = {}   # (node, rf) -> (node, rf, kind)
        self.prev_min = {}
        self.load = {}
        self.endpoints = []  # dicts

    # -- helpers ----------------------------------------------------------
    def _set(self, node, rf, at, slew, prev, mode):
        atd, sld, prv = ((self.at_max, self.slew_max, self.prev_max) if mode == "max"
                         else (self.at_min, self.slew_min, self.prev_min))
        cur = atd.setdefault(node, [None, None])
        sl = sld.setdefault(node, [None, None])
        better = cur[rf] is None or (at > cur[rf] if mode == "max" else at < cur[rf])
        if better:
            cur[rf] = at
            prv[(node, rf)] = prev
        if sl[rf] is None or (slew > sl[rf] if mode == "max" else slew < sl[rf]):
            sl[rf] = slew

    def _copy_to_sinks(self, net, src_node):
        """Zero wire delay: every sink pin inherits the driver's timing."""
        for sink in self.d.sinks.get(net, []):
            for mode in ("max", "min"):
                atd = self.at_max if mode == "max" else self.at_min
                sld = self.slew_max if mode == "max" else self.slew_min
                if src_node not in atd:
                    continue
                for rf in RF:
                    if atd[src_node][rf] is not None:
                        self._set(sink, rf, atd[src_node][rf], sld[src_node][rf],
                                  (src_node, rf, "net"), mode)

    @staticmethod
    def _out_rfs(sense, rf_in):
        if sense == "positive_unate":
            return (rf_in,)
        if sense == "negative_unate":
            return (1 - rf_in,)
        return RF

    # -- propagation -----------------------------------------------------
    def run(self):
        d, sdc = self.d, self.sdc
        clk = sdc.clock_port
        for net in d.driver:
            self.load[net] = d.net_load(net, sdc)

        # sources: input ports
        for p in d.in_ports:
            if p == clk or p in sdc.false_from:
                continue
            node = (None, p)
            delay = sdc.input_delay.get(p, 0.0)
            slew = sdc.input_slew.get(p, 0.0)
            for rf in RF:
                for mode in ("max", "min"):
                    self._set(node, rf, delay, slew, None, mode)
            self._copy_to_sinks(d.port_bits[p], node)

        # sources: flip-flop outputs (clock edge at t=0, ideal clock)
        comb = []
        for iname, (cell, conns) in d.insts.items():
            if not cell.sequential:
                comb.append(iname)
                continue
            for pname, pin in cell.pins.items():
                if pin.dir != "output" or pname not in conns:
                    continue
                net = conns[pname]
                if not isinstance(net, int):
                    continue
                load = self.load.get(net, 0.0)
                node = (iname, pname)
                for arc in pin.arcs:
                    if arc.type not in ("rising_edge", "falling_edge"):
                        continue
                    for rf in RF:
                        if arc.delay[rf] is None:
                            continue
                        dl = arc.delay[rf].lookup(input_slew=sdc.clock_slew, load=load)
                        sl = arc.slew[rf].lookup(input_slew=sdc.clock_slew, load=load)
                        for mode in ("max", "min"):
                            self._set(node, rf, dl, sl, ((iname, arc.related), RISE, "clock"), mode)
                self._copy_to_sinks(net, node)

        # combinational cells in topological order (Kahn on nets)
        pending = {}
        waiting = defaultdict(list)
        ready = []
        for iname in comb:
            cell, conns = d.insts[iname]
            deps = set()
            for pname, net in conns.items():
                if cell.pins[pname].dir == "input" and isinstance(net, int):
                    drv = d.driver.get(net)
                    if drv and drv[0] is not None and not d.insts[drv[0]][0].sequential:
                        deps.add(drv[0])
            pending[iname] = len(deps)
            for dep in deps:
                waiting[dep].append(iname)
            if not deps:
                ready.append(iname)
        done = 0
        while ready:
            iname = ready.pop()
            done += 1
            self._eval_comb(iname)
            for nxt in waiting[iname]:
                pending[nxt] -= 1
                if pending[nxt] == 0:
                    ready.append(nxt)
        if done != len(comb):
            sys.exit("combinational loop detected (%d of %d cells levelized)" % (done, len(comb)))

        self._checks()

    def _eval_comb(self, iname):
        cell, conns = self.d.insts[iname]
        for pname, pin in cell.pins.items():
            if pin.dir != "output" or pname not in conns:
                continue
            net = conns[pname]
            if not isinstance(net, int):
                continue
            load = self.load.get(net, 0.0)
            node = (iname, pname)
            for arc in pin.arcs:
                if arc.type != "combinational":
                    continue
                src = (iname, arc.related)
                for mode in ("max", "min"):
                    atd = self.at_max if mode == "max" else self.at_min
                    sld = self.slew_max if mode == "max" else self.slew_min
                    if src not in atd:
                        continue
                    for rf_in in RF:
                        a_in = atd[src][rf_in]
                        if a_in is None:
                            continue
                        s_in = sld[src][rf_in]
                        for rf_out in self._out_rfs(arc.sense, rf_in):
                            if arc.delay[rf_out] is None:
                                continue
                            dl = arc.delay[rf_out].lookup(input_slew=s_in, load=load)
                            sl = arc.slew[rf_out].lookup(input_slew=s_in, load=load)
                            self._set(node, rf_out, a_in + dl, sl, (src, rf_in, "cell"), mode)
            self._copy_to_sinks(net, node)

    # -- checks ----------------------------------------------------------
    def _checks(self):
        d, sdc = self.d, self.sdc
        T, unc = sdc.period, sdc.uncertainty
        for iname, (cell, conns) in d.insts.items():
            if not cell.sequential:
                continue
            for pname, pin in cell.pins.items():
                node = (iname, pname)
                for arc in pin.arcs:
                    if arc.type not in ("setup_rising", "hold_rising"):
                        continue
                    for rf in RF:
                        tbl = arc.constraint[rf]
                        if tbl is None:
                            continue
                        if arc.type == "setup_rising":
                            at = self.at_max.get(node, [None, None])[rf]
                            if at is None:
                                continue
                            s = self.slew_max[node][rf]
                            lib_t = tbl.lookup(constrained_slew=s, related_slew=sdc.clock_slew)
                            req = T - lib_t - unc
                            self.endpoints.append(dict(kind="setup", node=node, rf=rf, at=at,
                                                       req=req, slack=req - at, lib=lib_t))
                        else:
                            at = self.at_min.get(node, [None, None])[rf]
                            if at is None:
                                continue
                            s = self.slew_min[node][rf]
                            lib_t = tbl.lookup(constrained_slew=s, related_slew=sdc.clock_slew)
                            req = lib_t + unc
                            self.endpoints.append(dict(kind="hold", node=node, rf=rf, at=at,
                                                       req=req, slack=at - req, lib=lib_t))
        for p in d.out_ports:
            node = (None, p)
            od = sdc.output_delay.get(p)
            if od is None:
                continue
            for rf in RF:
                at = self.at_max.get(node, [None, None])[rf]
                if at is not None:
                    req = T - od - unc
                    self.endpoints.append(dict(kind="setup", node=node, rf=rf, at=at,
                                               req=req, slack=req - at, lib=od))
                at = self.at_min.get(node, [None, None])[rf]
                if at is not None:
                    req = -od + unc
                    self.endpoints.append(dict(kind="hold", node=node, rf=rf, at=at,
                                               req=req, slack=at - req, lib=od))

    # -- reporting -------------------------------------------------------
    def trace(self, node, rf, mode):
        prv = self.prev_max if mode == "max" else self.prev_min
        path = []
        cur = (node, rf, None)
        while True:
            n, r, kind = cur
            path.append((n, r, kind))
            p = prv.get((n, r))
            if p is None:
                break
            src, srf, k = p
            if k == "clock":
                path.append((src, srf, "clock"))
                break
            cur = (src, srf, k)
        path.reverse()
        return path

    def worst(self, kind):
        """Worst slack per endpoint pin (rise/fall merged), sorted."""
        best = {}
        for e in self.endpoints:
            if e["kind"] != kind:
                continue
            k = e["node"]
            if k not in best or e["slack"] < best[k]["slack"]:
                best[k] = e
        return sorted(best.values(), key=lambda e: e["slack"])

    def format_path(self, e):
        mode = "max" if e["kind"] == "setup" else "min"
        atd = self.at_max if mode == "max" else self.at_min
        sld = self.slew_max if mode == "max" else self.slew_min
        path = self.trace(e["node"], e["rf"], mode)
        d = self.d
        start = path[0][0]
        lines = []
        sp = d.pin_desc(start)
        if path[0][2] == "clock":
            sp += "  (rising edge-triggered flip-flop clocked by %s)" % self.sdc.clock_name
        else:
            sp += "  (input port clocked by %s)" % self.sdc.clock_name
        ep = d.pin_desc(e["node"])
        if e["node"][0] is not None:
            ep += "  (rising edge-triggered flip-flop clocked by %s)" % self.sdc.clock_name
        else:
            ep += "  (output port clocked by %s)" % self.sdc.clock_name
        lines.append("Startpoint: " + sp)
        lines.append("Endpoint:   " + ep)
        lines.append("Path Group: %s" % self.sdc.clock_name)
        lines.append("Path Type:  %s" % mode)
        lines.append("")
        hdr = "%9s %9s %8s %8s   %s" % ("Load(fF)", "Slew", "Delay", "Time", "Description")
        lines.append(hdr)
        lines.append("-" * 78)
        lines.append("%9s %9s %8.3f %8.3f   clock %s (rise edge)" % ("", "", 0.0, 0.0, self.sdc.clock_name))
        lines.append("%9s %9s %8.3f %8.3f   clock network delay (ideal)" % ("", "", 0.0, 0.0))
        prev_t = 0.0
        for n, r, kind in path:
            if kind == "clock":
                lines.append("%9s %9.3f %8.3f %8.3f ^ %s" % ("", self.sdc.clock_slew, 0.0, 0.0, d.pin_desc(n)))
                continue
            if n[0] is None and n[1] in d.in_ports and kind is None:
                t = atd[n][r]
                lines.append("%9s %9s %8.3f %8.3f   input external delay" % ("", "", t, t))
                prev_t = t
            t = atd[n][r]
            s = sld[n][r]
            is_out = n[0] is not None and d.insts[n[0]][0].pins[n[1]].dir == "output"
            load = ""
            if is_out:
                net = d.insts[n[0]][1][n[1]]
                load = "%.2f" % self.load.get(net, 0.0)
            elif n[0] is None and n[1] in d.in_ports:
                load = "%.2f" % self.load.get(d.port_bits[n[1]], 0.0)
            lines.append("%9s %9.3f %8.3f %8.3f %s %s" % (load, s, t - prev_t, t, RF_SYM[r], d.pin_desc(n)))
            if is_out:
                nn = d.net_name.get(d.insts[n[0]][1][n[1]], "")
                if nn and not nn.startswith("$"):
                    lines.append("%9s %9s %8s %8s     %s (net)" % ("", "", "", "", nn))
            prev_t = t
        lines.append("%9s %9s %8s %8.3f   data arrival time" % ("", "", "", e["at"]))
        lines.append("")
        T, unc = self.sdc.period, self.sdc.uncertainty
        if e["kind"] == "setup":
            lines.append("%9s %9s %8.3f %8.3f   clock %s (rise edge)" % ("", "", T, T, self.sdc.clock_name))
            lines.append("%9s %9s %8.3f %8.3f   clock network delay (ideal)" % ("", "", 0.0, T))
            lines.append("%9s %9s %8.3f %8.3f   clock uncertainty" % ("", "", -unc, T - unc))
            what = "library setup time" if e["node"][0] is not None else "output external delay"
            lines.append("%9s %9s %8.3f %8.3f   %s" % ("", "", -e["lib"], e["req"], what))
        else:
            lines.append("%9s %9s %8.3f %8.3f   clock %s (rise edge)" % ("", "", 0.0, 0.0, self.sdc.clock_name))
            lines.append("%9s %9s %8.3f %8.3f   clock uncertainty" % ("", "", unc, unc))
            what = "library hold time" if e["node"][0] is not None else "output external delay"
            lines.append("%9s %9s %8.3f %8.3f   %s" % ("", "", e["req"] - unc, e["req"], what))
        lines.append("%9s %9s %8s %8.3f   data required time" % ("", "", "", e["req"]))
        lines.append("-" * 78)
        lines.append("%9s %9s %8s %8.3f   slack (%s)" % ("", "", "", e["slack"],
                                                         "MET" if e["slack"] >= 0 else "VIOLATED"))
        stages = sum(1 for n, r, k in path if n[0] is not None and k != "clock"
                     and not d.insts[n[0]][0].sequential
                     and d.insts[n[0]][0].pins[n[1]].dir == "output")
        lines.append("")
        lines.append("logic depth: %d gates" % stages)
        return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lib", required=True)
    ap.add_argument("--netlist", required=True, help="Yosys JSON netlist")
    ap.add_argument("--top", required=True)
    ap.add_argument("--sdc", required=True)
    ap.add_argument("--report", help="write the full report here")
    ap.add_argument("--summary-json", help="write summary numbers as JSON")
    ap.add_argument("--paths", type=int, default=1, help="number of setup paths to print")
    ap.add_argument("--period", type=float, help="override the SDC clock period (ns)")
    a = ap.parse_args()

    lib = Library(a.lib)
    design = Design(lib, a.netlist, a.top)
    sdc = parse_sdc(a.sdc, design.in_ports, design.out_ports)
    if a.period:
        sdc.period = a.period
    if sdc.period is None:
        sys.exit("no create_clock in SDC")
    timer = Timer(design, sdc)
    timer.run()

    setup = timer.worst("setup")
    hold = timer.worst("hold")
    wns = min(0.0, setup[0]["slack"]) if setup else 0.0
    tns = sum(e["slack"] for e in setup if e["slack"] < 0)
    nviol = sum(1 for e in setup if e["slack"] < 0)
    whs = hold[0]["slack"] if hold else 0.0
    hviol = sum(1 for e in hold if e["slack"] < 0)
    # Delays don't depend on the period, so the smallest passing period is
    # T - worst_setup_slack.
    min_period = sdc.period - setup[0]["slack"] if setup else 0.0
    crit = setup[0]
    crit_delay = crit["at"]

    out = []
    out.append("=" * 78)
    out.append("Static timing report  -  design %s" % design.top)
    out.append("library  : %s (%s)   wire load: %s" % (lib.name, a.lib.split("/")[-1], lib.default_wire_load))
    out.append("clock    : %s  period %.3f ns  uncertainty %.3f ns  transition %.3f ns"
               % (sdc.clock_name, sdc.period, sdc.uncertainty, sdc.clock_slew))
    out.append("cells    : %d  (%d sequential)" % (len(design.insts),
               sum(1 for c, _ in design.insts.values() if c.sequential)))
    out.append("=" * 78)
    out.append("")
    out.append("Summary")
    out.append("-------")
    out.append("setup  WNS %8.3f ns   TNS %9.3f ns   violating endpoints %d / %d"
               % (wns, tns, nviol, len(setup)))
    out.append("       worst setup slack %+.3f ns" % setup[0]["slack"])
    out.append("hold   WHS %8.3f ns                     violating endpoints %d / %d"
               % (whs, hviol, len(hold)))
    out.append("critical path data arrival %.3f ns" % crit_delay)
    out.append("minimum clock period %.3f ns  ->  Fmax %.1f MHz" % (min_period, 1000.0 / min_period))
    out.append("")
    out.append("Worst setup endpoints")
    out.append("---------------------")
    for e in setup[:10]:
        out.append("  %8.3f  %s" % (e["slack"], design.pin_desc(e["node"])))
    out.append("")
    for i, e in enumerate(setup[:a.paths]):
        out.append("=" * 78)
        out.append("Setup path %d" % (i + 1))
        out.append("=" * 78)
        out.append(timer.format_path(e))
        out.append("")
    if hold:
        out.append("=" * 78)
        out.append("Hold path 1")
        out.append("=" * 78)
        out.append(timer.format_path(hold[0]))
        out.append("")
    text = "\n".join(out)
    if a.report:
        with open(a.report, "w") as f:
            f.write(text + "\n")
    print("\n".join(out[:16]))

    if a.summary_json:
        area = sum(c.area for c, _ in design.insts.values())
        seq = sum(1 for c, _ in design.insts.values() if c.sequential)
        json.dump(dict(design=design.top, period=sdc.period, wns=wns, tns=tns,
                       worst_setup_slack=setup[0]["slack"],
                       setup_violations=nviol, endpoints=len(setup), whs=whs,
                       hold_violations=hviol, min_period=min_period,
                       fmax_mhz=1000.0 / min_period, crit_arrival=crit_delay,
                       crit_start=design.pin_desc(timer.trace(crit["node"], crit["rf"], "max")[0][0]),
                       crit_end=design.pin_desc(crit["node"]),
                       cells=len(design.insts), flops=seq, area=area),
                  open(a.summary_json, "w"), indent=2)


if __name__ == "__main__":
    main()
