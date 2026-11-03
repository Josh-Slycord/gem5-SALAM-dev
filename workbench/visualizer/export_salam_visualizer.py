#!/usr/bin/env python3
"""
SALAM Visualizer - Microarchitectural Execution Trace Generator
Parses gem5-SALAM observability JSON and produces a standalone, interactive
visual simulation dashboard with cycle-by-cycle Gantt playback, FU concurrency,
and structural hazard analysis.
"""

import json
import os
import sys
from pathlib import Path

OPCODE_MAP = {
    1: ("Ret", "#94a3b8"),
    2: ("Br", "#64748b"),
    3: ("Switch", "#64748b"),
    13: ("Add", "#38bdf8"),        # Sky blue
    14: ("FAdd", "#0284c7"),
    15: ("Sub", "#0ea5e9"),
    16: ("FSub", "#0369a1"),
    17: ("Mul", "#a855f7"),        # Purple
    18: ("FMul", "#7e22ce"),
    19: ("UDiv", "#c084fc"),
    20: ("SDiv", "#9333ea"),
    25: ("Shl", "#f59e0b"),        # Amber
    26: ("LShr", "#d97706"),       # Orange
    27: ("AShr", "#b45309"),
    28: ("And", "#10b981"),        # Emerald green
    29: ("Or", "#059669"),
    30: ("Xor", "#047857"),
    31: ("Alloca", "#6b7280"),
    32: ("Load", "#3b82f6"),       # Blue
    33: ("Store", "#ec4899"),      # Pink
    34: ("GEP", "#06b6d4"),        # Cyan
    53: ("ICmp", "#eab308"),       # Yellow
    55: ("Phi", "#8b5cf6"),
    57: ("Select", "#6366f1")
}

FU_NAMES = {
    1: "Integer Adder",
    2: "Integer Multiplier",
    3: "Bit Shifter",
    4: "Bitwise Operations",
    5: "Float Adder",
    6: "Double Adder",
    7: "Float Multiplier",
    8: "Float Divider",
    9: "Double Multiplier",
    10: "Double Divider",
    15: "Bit Register"
}

def parse_salam_trace(trace_file_path):
    with open(trace_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    invocation = data.get("invocation", {})
    units_raw = data.get("units", [])
    trace = data.get("trace", [])

    grants = {}
    spans = []

    for ev in trace:
        lid = ev.get("lease_id")
        event_type = ev.get("event")
        if event_type == "grant":
            grants[lid] = ev
        elif event_type == "release":
            g = grants.pop(lid, None)
            if g:
                opcode_id = g.get("opcode", 0)
                op_name, op_color = OPCODE_MAP.get(opcode_id, (f"Op_{opcode_id}", "#64748b"))
                fu_id = g.get("fu_id", 0)
                fu_name = FU_NAMES.get(fu_id, f"FU_{fu_id}")

                spans.append({
                    "lease_id": lid,
                    "fu_id": fu_id,
                    "fu_name": fu_name,
                    "opcode_id": opcode_id,
                    "opcode_name": op_name,
                    "color": op_color,
                    "uid": g.get("uid", 0),
                    "start_cycle": g.get("cycle", 0),
                    "end_cycle": ev.get("cycle", 0),
                    "duration": max(1, ev.get("cycle", 0) - g.get("cycle", 0)),
                    "start_tick": g.get("tick", 0),
                    "end_tick": ev.get("tick", 0)
                })

    # Sort spans by start_cycle, then end_cycle
    spans.sort(key=lambda s: (s["start_cycle"], s["end_cycle"]))

    # Assign sub-lanes per FU so simultaneous parallel operations don't collide visually
    fu_lanes = {}
    for span in spans:
        fu = span["fu_id"]
        if fu not in fu_lanes:
            fu_lanes[fu] = []
        lanes = fu_lanes[fu]
        assigned_lane = 0
        found = False
        for i, lane_end in enumerate(lanes):
            if span["start_cycle"] >= lane_end:
                lanes[i] = span["end_cycle"]
                assigned_lane = i
                found = True
                break
        if not found:
            assigned_lane = len(lanes)
            lanes.append(span["end_cycle"])
        span["lane"] = assigned_lane

    # Calculate per-cycle concurrency
    max_cycle = invocation.get("elapsed_cycles", 0)
    if not max_cycle and spans:
        max_cycle = max(s["end_cycle"] for s in spans)

    concurrency = [0] * (max_cycle + 2)
    for span in spans:
        s_c = span["start_cycle"]
        e_c = span["end_cycle"]
        for c in range(s_c, e_c + 1):
            if c < len(concurrency):
                concurrency[c] += 1

    return {
        "invocation": invocation,
        "units": units_raw,
        "spans": spans,
        "fu_lane_counts": {k: len(v) for k, v in fu_lanes.items()},
        "concurrency": concurrency,
        "max_cycle": max_cycle,
        "totals": data.get("totals", {})
    }


def generate_html(trace_data, output_html_path):
    trace_json_str = json.dumps(trace_data)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>gem5-SALAM Accelerator Execution Twin</title>
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
                    <span class="badge">Cycle-Accurate Trace</span>
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
                    <span class="stat-label">Structural Stalls</span>
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
                <div class="viewport-title">Cycle-by-Cycle Functional Unit Execution Matrix</div>
                <div class="legend">
                    <div class="legend-item"><div class="legend-dot" style="background: #a855f7;"></div>Multipliers (Mul)</div>
                    <div class="legend-item"><div class="legend-dot" style="background: #38bdf8;"></div>Adders (Add)</div>
                    <div class="legend-item"><div class="legend-dot" style="background: #f59e0b;"></div>Bit Shifters (Shl/LShr)</div>
                    <div class="legend-item"><div class="legend-dot" style="background: #10b981;"></div>Bitwise (And/Or/Xor)</div>
                </div>
            </div>
            <canvas id="ganttCanvas"></canvas>
            <div class="viewport-title" style="font-size: 11px; color: var(--text-muted);">Concurrent Active Functional Units Across Time</div>
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
                                <th>Denials (Stalls)</th>
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
        const TRACK_ORDER = [
            {{ id: 2, name: "Integer Multiplier", color: "#a855f7" }},
            {{ id: 1, name: "Integer Adder", color: "#38bdf8" }},
            {{ id: 3, name: "Bit Shifter", color: "#f59e0b" }},
            {{ id: 4, name: "Bitwise Operations", color: "#10b981" }}
        ];

        // Populate header
        accName.textContent = TRACE_DATA.invocation.name || "SALAM Accelerator";
        valCycles.textContent = maxCycle + " cycles";
        valTime.textContent = (TRACE_DATA.invocation.elapsed_ticks / 1e6).toFixed(2) + " µs";
        valPeak.textContent = (TRACE_DATA.totals.peak || 0) + " FUs";
        valStalls.textContent = (TRACE_DATA.totals.denials || 0);
        valOps.textContent = TRACE_DATA.spans.length.toLocaleString();

        cycleScrubber.max = maxCycle;

        // Populate table
        const activeUnitIds = new Set(TRACE_DATA.spans.map(s => s.fu_id));
        const activeUnits = TRACE_DATA.units.filter(u => activeUnitIds.has(u.id) || u.attempts > 0);
        
        activeUnits.forEach(u => {{
            const row = document.createElement("tr");
            const limText = u.limit === 0 ? "Unlimited (Static)" : u.limit;
            const denialColor = u.denials > 0 ? "var(--accent-rose)" : "var(--accent-emerald)";
            row.innerHTML = `
                <td><strong>${{u.name}}</strong></td>
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
            const trackHeight = plotH / TRACK_ORDER.length;

            TRACK_ORDER.forEach((track, idx) => {{
                const y = margin.top + idx * trackHeight;

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

                const trackY = margin.top + trackIdx * trackHeight;
                const laneCount = Math.max(1, TRACE_DATA.fu_lane_counts[span.fu_id] || 1);
                const laneH = (trackHeight - 10) / Math.min(laneCount, 8);
                const spanY = trackY + 5 + (span.lane % 8) * laneH;

                const x1 = scaleX(span.start_cycle);
                const x2 = scaleX(span.end_cycle + 0.8);
                const spanW = Math.max(2, x2 - x1);

                if (x2 < margin.left || x1 > width - margin.right) return;

                // Opcode block
                gCtx.fillStyle = span.color;
                gCtx.globalAlpha = (span.start_cycle <= currentCycle && currentCycle <= span.end_cycle) ? 1.0 : 0.65;
                gCtx.fillRect(x1 + blockPadding, spanY + 1, spanW - blockPadding, laneH - 2);
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
            const peak = Math.max(1, TRACE_DATA.totals.peak || 18);

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

            for (let c = 1; c <= maxCycle; c++) {{
                const x = scaleX(c);
                const count = TRACE_DATA.concurrency[c] || 0;
                const y = cHeight - 10 - (count / peak) * plotH;
                cCtx.lineTo(x, y);
            }}

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
            const active = TRACE_DATA.spans.filter(s => s.start_cycle <= currentCycle && currentCycle <= s.end_cycle);
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
                    <span><strong>${{s.opcode_name}}</strong> (#${{s.uid}}) &rarr; ${{s.fu_name}}</span>
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
            const trackHeight = plotH / TRACK_ORDER.length;

            let hit = null;
            for (const span of TRACE_DATA.spans) {{
                const trackIdx = TRACK_ORDER.findIndex(t => t.id === span.fu_id);
                if (trackIdx === -1) continue;

                const trackY = margin.top + trackIdx * trackHeight;
                const laneCount = Math.max(1, TRACE_DATA.fu_lane_counts[span.fu_id] || 1);
                const laneH = (trackHeight - 10) / Math.min(laneCount, 8);
                const spanY = trackY + 5 + (span.lane % 8) * laneH;

                const x1 = scaleX(span.start_cycle);
                const x2 = scaleX(span.end_cycle + 0.8);
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
                    <div><strong>${{hit.fu_name}}</strong></div>
                    <div>Opcode: <strong>${{hit.opcode_name}}</strong> (#${{hit.opcode_id}})</div>
                    <div>Instruction UID: <strong>${{hit.uid}}</strong></div>
                    <div>Cycles: <strong>${{hit.start_cycle}} &rarr; ${{hit.end_cycle}}</strong> (${{hit.duration}} cyc)</div>
                    <div>Ticks: ${{hit.start_tick}} &rarr; ${{hit.end_tick}} ps</div>
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
    print(f"Interactive SALAM Visualizer successfully exported to: {output_html_path}")


def main():
    if len(sys.argv) > 1:
        trace_path = sys.argv[1]
    else:
        # Default to the verified gemm_run output
        default_wsl = Path("/home/jslycord/gem5-SALAM-dev/BM_ARM_OUT/gemm_run/observability/fu-scheduling-system.gemm_clstr.gemm.invocation-1.json")
        default_win = Path(r"\\wsl.localhost\gem5-salam-prebuilt\home\jslycord\gem5-SALAM-dev\BM_ARM_OUT\gemm_run\observability\fu-scheduling-system.gemm_clstr.gemm.invocation-1.json")
        if default_wsl.exists():
            trace_path = str(default_wsl)
        elif default_win.exists():
            trace_path = str(default_win)
        else:
            print("Error: Could not find default observability file. Please provide path.")
            sys.exit(1)

    output_path = sys.argv[2] if len(sys.argv) > 2 else "salam_trace_dashboard.html"

    print(f"Parsing SALAM execution trace: {trace_path}")
    trace_data = parse_salam_trace(trace_path)
    print(f"Extracted {len(trace_data['spans'])} instruction execution spans across {trace_data['max_cycle']} cycles.")
    generate_html(trace_data, output_path)

if __name__ == "__main__":
    main()
