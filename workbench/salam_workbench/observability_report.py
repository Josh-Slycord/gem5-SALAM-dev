"""Render validated SALAM event measurements without promoting unknown values."""
import html
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .report import _link

GROUPS = (
    (
        "Lifecycle",
        (
            ("Elapsed", "lifecycle.elapsed_ticks", "ticks", False),
            (
                "Interface calls",
                "lifecycle.interface_tick_calls",
                "calls",
                False,
            ),
        ),
    ),
    (
        "Logical memory",
        (
            ("Reads completed", "memory.reads.completed", "requests", False),
            ("Read payload", "memory.reads.completed_bytes", "bytes", False),
            ("Writes completed", "memory.writes.completed", "requests", False),
            ("Write payload", "memory.writes.completed_bytes", "bytes", False),
        ),
    ),
    (
        "Selected commits",
        (
            ("Total", "execution.selected_commits_total", "commits", False),
            ("Compute", "execution.queued_compute_commits", "commits", False),
            ("Read", "execution.memory_read_commits", "commits", False),
            ("Write", "execution.memory_write_commits", "commits", False),
        ),
    ),
    (
        "Queues and latency",
        (
            ("Queue samples", "queues.sample_count", "samples", False),
            ("Reservation peak", "queues.reservation.max", "entries", False),
            ("Reservation mean", "queues.reservation.mean", "entries", True),
            (
                "Mean read latency",
                "memory.reads.latency_ticks.mean",
                "ticks",
                True,
            ),
            (
                "Mean write latency",
                "memory.writes.latency_ticks.mean",
                "ticks",
                True,
            ),
        ),
    ),
)

STYLE = """<style>
.obs-overview{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1.2rem 2rem;margin:1rem 0 1.35rem}
.obs-group{border-top:1px solid #dce2e9;padding-top:.55rem}
.obs-group h5{font-size:.8rem;letter-spacing:.08em;text-transform:uppercase;color:#526172;margin:.2rem 0 .65rem}
.obs-group dl{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.3rem .8rem;margin:0}
.obs-group dt{color:#526172}.obs-group dd{margin:0;text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.obs-group dd small{color:#526172;font-weight:400}
.obs-source{font-size:.9rem;overflow-wrap:anywhere}.obs-record{margin:1.4rem 0 1.8rem}
.obs-record h4{margin-bottom:.35rem}.obs-detail{margin:1rem 0 1.5rem}
.obs-detail summary{cursor:pointer;color:#155c9a;font-weight:600}
@media(max-width:680px){.obs-overview{grid-template-columns:1fr;gap:1rem}}
</style>"""


def _escape(value):
    return html.escape(str(value), quote=True)


def _visible_metric(metric, verified):
    """Return a finite numeric value only from a validated, observed metric."""
    if (
        not verified
        or not isinstance(metric, dict)
        or metric.get("availability") != "observed"
    ):
        return None
    value = metric.get("value")
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _summary_value(metric, verified, rounded=False):
    number = _visible_metric(metric, verified)
    if number is None:
        return "unknown"
    if rounded:
        two_places = number.quantize(Decimal("0.01"))
        if two_places != number:
            return "≈" + format(two_places, ",.2f")
    if number == number.to_integral_value():
        return format(number, ",.0f")
    return format(number, ",f")


def _overview(record, verified):
    metrics = record.get("metrics", {})
    parts = ['<div class="obs-overview">']
    for title, fields in GROUPS:
        parts.append('<div class="obs-group"><h5>' + _escape(title) + "</h5><dl>")
        for label, key, unit, rounded in fields:
            value = _summary_value(metrics.get(key), verified, rounded)
            unit_html = (
                "" if value == "unknown" else " <small>" + _escape(unit) + "</small>"
            )
            parts.append(
                "<dt>"
                + _escape(label)
                + "</dt><dd>"
                + _escape(value)
                + unit_html
                + "</dd>"
            )
        parts.append("</dl></div>")
    parts.append("</div>")
    return "".join(parts)


def _detail_table(record, verified):
    rows = []
    for name, metric in sorted(record.get("metrics", {}).items()):
        metric = metric if isinstance(metric, dict) else {}
        number = _visible_metric(metric, verified)
        value = metric.get("value") if number is not None else "unknown"
        status = metric.get("availability", "unknown") if verified else "unverified"
        if verified:
            scope = metric.get("scope") or metric.get("source_path") or "—"
            derivation = metric.get("derivation") or {}
            if derivation.get("exact_ratio"):
                scope += "; exact ratio " + str(derivation["exact_ratio"])
        else:
            scope = "Unknown until validation"
        rows.append(
            "<tr><th>"
            + _escape(name)
            + "</th><td>"
            + _escape(value)
            + "</td><td>"
            + _escape(metric.get("unit") or "—")
            + "</td><td>"
            + _escape(scope)
            + "</td><td>"
            + _escape(status)
            + "</td></tr>"
        )
    for name, detail in sorted(record.get("unsupported", {}).items()):
        reason = (
            detail.get("reason", "unavailable")
            if verified and isinstance(detail, dict)
            else "unverified"
        )
        rows.append(
            "<tr><th>"
            + _escape(name)
            + "</th><td>unknown</td><td>—</td><td>"
            + _escape(reason)
            + "</td><td>"
            + ("unavailable" if verified else "unverified")
            + "</td></tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="5">No validated metrics available.</td></tr>')
    return (
        '<details class="obs-detail"><summary>All recorded metrics, units, and definitions</summary>'
        '<div class="scroll"><table><thead><tr><th>Metric</th><th>Value</th><th>Unit</th>'
        "<th>Scope or source</th><th>Availability</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div></details>"
    )


def _source_link(run, record, report_dir, verified):
    relative = record.get("artifact_path")
    directory = run.get("directory")
    if not relative or not directory:
        return '<p class="obs-source">Raw observation source: unavailable.</p>'
    try:
        root = Path(directory).resolve()
        target = (root / relative).resolve()
        target.relative_to(root)
    except (TypeError, ValueError):
        return '<p class="obs-source">Raw observation source: unavailable.</p>'
    parts = [
        '<p class="obs-source">',
        _link(target, report_dir, "Raw observation JSON"),
    ]
    provenance = record.get("provenance") or {}
    sha256 = provenance.get("sha256")
    if (
        verified
        and isinstance(sha256, str)
        and len(sha256) == 64
        and all(c in "0123456789abcdef" for c in sha256)
    ):
        parts.append(" · Verified SHA-256 <code>" + _escape(sha256) + "</code>")
    else:
        parts.append(" · Hash or record unverified")
    parts.append("</p>")
    return "".join(parts)


def render_observability(run, report_dir):
    """The caller supplies an independently reloaded run from report.load_run."""
    assessment = run.get("observability", {})
    parts = [STYLE, "<h3>Accelerator event measurements</h3>"]
    if assessment.get("status") == "unavailable":
        return (
            "".join(parts)
            + "<p>Unknown: this saved run declares no versioned observability contract.</p>"
        )
    accepted = (
        run.get("correctness_verified") is True and assessment.get("valid") is True
    )
    parts.append(
        "<p>Validation: <strong>"
        + _escape(assessment.get("status", "unknown"))
        + "</strong>. "
        "These are invocation-local SALAM interface observations. Whole-guest statistics above use "
        "a separate measurement window; these values are not cache hits, all retired instructions, "
        "DMA throughput, or physical hardware performance.</p>"
    )
    if not accepted:
        parts.append(
            "<p>Measurements remain unknown because complete run and observation evidence did not validate.</p>"
        )
    for record in assessment.get("records", []):
        identity = record.get("identity", {})
        name = identity.get("accelerator", "unknown")
        kind = (
            "Top controller"
            if str(name).lower().endswith(".top")
            else "Accelerator function"
        )
        verified = (
            accepted
            and record.get("contract_valid") is True
            and record.get("provenance", {}).get("hash_verified") is True
        )
        parts.append(
            '<div class="obs-record"><h4>'
            + _escape(kind)
            + " · "
            + _escape(name)
            + " / invocation "
            + _escape(identity.get("invocation", "unknown"))
            + "</h4>"
        )
        parts.append(_source_link(run, record, report_dir, verified))
        parts.append(_overview(record, verified))
        parts.append(_detail_table(record, verified))
        parts.append("</div>")
    parts.append(
        "<p>Queue means sample aggregate depth at interface tick entry; they are not time weighted. "
        "Request latency runs from enqueue to final logical completion and includes waiting. "
        "Summary means marked ≈ are rounded for reading; the detail table retains exact reported values. "
        "Power and area require separate characterized models and remain unknown.</p>"
    )
    return "".join(parts)
