#!/usr/bin/env python3
"""
SALAM Visualizer - Validated Functional Unit Trace Preview
Parses gem5-SALAM observability JSON and produces a standalone, interactive
visual simulation dashboard with cycle-by-cycle Gantt playback, FU concurrency,
and denied-attempt summaries. This viewer does not evaluate numerical
correctness or establish physical RTL timing accuracy.
"""

import argparse
import codecs
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

OPCODE_MAP = {
    1: ("Ret", "#94a3b8"),
    2: ("Br", "#64748b"),
    3: ("Switch", "#64748b"),
    13: ("Add", "#38bdf8"),  # Sky blue
    14: ("FAdd", "#0284c7"),
    15: ("Sub", "#0ea5e9"),
    16: ("FSub", "#0369a1"),
    17: ("Mul", "#a855f7"),  # Purple
    18: ("FMul", "#7e22ce"),
    19: ("UDiv", "#c084fc"),
    20: ("SDiv", "#9333ea"),
    25: ("Shl", "#f59e0b"),  # Amber
    26: ("LShr", "#d97706"),  # Orange
    27: ("AShr", "#b45309"),
    28: ("And", "#10b981"),  # Emerald green
    29: ("Or", "#059669"),
    30: ("Xor", "#047857"),
    31: ("Alloca", "#6b7280"),
    32: ("Load", "#3b82f6"),  # Blue
    33: ("Store", "#ec4899"),  # Pink
    34: ("GEP", "#06b6d4"),  # Cyan
    53: ("ICmp", "#eab308"),  # Yellow
    55: ("Phi", "#8b5cf6"),
    57: ("Select", "#6366f1"),
}

# Unit names and IDs come from the validated simulator trace. Historical
# hardcoded FU aliases are intentionally retired; future units stay visible.

# Preview limits affect rendering only; every source event is replayed.
MAX_TRACE_BYTES = 512 * 1024 * 1024
MAX_TRACE_EVENTS = 4194304
DEFAULT_MAX_SPANS = 20000
COUNTERS = ("attempts", "grants", "denials", "releases", "peak", "outstanding")


class TraceValidationError(ValueError):
    """The trace cannot substantiate a complete FU scheduling visualization."""


def _unsigned(value, name, positive=False):
    if type(value) is not int or value < (1 if positive else 0):
        raise TraceValidationError(name + " must be an unsigned integer")
    return value


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TraceValidationError("Duplicate JSON key: " + key)
        result[key] = value
    return result


class _JSONStream:
    """Incrementally decode the top-level object and each trace event.

    The simulator writes a single JSON object, not JSONL. Retaining the whole
    trace is unnecessary: this reader keeps at most one decoded event plus a
    bounded text window. Other top-level values are bounded to one MiB.
    """

    def __init__(self, stream):
        self.stream = stream
        self.buffer = ""
        self.pos = 0
        self.eof = False
        self.bytes_read = 0
        self.digest = hashlib.sha256()
        self.text_decoder = codecs.getincrementaldecoder("utf-8")()
        self.decoder = json.JSONDecoder(object_pairs_hook=_unique_pairs)

    def _fill(self):
        self.buffer = self.buffer[self.pos :]
        self.pos = 0
        chunk = self.stream.read(65536)
        self.bytes_read += len(chunk)
        self.digest.update(chunk)
        if self.bytes_read > MAX_TRACE_BYTES:
            raise TraceValidationError("Trace grew beyond the input budget")
        self.buffer += self.text_decoder.decode(chunk, final=not chunk)
        self.eof = not chunk
        if len(self.buffer) > 1024 * 1024:
            raise TraceValidationError("JSON value exceeds one MiB")

    def peek(self):
        while True:
            while self.pos < len(self.buffer) and self.buffer[self.pos].isspace():
                self.pos += 1
            if self.pos < len(self.buffer):
                return self.buffer[self.pos]
            if self.eof:
                return ""
            self._fill()

    def take(self, expected):
        if self.peek() != expected:
            raise TraceValidationError("Expected JSON delimiter " + expected)
        self.pos += 1

    def value(self):
        self.peek()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.pos)
                # Numeric tokens can straddle read boundaries.
                if end == len(self.buffer) and not self.eof:
                    self._fill()
                    continue
                self.pos = end
                return value
            except json.JSONDecodeError as exc:
                if self.eof:
                    raise TraceValidationError("Malformed JSON: " + str(exc))
                self._fill()

    def items(self):
        self.take("{")
        keys = set()
        first = True
        while self.peek() != "}":
            if not first:
                self.take(",")
            first = False
            key = self.value()
            if not isinstance(key, str) or key in keys:
                raise TraceValidationError("Unique top-level JSON keys required")
            keys.add(key)
            if len(keys) > 64:
                raise TraceValidationError("Too many top-level metadata fields")
            self.take(":")
            if key in ("event", "trace_start", "trace_end"):
                raise TraceValidationError("Reserved top-level key")
            if key == "trace":
                self.take("[")
                event_first = True
                yield "trace_start", None
                while self.peek() != "]":
                    if not event_first:
                        self.take(",")
                    event_first = False
                    yield "event", self.value()
                self.take("]")
                yield "trace_end", None
            else:
                yield key, self.value()
        self.take("}")
        if self.peek():
            raise TraceValidationError("Unexpected data after JSON object")


def _file_identity(info):
    """Include inode and change time: size/mtime alone miss atomic replacement."""
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def parse_salam_trace(trace_file_path, max_spans=DEFAULT_MAX_SPANS):
    """Replay the full trace; retain only an explicitly bounded HTML preview.

    This checks scheduling evidence, not benchmark numerical correctness.
    The established Workbench numerical/GUI checks remain independent.
    """
    import heapq

    _unsigned(max_spans, "max_spans", positive=True)
    if max_spans > 100000:
        raise TraceValidationError("max_spans must not exceed 100000")
    source = Path(trace_file_path)
    before = source.stat()
    if not stat.S_ISREG(before.st_mode):
        raise TraceValidationError("Source must be a regular file")
    if before.st_size > MAX_TRACE_BYTES:
        raise TraceValidationError("Trace exceeds the 512 MiB input budget")
    header, indexed, observed, leases = {}, {}, {}, {}
    spans = []
    event_count = completed = peak = last_lease = 0
    previous_cycle = previous_tick = -1
    first_tick = None
    trace_started = trace_ended = False
    with source.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if _file_identity(opened) != _file_identity(before):
            raise TraceValidationError("Source changed while opening")
        reader = _JSONStream(stream)
        for key, value in reader.items():
            if key == "trace_start":
                trace_started = True
                invocation = header.get("invocation")
                if (
                    header.get("kind") != "salam_fu_scheduling"
                    or type(header.get("schema_version")) is not int
                    or header["schema_version"] != 1
                ):
                    raise TraceValidationError("Expected SALAM FU schema version 1")
                if (
                    not isinstance(invocation, dict)
                    or not isinstance(invocation.get("name"), str)
                    or not invocation["name"]
                ):
                    raise TraceValidationError("Named invocation required before trace")
                for field in ("elapsed_cycles", "elapsed_ticks"):
                    _unsigned(invocation.get(field), field, positive=True)
                if invocation["elapsed_cycles"] > 9007199254740991:
                    raise TraceValidationError(
                        "Cycle range exceeds exact browser integers"
                    )
                units = header.get("units")
                if not isinstance(units, list) or not units or len(units) > 4096:
                    raise TraceValidationError(
                        "Unit declarations required before trace"
                    )
                names = set()
                for unit in units:
                    if not isinstance(unit, dict):
                        raise TraceValidationError("Unit must be an object")
                    uid = _unsigned(unit.get("id"), "unit.id", positive=True)
                    if uid > 4294967295:
                        raise TraceValidationError("FU ID exceeds native uint32 range")
                    name = unit.get("name")
                    if (
                        uid in indexed
                        or not isinstance(name, str)
                        or not name
                        or len(name) > 256
                        or name in names
                    ):
                        raise TraceValidationError("Unique unit IDs and names required")
                    names.add(name)
                    for field in ("limit",) + COUNTERS:
                        _unsigned(unit.get(field), "unit." + field)
                    indexed[uid] = unit
                    observed[uid] = dict.fromkeys(COUNTERS, 0)
                continue
            if key == "trace_end":
                trace_ended = True
                continue
            if key != "event":
                header[key] = value
                continue
            event_count += 1
            if event_count > MAX_TRACE_EVENTS:
                raise TraceValidationError("Trace event budget exceeded")
            ev = value
            fields = ("cycle", "tick", "uid", "opcode", "fu_id", "lease_id")
            if not isinstance(ev, dict):
                raise TraceValidationError("Trace event must be an object")
            for field in fields:
                _unsigned(
                    ev.get(field),
                    "event." + field,
                    positive=field in ("cycle", "fu_id"),
                )
            kind, fu, lid = ev.get("event"), ev["fu_id"], ev["lease_id"]
            if kind not in ("grant", "release", "deny") or fu not in indexed:
                raise TraceValidationError("Unknown event kind or undeclared FU")
            if (
                ev["cycle"] < previous_cycle
                or ev["tick"] < previous_tick
                or ev["cycle"] > invocation["elapsed_cycles"]
            ):
                raise TraceValidationError("Event order or invocation bounds invalid")
            if first_tick is None:
                first_tick = ev["tick"]
            previous_cycle, previous_tick = ev["cycle"], ev["tick"]
            count, limit = observed[fu], indexed[fu]["limit"]
            if kind == "grant":
                if lid <= last_lease:
                    raise TraceValidationError("Grant lease IDs must increase")
                if limit and count["outstanding"] >= limit:
                    raise TraceValidationError("Grant exceeds FU capacity")
                last_lease = lid
                leases[lid] = ev
                count["attempts"] += 1
                count["grants"] += 1
                count["outstanding"] += 1
                count["peak"] = max(count["peak"], count["outstanding"])
            elif kind == "deny":
                if lid or not limit or count["outstanding"] < limit:
                    raise TraceValidationError("Denial without full positive FU cap")
                count["attempts"] += 1
                count["denials"] += 1
            else:
                grant = leases.pop(lid, None)
                if (
                    not lid
                    or grant is None
                    or any(ev[f] != grant[f] for f in ("fu_id", "uid", "opcode"))
                ):
                    raise TraceValidationError("Unmatched release identity")
                count["releases"] += 1
                count["outstanding"] -= 1
                completed += 1
                if len(spans) < max_spans:
                    opcode = grant["opcode"]
                    op_name, color = OPCODE_MAP.get(
                        opcode, ("Op_{}".format(opcode), "#64748b")
                    )
                    spans.append(
                        {
                            "lease_id": str(lid),
                            "fu_id": fu,
                            "fu_name": indexed[fu]["name"],
                            "opcode_id": str(opcode),
                            "opcode_name": op_name,
                            "color": color,
                            "uid": str(grant["uid"]),
                            "start_cycle": grant["cycle"],
                            "end_cycle": ev["cycle"],
                            "duration": ev["cycle"] - grant["cycle"],
                            # Strings preserve ticks beyond JS's exact integer range.
                            "start_tick": str(grant["tick"]),
                            "end_tick": str(ev["tick"]),
                        }
                    )
            peak = max(peak, len(leases))
        if _file_identity(os.fstat(stream.fileno())) != _file_identity(
            opened
        ) or _file_identity(source.stat()) != _file_identity(opened):
            raise TraceValidationError("Source changed during replay")
        digest = reader.digest
        if reader.bytes_read != opened.st_size:
            raise TraceValidationError("Parsed byte count differs from source size")
    if (
        first_tick is not None
        and previous_tick - first_tick > invocation["elapsed_ticks"]
    ):
        raise TraceValidationError("Event tick span exceeds invocation elapsed_ticks")
    if (
        not trace_started
        or not trace_ended
        or header.get("trace_truncated") is not False
    ):
        raise TraceValidationError("Complete, explicitly untruncated trace required")
    if leases:
        raise TraceValidationError("Unreleased grants remain at invocation end")
    if "trace_event_limit" in header:
        budget = _unsigned(header["trace_event_limit"], "trace_event_limit", True)
        if budget > MAX_TRACE_EVENTS or event_count > budget:
            raise TraceValidationError("Trace event limit invalid or exceeded")
    for uid, unit in indexed.items():
        for field in COUNTERS:
            if unit[field] != observed[uid][field]:
                raise TraceValidationError("Unit counter mismatch: " + field)
    totals = header.get("totals")
    if not isinstance(totals, dict):
        raise TraceValidationError("Totals are required")
    for field in COUNTERS:
        actual = peak if field == "peak" else sum(u[field] for u in observed.values())
        if _unsigned(totals.get(field), "totals." + field) != actual:
            raise TraceValidationError("Total counter mismatch: " + field)
    if _file_identity(source.stat()) != _file_identity(opened):
        raise TraceValidationError("Source changed after replay")
    spans.sort(
        key=lambda item: (
            item["start_cycle"],
            item["end_cycle"],
            item["lease_id"],
        )
    )
    lane_ends, lane_counts, deltas = {}, {}, {}
    for span in spans:
        fu = span["fu_id"]
        lanes = lane_ends.setdefault(fu, [])
        if lanes and lanes[0][0] <= span["start_cycle"]:
            _, lane = heapq.heappop(lanes)
        else:
            lane = lane_counts.get(fu, 0)
            lane_counts[fu] = lane + 1
        heapq.heappush(lanes, (span["end_cycle"], lane))
        span["lane"] = lane
        # [grant, release): zero-duration operations are markers, never
        # fabricated one-cycle activity. Event-order peak remains separate.
        for cycle, delta in (
            (span["start_cycle"], 1),
            (span["end_cycle"], -1),
        ):
            deltas[cycle] = deltas.get(cycle, 0) + delta
    concurrency, active = [], 0
    for cycle in sorted(deltas):
        active += deltas[cycle]
        concurrency.append({"cycle": cycle, "count": active})
    return {
        "invocation": dict(invocation, elapsed_ticks=str(invocation["elapsed_ticks"])),
        "units": header["units"],
        "spans": spans,
        "fu_lane_counts": lane_counts,
        "concurrency": concurrency,
        "max_cycle": invocation["elapsed_cycles"],
        "totals": totals,
        "validation": {
            "state": "passed",
            "scope": "FU scheduling trace only",
            "numerical_correctness": "not evaluated",
            "events_replayed": event_count,
        },
        "preview": {
            "rendered_spans": len(spans),
            "total_spans": completed,
            "limited": completed > len(spans),
            "max_spans": max_spans,
        },
        "source": {
            "path": str(source.resolve()),
            "sha256": digest.hexdigest(),
            "bytes": before.st_size,
        },
    }


def generate_html(trace_data, output_html_path):
    trace_json_str = (
        json.dumps(trace_data, ensure_ascii=True)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>gem5-SALAM Functional Unit Trace Viewer</title>
    <style>
        :root {{
            --bg-dark: #090d16;
            --bg-card: #131b2e;
            --bg-card-border: #1e293b;
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --accent-cyan: #06b6d4;
            --accent-blue: #3b82f6;
            --accent-purple: #a855f7;
            --accent-emerald: #10b981;
            --accent-amber: #f59e0b;
            --accent-rose: #f43f5e;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            background: var(--bg-dark);
            color: var(--text-main);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.5;
            padding: 20px;
            overflow-x: hidden;
        }}

        .dashboard-container {{
            max-width: 1520px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }}

        /* Header */
        header {{
            background: var(--bg-card);
            border: 1px solid var(--bg-card-border);
            border-radius: 12px;
            padding: 20px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
        }}

        .title-group h1 {{
            font-size: 20px;
            font-weight: 700;
            color: var(--accent-cyan);
            letter-spacing: -0.02em;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .badge {{
            font-size: 11px;
            font-weight: 600;
            background: rgba(6, 182, 212, 0.15);
            color: var(--accent-cyan);
            border: 1px solid rgba(6, 182, 212, 0.3);
            padding: 2px 8px;
            border-radius: 9999px;
            text-transform: uppercase;
        }}

        .title-group p {{
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 4px;
        }}

        .stats-strip {{
            display: flex;
            gap: 24px;
        }}

        .stat-item {{
            display: flex;
            flex-direction: column;
            align-items: flex-end;
        }}

        .stat-label {{
            font-size: 11px;
            color: var(--text-muted);
            text-transform: uppercase;
            font-weight: 600;
        }}

        .stat-value {{
            font-size: 18px;
            font-weight: 700;
            color: #fff;
            font-feature-settings: "tnum";
        }}

        /* Controls bar */
        .controls-card {{
            background: var(--bg-card);
            border: 1px solid var(--bg-card-border);
            border-radius: 12px;
            padding: 14px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 20px;
        }}

        .playback-controls {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        button.btn {{
            background: #1e293b;
            color: #fff;
            border: 1px solid #334155;
            padding: 8px 14px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
            display: flex;
            align-items: center;
            gap: 6px;
            user-select: none;
        }}

        button.btn:hover {{
            background: #334155;
            border-color: #475569;
        }}

        button.btn.btn-primary {{
            background: var(--accent-cyan);
            color: #041017;
            border-color: var(--accent-cyan);
        }}

        button.btn.btn-primary:hover {{
            background: #22d3ee;
        }}

        .scrubber-group {{
            flex: 1;
            display: flex;
            align-items: center;
            gap: 16px;
        }}

        .scrubber-slider {{
            flex: 1;
            -webkit-appearance: none;
            height: 6px;
            background: #1e293b;
            border-radius: 3px;
            outline: none;
            cursor: pointer;
        }}

        .scrubber-slider::-webkit-slider-thumb {{
            -webkit-appearance: none;
            width: 16px;
            height: 16px;
            border-radius: 50%;
            background: var(--accent-cyan);
            cursor: pointer;
            box-shadow: 0 0 10px rgba(6, 182, 212, 0.8);
        }}

        .cycle-counter {{
            font-family: monospace;
            font-size: 15px;
            font-weight: 700;
            color: var(--accent-cyan);
            min-width: 95px;
            text-align: right;
            user-select: none;
        }}

        /* Timeline View */
        .viewport-card {{
            background: var(--bg-card);
            border: 1px solid var(--bg-card-border);
            border-radius: 12px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 14px;
            overflow: hidden;
        }}

        .viewport-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .viewport-title {{
            font-size: 13px;
            font-weight: 700;
            color: #e2e8f0;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .legend {{
            display: flex;
            gap: 16px;
            font-size: 12px;
            color: var(--text-muted);
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .legend-dot {{
            width: 10px;
            height: 10px;
            border-radius: 3px;
        }}

        #ganttCanvas {{
            width: 100%;
            height: 380px;
            background: #090e1a;
            border-radius: 8px;
            cursor: grab;
            border: 1px solid #1e293b;
            display: block;
        }}

        #concurrencyCanvas {{
            width: 100%;
            height: 90px;
            background: #090e1a;
            border-radius: 8px;
            border: 1px solid #1e293b;
            display: block;
        }}

        /* Stable Bottom Grid */
        .bottom-grid {{
            display: grid;
            grid-template-columns: 1.7fr 1.3fr;
            gap: 20px;
            margin-bottom: 20px;
        }}

        .card {{
            background: var(--bg-card);
            border: 1px solid var(--bg-card-border);
            border-radius: 12px;
            padding: 20px;
            height: 330px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}

        .card-header-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid #1e293b;
        }}

        .card h3 {{
            font-size: 13px;
            font-weight: 700;
            color: #e2e8f0;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .table-scroll-container {{
            flex: 1;
            overflow-y: auto;
        }}

        .fu-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}

        .fu-table th {{
            text-align: left;
            color: var(--text-muted);
            font-weight: 600;
            padding: 8px 10px;
            border-bottom: 1px solid #1e293b;
            position: sticky;
            top: 0;
            background: var(--bg-card);
        }}

        .fu-table td {{
            padding: 8px 10px;
            border-bottom: 1px solid #1e293b;
            color: #e2e8f0;
            font-feature-settings: "tnum";
        }}

        .fu-table tr:hover {{
            background: rgba(255, 255, 255, 0.02);
        }}

        .active-chips-container {{
            flex: 1;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            overflow-y: auto;
            align-content: flex-start;
            padding-right: 6px;
        }}

        .chip {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 5px 10px;
            font-size: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
            font-family: monospace;
            user-select: none;
            transition: background 0.15s ease, border-color 0.15s ease;
        }}

        .chip:hover {{
            border-color: var(--accent-cyan);
            background: #25334d;
        }}

        .chip-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            flex-shrink: 0;
        }}

        #tooltip {{
            position: absolute;
            display: none;
            background: #1e293b;
            border: 1px solid #38bdf8;
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 12px;
            color: #fff;
            pointer-events: none;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.5);
            z-index: 100;
            font-family: monospace;
        }}
    </style>
</head>
<body>
    <div id="tooltip"></div>
    <div class="dashboard-container">
        <!-- Header -->
        <header>
            <div class="title-group">
                <h1>
                    <span>gem5-SALAM Hardware Accelerator Visualizer</span>
                    <span class="badge">FU trace replay verified</span>
                </h1>
                <p id="subheading">Target: <strong id="accName">system.gemm_clstr.gemm</strong> | Full-System ARM Timing Simulation</p>
            </div>
            <div class="stats-strip">
                <div class="stat-item">
                    <span class="stat-label">Elapsed Cycles</span>
                    <span class="stat-value" id="valCycles">0</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Sim Time</span>
                    <span class="stat-value" id="valTime">0 ns</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Peak Concurrency</span>
                    <span class="stat-value" style="color: var(--accent-emerald);" id="valPeak">0 FUs</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Denied FU attempts</span>
                    <span class="stat-value" style="color: var(--accent-cyan);" id="valStalls">0</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Total Operations</span>
                    <span class="stat-value" id="valOps">0</span>
                </div>
            </div>
        </header>

        <!-- Controls -->
        <div class="controls-card">
            <div class="playback-controls">
                <button class="btn btn-primary" id="btnPlay">▶ Play</button>
                <button class="btn" id="btnReset">↺ Reset</button>
                <button class="btn" id="btnSpeed">Speed: 1x</button>
                <button class="btn" id="btnZoomIn">Zoom +</button>
                <button class="btn" id="btnZoomOut">Zoom -</button>
            </div>
            <div class="scrubber-group">
                <input type="range" id="cycleScrubber" class="scrubber-slider" min="1" max="100" value="1">
                <div class="cycle-counter" id="cycleDisplay">Cycle: 1</div>
            </div>
        </div>

        <!-- Gantt View -->
        <div class="viewport-card">
            <div class="viewport-header">
                <div class="viewport-title">Functional Unit Lease Intervals</div>
                <div class="legend">
                    <div class="legend-item"><div class="legend-dot" style="background: #a855f7;"></div>Multipliers (Mul)</div>
                    <div class="legend-item"><div class="legend-dot" style="background: #38bdf8;"></div>Adders (Add)</div>
                    <div class="legend-item"><div class="legend-dot" style="background: #f59e0b;"></div>Bit Shifters (Shl/LShr)</div>
                    <div class="legend-item"><div class="legend-dot" style="background: #10b981;"></div>Bitwise (And/Or/Xor)</div>
                </div>
            </div>
            <p id="provenanceStatus" style="color:var(--text-muted);font-size:12px;overflow-wrap:anywhere;padding:8px 0;"></p>
            <div style="max-height:600px;overflow-y:auto;"><canvas id="ganttCanvas"></canvas></div>
            <div class="viewport-title" style="font-size: 11px; color: var(--text-muted);">Preview occupancy at cycle boundaries (half-open spans)</div>
            <canvas id="concurrencyCanvas"></canvas>
        </div>

        <!-- Details Grid (Rock-Solid Height, No Layout Shifts) -->
        <div class="bottom-grid">
            <div class="card">
                <div class="card-header-bar">
                    <h3>Functional Unit Allocation & Utilization Summary</h3>
                </div>
                <div class="table-scroll-container">
                    <table class="fu-table">
                        <thead>
                            <tr>
                                <th>Functional Unit</th>
                                <th>Allocation Limit</th>
                                <th>Total Attempts</th>
                                <th>Grants</th>
                                <th>Denied attempts</th>
                                <th>Peak Active</th>
                            </tr>
                        </thead>
                        <tbody id="fuTableBody">
                        </tbody>
                    </table>
                </div>
            </div>
            <div class="card">
                <div class="card-header-bar">
                    <h3>Active Instructions at Current Cycle</h3>
                    <span class="badge" id="activeCountBadge">0 active</span>
                </div>
                <div class="active-chips-container" id="activeChips">
                    <span style="color: var(--text-muted); font-size: 13px;">Move scrubber or click Play to see active operations.</span>
                </div>
            </div>
        </div>
    </div>

    <script>
        const TRACE_DATA = {trace_json_str};

        // DOM elements
        const accName = document.getElementById("accName");
        const valCycles = document.getElementById("valCycles");
        const valTime = document.getElementById("valTime");
        const valPeak = document.getElementById("valPeak");
        const valStalls = document.getElementById("valStalls");
        const valOps = document.getElementById("valOps");
        const cycleScrubber = document.getElementById("cycleScrubber");
        const cycleDisplay = document.getElementById("cycleDisplay");
        const btnPlay = document.getElementById("btnPlay");
        const btnReset = document.getElementById("btnReset");
        const btnSpeed = document.getElementById("btnSpeed");
        const btnZoomIn = document.getElementById("btnZoomIn");
        const btnZoomOut = document.getElementById("btnZoomOut");
        const ganttCanvas = document.getElementById("ganttCanvas");
        const concurrencyCanvas = document.getElementById("concurrencyCanvas");
        const fuTableBody = document.getElementById("fuTableBody");
        const activeChips = document.getElementById("activeChips");
        const activeCountBadge = document.getElementById("activeCountBadge");
        const tooltip = document.getElementById("tooltip");

        const gCtx = ganttCanvas.getContext("2d");
        const cCtx = concurrencyCanvas.getContext("2d");

        // Simulation state
        let currentCycle = 1;
        let isPlaying = false;
        let playInterval = null;
        let speedMultiplier = 1;
        const maxCycle = TRACE_DATA.max_cycle;

        // Viewport transform
        let zoomX = 1.0;
        let panX = 0;
        const activeUnitIds = new Set(TRACE_DATA.spans.map(s => s.fu_id));
        const TRACK_ORDER = TRACE_DATA.units
            .filter(u => activeUnitIds.has(u.id) || u.attempts > 0)
            .map(u => ({{ id: u.id, name: u.name }}));
        // Declared units are authoritative, including unfamiliar future FU IDs.
        const allLaneCount = Math.max(1, TRACK_ORDER.reduce((n, t) =>
            n + Math.max(2, TRACE_DATA.fu_lane_counts[t.id] || 1), 0));
        function escapeHtml(value) {{
            const node = document.createElement("div");
            node.textContent = String(value);
            return node.innerHTML;
        }}
        function trackGeometry(margin, plotH) {{
            let y = margin.top;
            return TRACK_ORDER.map(track => {{
                const lanes = Math.max(1, TRACE_DATA.fu_lane_counts[track.id] || 1);
                const height = plotH * Math.max(2, lanes) / allLaneCount;
                const result = {{ y, height, laneH: Math.max(0.1, (height - 6) / lanes) }};
                y += height;
                return result;
            }});
        }}

        // Populate header
        accName.textContent = TRACE_DATA.invocation.name || "SALAM Accelerator";
        valCycles.textContent = maxCycle + " cycles";
        valTime.textContent = TRACE_DATA.invocation.elapsed_ticks + " ticks";
        const preview = TRACE_DATA.preview;
        document.getElementById("provenanceStatus").textContent =
            "Scheduling replay: " + TRACE_DATA.validation.events_replayed + " events. " +
            "Showing " + preview.rendered_spans + " of " + preview.total_spans +
            " completed spans" + (preview.limited ? " (bounded preview; curve covers preview only). " : ". ") +
            "Numerical correctness: not evaluated by this viewer. " +
            "Raw SHA-256: " + TRACE_DATA.source.sha256;
        valPeak.textContent = (TRACE_DATA.totals.peak || 0) + " leases";
        valStalls.textContent = (TRACE_DATA.totals.denials || 0);
        valOps.textContent = TRACE_DATA.spans.length.toLocaleString();

        cycleScrubber.max = maxCycle;

        // Populate table
        const activeUnits = TRACE_DATA.units.filter(u => activeUnitIds.has(u.id) || u.attempts > 0);

        activeUnits.forEach(u => {{
            const row = document.createElement("tr");
            const limText = u.limit === 0 ? "Unlimited" : u.limit;
            const denialColor = u.denials > 0 ? "var(--accent-rose)" : "var(--accent-emerald)";
            row.innerHTML = `
                <td><strong>${{escapeHtml(u.name)}}</strong></td>
                <td><span class="badge" style="background:#1e293b; color:#94a3b8; border-color:#334155;">${{limText}}</span></td>
                <td>${{u.attempts}}</td>
                <td style="color:var(--accent-emerald); font-weight:600;">${{u.grants}}</td>
                <td style="color:${{denialColor}}; font-weight:600;">${{u.denials}}</td>
                <td><strong>${{u.peak}}</strong></td>
            `;
            fuTableBody.appendChild(row);
        }});

        // Resize canvases
        function resizeCanvases() {{
            ganttCanvas.style.height = Math.min(12000, Math.max(420, allLaneCount * 18 + 50)) + "px";
            const rect = ganttCanvas.getBoundingClientRect();
            ganttCanvas.width = rect.width * window.devicePixelRatio;
            ganttCanvas.height = rect.height * window.devicePixelRatio;
            gCtx.scale(window.devicePixelRatio, window.devicePixelRatio);

            const cRect = concurrencyCanvas.getBoundingClientRect();
            concurrencyCanvas.width = cRect.width * window.devicePixelRatio;
            concurrencyCanvas.height = cRect.height * window.devicePixelRatio;
            cCtx.scale(window.devicePixelRatio, window.devicePixelRatio);
            render();
        }}

        window.addEventListener("resize", resizeCanvases);

        // Render gantt
        function render() {{
            const width = ganttCanvas.clientWidth;
            const height = ganttCanvas.clientHeight;
            gCtx.clearRect(0, 0, width, height);

            const margin = {{ left: 160, right: 30, top: 30, bottom: 20 }};
            const plotW = width - margin.left - margin.right;
            const plotH = height - margin.top - margin.bottom;

            const scaleX = (cycle) => margin.left + ((cycle - 1) / maxCycle) * plotW * zoomX + panX;

            // Tracks
            const geometry = trackGeometry(margin, plotH);

            TRACK_ORDER.forEach((track, idx) => {{
                const y = geometry[idx].y;
                const trackHeight = geometry[idx].height;

                // Track background
                if (idx % 2 === 0) {{
                    gCtx.fillStyle = "rgba(255, 255, 255, 0.015)";
                    gCtx.fillRect(margin.left, y, plotW, trackHeight);
                }}

                // Track label
                gCtx.fillStyle = "#94a3b8";
                gCtx.font = "600 12px sans-serif";
                gCtx.textAlign = "right";
                gCtx.fillText(track.name, margin.left - 14, y + trackHeight / 2 + 4);

                // Divider line
                gCtx.strokeStyle = "#1e293b";
                gCtx.lineWidth = 1;
                gCtx.beginPath();
                gCtx.moveTo(margin.left, y + trackHeight);
                gCtx.lineTo(width - margin.right, y + trackHeight);
                gCtx.stroke();
            }});

            // Draw spans
            const blockPadding = 2;
            TRACE_DATA.spans.forEach(span => {{
                const trackIdx = TRACK_ORDER.findIndex(t => t.id === span.fu_id);
                if (trackIdx === -1) return;

                const trackY = geometry[trackIdx].y;
                const laneH = geometry[trackIdx].laneH;
                const spanY = trackY + 3 + span.lane * laneH;

                const x1 = scaleX(span.start_cycle);
                const x2 = scaleX(span.end_cycle);
                const spanW = Math.max(2, x2 - x1);

                if (x2 < margin.left || x1 > width - margin.right) return;

                // Opcode block
                gCtx.fillStyle = span.color;
                gCtx.globalAlpha = (span.start_cycle <= currentCycle && currentCycle < span.end_cycle) ? 1.0 : 0.65;
                gCtx.fillRect(x1 + blockPadding, spanY + 1, Math.max(1, spanW - blockPadding), Math.max(0.1, laneH - 2));
                gCtx.globalAlpha = 1.0;

                // Text label if wide enough
                if (spanW > 28 && laneH > 10) {{
                    gCtx.fillStyle = "#ffffff";
                    gCtx.font = "bold 9px monospace";
                    gCtx.textAlign = "center";
                    gCtx.fillText(span.opcode_name, x1 + spanW / 2, spanY + laneH / 2 + 3);
                }}
            }});

            // Draw current cycle cursor line
            const curX = scaleX(currentCycle);
            if (curX >= margin.left && curX <= width - margin.right) {{
                gCtx.strokeStyle = "rgba(6, 182, 212, 0.9)";
                gCtx.lineWidth = 2;
                gCtx.setLineDash([4, 4]);
                gCtx.beginPath();
                gCtx.moveTo(curX, margin.top);
                gCtx.lineTo(curX, height - margin.bottom);
                gCtx.stroke();
                gCtx.setLineDash([]);

                // Cursor pill
                gCtx.fillStyle = "var(--accent-cyan)";
                gCtx.font = "bold 10px monospace";
                gCtx.textAlign = "center";
                gCtx.fillText("Cycle " + currentCycle, curX, margin.top - 8);
            }}

            // Render Concurrency Curve
            renderConcurrency(scaleX, margin, width);
            updateActiveChips();
        }}

        function renderConcurrency(scaleX, margin, width) {{
            const cWidth = concurrencyCanvas.clientWidth;
            const cHeight = concurrencyCanvas.clientHeight;
            cCtx.clearRect(0, 0, cWidth, cHeight);

            const plotW = cWidth - margin.left - margin.right;
            const plotH = cHeight - 20;
            const peak = Math.max(1, TRACE_DATA.totals.peak || 0);

            // Grid lines
            cCtx.strokeStyle = "#1e293b";
            cCtx.lineWidth = 1;
            cCtx.beginPath();
            cCtx.moveTo(margin.left, cHeight - 10);
            cCtx.lineTo(cWidth - margin.right, cHeight - 10);
            cCtx.stroke();

            // Label
            cCtx.fillStyle = "#94a3b8";
            cCtx.font = "600 11px sans-serif";
            cCtx.textAlign = "right";
            cCtx.fillText("Concurrency", margin.left - 14, cHeight / 2 + 4);

            // Area curve
            cCtx.fillStyle = "rgba(16, 185, 129, 0.25)";
            cCtx.strokeStyle = "#10b981";
            cCtx.lineWidth = 2;
            cCtx.beginPath();
            cCtx.moveTo(margin.left, cHeight - 10);

            let previousCount = 0;
            TRACE_DATA.concurrency.forEach(point => {{
                const x = scaleX(point.cycle);
                cCtx.lineTo(x, cHeight - 10 - (previousCount / peak) * plotH);
                cCtx.lineTo(x, cHeight - 10 - (point.count / peak) * plotH);
                previousCount = point.count;
            }});

            cCtx.lineTo(scaleX(maxCycle), cHeight - 10);
            cCtx.closePath();
            cCtx.fill();
            cCtx.stroke();

            // Cursor on concurrency
            const curX = scaleX(currentCycle);
            if (curX >= margin.left && curX <= cWidth - margin.right) {{
                cCtx.strokeStyle = "rgba(6, 182, 212, 0.9)";
                cCtx.lineWidth = 2;
                cCtx.setLineDash([4, 4]);
                cCtx.beginPath();
                cCtx.moveTo(curX, 5);
                cCtx.lineTo(curX, cHeight - 10);
                cCtx.stroke();
                cCtx.setLineDash([]);
            }}
        }}

        // Smooth active chips rendering without layout shifting or strobe effect
        let lastActiveKey = "";
        function updateActiveChips() {{
            const active = TRACE_DATA.spans.filter(s => s.start_cycle <= currentCycle && currentCycle < s.end_cycle);
            activeCountBadge.textContent = active.length + " active";

            const currentKey = active.map(s => s.lease_id).join(",");
            if (currentKey === lastActiveKey) {{
                return; // Prevent DOM churn and flashing when active set hasn't changed
            }}
            lastActiveKey = currentKey;

            if (active.length === 0) {{
                activeChips.innerHTML = `<div style="color: var(--text-muted); font-size: 13px; padding: 20px 0;">Cycle ${{currentCycle}}: Pipeline transition / idle phase.</div>`;
                return;
            }}

            const chipsHtml = active.slice(0, 24).map(s => `
                <div class="chip">
                    <div class="chip-dot" style="background: ${{s.color}};"></div>
                    <span><strong>${{s.opcode_name}}</strong> (#${{s.uid}}) &rarr; ${{escapeHtml(s.fu_name)}}</span>
                </div>
            `).join("");

            const extra = active.length > 24 ? `<div class="chip" style="color:var(--text-muted);">+${{active.length - 24}} more active operations</div>` : "";
            activeChips.innerHTML = chipsHtml + extra;
        }}

        // Controls binding
        cycleScrubber.addEventListener("input", (e) => {{
            currentCycle = parseInt(e.target.value);
            cycleDisplay.textContent = "Cycle: " + currentCycle;
            render();
        }});

        btnPlay.addEventListener("click", () => {{
            if (isPlaying) {{
                clearInterval(playInterval);
                isPlaying = false;
                btnPlay.textContent = "▶ Play";
            }} else {{
                isPlaying = true;
                btnPlay.textContent = "⏸ Pause";
                playInterval = setInterval(() => {{
                    currentCycle++;
                    if (currentCycle > maxCycle) currentCycle = 1;
                    cycleScrubber.value = currentCycle;
                    cycleDisplay.textContent = "Cycle: " + currentCycle;
                    render();
                }}, 40 / speedMultiplier);
            }}
        }});

        btnReset.addEventListener("click", () => {{
            currentCycle = 1;
            cycleScrubber.value = 1;
            cycleDisplay.textContent = "Cycle: 1";
            zoomX = 1.0;
            panX = 0;
            render();
        }});

        btnSpeed.addEventListener("click", () => {{
            if (speedMultiplier === 1) speedMultiplier = 2;
            else if (speedMultiplier === 2) speedMultiplier = 5;
            else if (speedMultiplier === 5) speedMultiplier = 10;
            else speedMultiplier = 1;
            btnSpeed.textContent = "Speed: " + speedMultiplier + "x";
            if (isPlaying) {{
                clearInterval(playInterval);
                playInterval = setInterval(() => {{
                    currentCycle++;
                    if (currentCycle > maxCycle) currentCycle = 1;
                    cycleScrubber.value = currentCycle;
                    cycleDisplay.textContent = "Cycle: " + currentCycle;
                    render();
                }}, 40 / speedMultiplier);
            }}
        }});

        btnZoomIn.addEventListener("click", () => {{
            zoomX = Math.min(zoomX * 1.5, 12.0);
            render();
        }});

        btnZoomOut.addEventListener("click", () => {{
            zoomX = Math.max(zoomX / 1.5, 0.7);
            render();
        }});

        // Canvas pan
        let isDragging = false;
        let startPanX = 0;
        let mouseStartX = 0;

        ganttCanvas.addEventListener("mousedown", (e) => {{
            isDragging = true;
            mouseStartX = e.clientX;
            startPanX = panX;
            ganttCanvas.style.cursor = "grabbing";
        }});

        window.addEventListener("mouseup", () => {{
            isDragging = false;
            ganttCanvas.style.cursor = "grab";
        }});

        window.addEventListener("mousemove", (e) => {{
            if (isDragging) {{
                panX = startPanX + (e.clientX - mouseStartX);
                render();
            }}
        }});

        // Tooltip hover
        ganttCanvas.addEventListener("mousemove", (e) => {{
            if (isDragging) return;
            const rect = ganttCanvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;

            const margin = {{ left: 160, right: 30, top: 30, bottom: 20 }};
            const plotW = ganttCanvas.clientWidth - margin.left - margin.right;
            const plotH = ganttCanvas.clientHeight - margin.top - margin.bottom;
            const scaleX = (cycle) => margin.left + ((cycle - 1) / maxCycle) * plotW * zoomX + panX;
            const geometry = trackGeometry(margin, plotH);

            let hit = null;
            for (const span of TRACE_DATA.spans) {{
                const trackIdx = TRACK_ORDER.findIndex(t => t.id === span.fu_id);
                if (trackIdx === -1) continue;

                const trackY = geometry[trackIdx].y;
                const laneH = geometry[trackIdx].laneH;
                const spanY = trackY + 3 + span.lane * laneH;

                const x1 = scaleX(span.start_cycle);
                const x2 = scaleX(span.end_cycle);
                const spanW = Math.max(2, x2 - x1);

                if (mouseX >= x1 && mouseX <= x2 && mouseY >= spanY && mouseY <= spanY + laneH) {{
                    hit = span;
                    break;
                }}
            }}

            if (hit) {{
                tooltip.style.display = "block";
                tooltip.style.left = (e.pageX + 15) + "px";
                tooltip.style.top = (e.pageY + 10) + "px";
                tooltip.innerHTML = `
                    <div><strong>${{escapeHtml(hit.fu_name)}}</strong></div>
                    <div>Opcode: <strong>${{hit.opcode_name}}</strong> (#${{hit.opcode_id}})</div>
                    <div>Instruction UID: <strong>${{hit.uid}}</strong></div>
                    <div>Cycle interval [start, end): <strong>${{hit.start_cycle}} &rarr; ${{hit.end_cycle}}</strong> (${{hit.duration}} cyc)</div>
                    <div>Ticks: ${{hit.start_tick}} &rarr; ${{hit.end_tick}} ticks</div>
                    <div>Lease ID: #${{hit.lease_id}}</div>
                `;
            }} else {{
                tooltip.style.display = "none";
            }}
        }});

        ganttCanvas.addEventListener("mouseleave", () => {{
            tooltip.style.display = "none";
        }});

        // Initial setup
        setTimeout(resizeCanvases, 50);
    </script>
</body>
</html>
"""
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)


def export_trace(
    trace_path, output_path, max_spans=DEFAULT_MAX_SPANS, expected_sha256=None
):
    """Export a validated preview, optionally bound to a recorded raw hash."""
    source, output = Path(trace_path), Path(output_path)
    if source.resolve() == output.resolve():
        raise TraceValidationError("Output must not overwrite the source trace")
    if output.suffix.lower() != ".html":
        raise TraceValidationError("Output must have an .html extension")
    data = parse_salam_trace(source, max_spans=max_spans)
    if expected_sha256 is not None and data["source"]["sha256"] != expected_sha256:
        raise TraceValidationError("Source hash differs from recorded artifact")
    output.parent.mkdir(parents=True, exist_ok=True)
    generate_html(data, output)
    metadata = {key: data[key] for key in ("source", "validation", "preview")}
    metadata["output"] = str(output.resolve())
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", help="Complete direct SALAM FU scheduling JSON")
    parser.add_argument("output", nargs="?", default="salam_trace_dashboard.html")
    parser.add_argument("--max-spans", type=int, default=DEFAULT_MAX_SPANS)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args(argv)
    try:
        metadata = export_trace(
            args.trace, args.output, args.max_spans, args.expected_sha256
        )
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(2, "SALAM trace export rejected: {}\n".format(exc))
    print(json.dumps(metadata, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
