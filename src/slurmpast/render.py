"""Rich renderables shared by the TUI and the plain-text output.

Kept apart from ``tui.py`` so the same bar, chip and verdict look identical
whether you are inside the app or piping ``--plain`` into a file.
"""

from __future__ import annotations

import math

from rich.text import Text

from . import theme
from .duration import (
    format_bytes,
    format_cpu_freq,
    format_duration,
    format_percent,
)
from .model import Job, severity_rank


def bar_cells(percent: float | None, width: int) -> int:
    """Whole filled cells for a magnitude bar.

    Rounds rather than floors, and anything that *prints* as >=1% keeps at least
    one lit cell, so the bar never contradicts the number beside it. (A bare
    floor is what made a 4% row draw an empty gauge next to its own "4%".)
    """
    if width <= 0 or percent is None:
        return 0
    if math.isnan(percent):
        return 0
    percent = min(max(percent, 0.0), 100.0)
    cells = min(width, round(percent / 100.0 * width))
    if cells == 0 and percent >= 0.5:
        cells = 1
    return int(cells)


# Partial-cell caps, so a bar lands on its true position instead of snapping to
# the nearest whole cell. Same glyph set slurmwatch uses.
_EIGHTHS = "▏▎▍▌▋▊▉"


def bar(percent: float | None, color: str, width: int = theme.BAR_WIDTH, ascii_mode: bool = False):
    """A magnitude bar, matching slurmwatch's.

    The empty track is a shaded block (``░``) in a faint neutral, NOT a line
    glyph -- ``─`` renders as a string of dashes, which reads as punctuation
    rather than as the unfilled remainder of a gauge.

    The fill is drawn to one-eighth-of-a-cell precision. Two rules keep the bar
    honest against the number printed beside it: the last eighth is withheld
    until the percentage *rounds* to 100, so a visually full bar always means
    100%; and anything that displays as >=1% keeps at least a sliver, so a bar
    never reads empty next to a non-zero figure.

    ``None`` draws an empty track -- never a full or a zero bar.
    """
    if width <= 0:
        return Text()
    if percent is None or math.isnan(percent):
        return Text(("-" if ascii_mode else "░") * width, style=theme.FAINT)

    percent = min(max(percent, 0.0), 100.0)
    text = Text()
    if ascii_mode:
        full = bar_cells(percent, width)
        text.append("#" * full, style=color)
        text.append("-" * (width - full), style=theme.FAINT)
        return text

    eighths = min(width * 8, round(percent / 100.0 * width * 8))
    # Withhold the last eighth until the value rounds to 100 *at the precision we
    # print it* -- labels here carry one decimal, so a full bar beside "99.6%"
    # would contradict itself.
    if eighths >= width * 8 and round(percent, 1) < 100.0:
        eighths = width * 8 - 1
    eighths = 0 if round(percent, 1) < 1.0 else max(1, eighths)
    full, rem = divmod(int(eighths), 8)
    fill = "█" * full + (_EIGHTHS[rem - 1] if rem else "")
    if fill:
        text.append(fill, style=color)
    empty = width - full - (1 if rem else 0)
    if empty > 0:
        text.append("░" * empty, style=theme.FAINT)
    return text


def health_dot(grade: str, ascii_mode: bool = False):
    glyphs = theme.HEALTH_GLYPH_ASCII if ascii_mode else theme.HEALTH_GLYPH
    return Text(glyphs.get(grade, glyphs["none"]), style=theme.HEALTH_COLOR.get(grade, theme.FAINT))


def state_text(state: str, ascii_mode: bool = False):
    grade = theme.STATE_HEALTH.get(state, "none")
    text = Text()
    text.append_text(health_dot(grade, ascii_mode))
    text.append(" ")
    text.append(state or "?", style=theme.HEALTH_COLOR.get(grade, theme.DIM))
    return text


def severity_chip(severity: str):
    grade = theme.SEVERITY_HEALTH.get(severity, "none")
    label = {"critical": "FAIL", "warning": "WARN", "info": "INFO"}.get(severity, "----")
    return Text(label, style="bold %s" % theme.HEALTH_COLOR.get(grade, theme.FAINT))


def job_headline(job: Job, ascii_mode: bool = False):
    """``<state> · <elapsed> · <cpu util>`` -- the three facts that classify a job."""
    text = state_text(job.base_state, ascii_mode)
    text.append("  ")
    text.append(format_duration(job.elapsed), style=theme.DIM)
    text.append("  cpu ", style=theme.FAINT)
    util = job.cpu_utilization
    style = theme.CPU_COLOR
    if util is not None and util < 0.02:
        style = theme.HEALTH_COLOR["crit"]
    text.append(format_percent(util), style=style)
    return text


def finding_lines(finding, width: int = 74) -> list[str]:
    out = [finding.title]
    out.extend("    " + line for line in wrap(finding.evidence, width - 4))
    if finding.action:
        for index, line in enumerate(wrap(finding.action, width - 7)):
            out.append(("    -> " if index == 0 else "       ") + line)
    return out


def wrap(text: str, width: int) -> list[str]:
    """Word wrap that preserves explicit newlines."""
    lines: list[str] = []
    for paragraph in (text or "").split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            if current and len(current) + 1 + len(word) > width:
                lines.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            lines.append(current)
    return lines


def resource_line(label: str, value: str, color: str, percent: float | None, ascii_mode=False):
    text = Text()
    text.append("  %-9s " % label, style=color)
    text.append_text(bar(percent, color, ascii_mode=ascii_mode))
    text.append("  ")
    text.append(value, style=theme.INK)
    return text


def mem_text(job: Job) -> str:
    """Memory ceiling, saying where the figure came from when ReqMem was unusable."""
    limit = job.mem_limit_bytes
    if limit is None:
        return "n/a"
    if job.req_mem_bytes:
        return format_bytes(limit)
    return "%s (AllocTRES; ReqMem was 0n)" % format_bytes(limit)


def sort_findings(findings):
    return sorted(findings, key=lambda f: severity_rank(f.severity))


# --- the full job detail, shared by the dashboard and the plain renderer ----
# One source of truth so the two never drift: both consume these sections.


def _pct_of(value, whole):
    if value is None or not whole:
        return None
    return 100.0 * value / whole


def job_sections(job):
    """Everything known about a finished job, as ``(title, [(label, value, bar)])``.

    ``bar`` is a percentage for rows worth drawing a gauge for, else None. Rows
    whose value could not be read are omitted entirely rather than printed as
    zero -- a fabricated 0 is indistinguishable from a measurement.
    """
    sections = []

    # -- identity ------------------------------------------------------------
    ident = [("name", job.name or "n/a", None)]
    ident.append(
        (
            "account",
            "%s / %s / %s" % (job.partition or "?", job.qos or "?", job.account or "?"),
            None,
        )
    )
    if job.node_list:
        ident.append(
            (
                "nodes",
                "%s  (%d node%s)"
                % (job.node_list, job.node_count, "" if job.node_count == 1 else "s"),
                None,
            )
        )
    if job.constraints:
        ident.append(("constraint", job.constraints, None))
    if job.reservation:
        ident.append(("reservation", job.reservation, None))
    if job.cluster:
        ident.append(("cluster", job.cluster, None))
    if job.work_dir:
        ident.append(("workdir", job.work_dir, None))
    sections.append(("job", ident))

    # -- timing --------------------------------------------------------------
    timing = []
    if job.submit:
        timing.append(("submitted", job.submit, None))
    if job.start:
        timing.append(("started", job.start, None))
    if job.end:
        timing.append(("ended", job.end, None))
    if job.queue_wait is not None:
        timing.append(("queued for", format_duration(job.queue_wait), None))
    timing.append(
        (
            "walltime",
            "%s of %s   (%s)"
            % (
                format_duration(job.elapsed),
                format_duration(job.timelimit),
                format_percent(job.walltime_used),
            ),
            _pct_of(job.walltime_used, 1.0),
        )
    )
    if job.suspended:
        timing.append(("suspended", format_duration(job.suspended), None))
    if job.scheduled_by:
        timing.append(("scheduled by", job.scheduled_by, None))
    if job.priority is not None:
        timing.append(("priority", f"{job.priority:,}", None))
    sections.append(("timing", timing))

    # -- cpu -----------------------------------------------------------------
    cpu = [
        (
            "total",
            "%s of %s allocated   (%s over %s core%s)"
            % (
                format_duration(job.total_cpu),
                format_duration(job.cpu_time),
                format_percent(job.cpu_utilization),
                job.cpu_count or "?",
                "" if job.cpu_count == 1 else "s",
            ),
            _pct_of(job.cpu_utilization, 1.0),
        )
    ]
    if job.user_cpu is not None or job.system_cpu is not None:
        cpu.append(
            (
                "user / system",
                "%s / %s   (kernel %s)"
                % (
                    format_duration(job.user_cpu),
                    format_duration(job.system_cpu),
                    format_percent(job.system_cpu_fraction),
                ),
                _pct_of(job.system_cpu_fraction, 1.0),
            )
        )
    freq_hz = job.cpu_freq_hz
    if freq_hz is not None:
        note = ""
        if freq_hz < 1.5e9:
            note = "   (downclocked)"
        cpu.append(("avg clock", format_cpu_freq(freq_hz) + note, None))
    if job.task_count:
        cpu.append(("tasks", str(job.task_count), None))
    spread = job.straggler_spread
    if spread is not None:
        node, task = job.slowest_task
        where = " (task %s on %s)" % (task or "?", node) if node else ""
        cpu.append(
            (
                "slowest task",
                "%s below average%s" % (format_percent(spread), where),
                _pct_of(spread, 1.0),
            )
        )
    sections.append(("cpu", cpu))

    # -- memory --------------------------------------------------------------
    mem = [("limit", mem_text(job), None)]
    if job.max_rss is not None:
        note = ""
        if job.mem_limit_bytes and job.max_rss > job.mem_limit_bytes:
            note = "   ABOVE THE LIMIT - not a working set"
        mem.append(
            (
                "peak (MaxRSS)",
                "%s   (%s)%s"
                % (format_bytes(job.max_rss), format_percent(job.mem_utilization), note),
                _pct_of(job.mem_utilization, 1.0),
            )
        )
    if job.max_rss_node:
        mem.append(
            (
                "peak on",
                "%s%s"
                % (job.max_rss_node, " task %s" % job.max_rss_task if job.max_rss_task else ""),
                None,
            )
        )
    if job.ave_rss is not None:
        imbalance = job.rss_task_imbalance
        extra = "   (%.1fx the average)" % imbalance if imbalance and imbalance >= 1.5 else ""
        mem.append(("average", "%s%s" % (format_bytes(job.ave_rss), extra), None))
    if job.max_vmsize is not None:
        ratio = job.vmsize_to_rss
        note = "   (%.0fx resident - address space, not memory used)" % ratio if ratio else ""
        mem.append(("virtual", "%s%s" % (format_bytes(job.max_vmsize), note), None))
    if job.max_pages:
        mem.append(("page faults", f"{int(job.max_pages):,}", None))
    sections.append(("memory", mem))

    # -- io ------------------------------------------------------------------
    io = []
    if job.read_bytes is not None:
        io.append(("read", format_bytes(job.read_bytes), None))
    if job.write_bytes is not None:
        io.append(("written", format_bytes(job.write_bytes), None))
    if job.io_rate is not None:
        io.append(("rate", "%s/s sustained" % format_bytes(job.io_rate), None))
    if io:
        sections.append(("filesystem", io))

    # -- gpu -----------------------------------------------------------------
    if job.gpu_count:
        gpu = [
            ("devices", str(job.gpu_count), None),
            ("gpu-hours", "%.1f" % (job.gpu_hours or 0.0), None),
            (
                "utilization",
                "not recorded - gres/gpuutil is absent from this cluster's accounting",
                None,
            ),
        ]
        sections.append(("gpu", gpu))

    # -- outcome -------------------------------------------------------------
    outcome = [("state", job.base_state or "?", None)]
    if job.exit_code is not None:
        text = str(job.exit_code)
        if job.signal:
            text += " (signal %d)" % job.signal
        outcome.append(("exit code", text, None))
    if job.derived_exit_code not in (None, job.exit_code):
        outcome.append(("worst step exit", str(job.derived_exit_code), None))
    if job.reason:
        outcome.append(("reason", job.reason, None))
    if job.energy_joules is not None:
        outcome.append(("energy", "%d J" % job.energy_joules, None))
    if job.comment:
        outcome.append(("comment", job.comment, None))
    sections.append(("outcome", outcome))

    return sections


def stamp_short(iso, with_date=True):
    """``2026-06-27T08:12:50`` -> ``06-27 08:12``, for dense table columns.

    Returns ``""`` for a missing timestamp rather than a placeholder date, so an
    absent value never looks like a real one.
    """
    if not iso:
        return ""
    text = str(iso)
    if "T" not in text:
        return text[:11]
    date, _, clock = text.partition("T")
    hhmm = clock[:5]
    if not with_date:
        return hhmm
    return "%s %s" % (date[5:10], hhmm)


# --- slurmwatch-style resource rows ---------------------------------------

_MARKER = "●"
_MARKER_ASCII = "*"


def resource_rows(job, ascii_mode: bool = False, width: int = 18):
    """The job's resources in slurmwatch's row idiom: ``● LABEL bar value · detail``.

    Deliberately the same shape as the live view. The two tools sit either side of
    one job, and someone who watched it run should recognise the shape of what they
    are reading afterwards. As in slurmwatch the marker is decorative -- it carries
    the resource's identity hue, never a health grade; the bar and the number carry
    the magnitude, and the verdict lives in the findings below.

    A row whose value could not be measured draws an empty track and prints
    ``n/a`` rather than a zero.
    """
    marker = _MARKER_ASCII if ascii_mode else _MARKER
    rows = []

    def row(label, color, fraction, value, detail=""):
        text = Text()
        text.append("  %s " % marker, style=color)
        text.append("%-6s " % label, style=color)
        text.append_text(
            bar(
                None if fraction is None else fraction * 100.0,
                color,
                width=width,
                ascii_mode=ascii_mode,
            )
        )
        text.append("  ")
        text.append("%7s" % value, style=theme.INK)
        if detail:
            text.append("   %s %s" % ("-" if ascii_mode else "·", detail), style=theme.DIM)
        rows.append(text)

    row(
        "TIME",
        theme.ACCENT,
        job.walltime_used,
        format_percent(job.walltime_used),
        "%s of %s" % (format_duration(job.elapsed), format_duration(job.timelimit)),
    )
    row(
        "CPU",
        theme.CPU_COLOR,
        job.cpu_utilization,
        format_percent(job.cpu_utilization),
        "%s of %s over %s cores"
        % (
            format_duration(job.total_cpu),
            format_duration(job.cpu_time),
            job.cpu_count or "?",
        ),
    )
    if job.system_cpu_fraction is not None:
        row(
            "KERNEL",
            theme.MEM_COLOR,
            job.system_cpu_fraction,
            format_percent(job.system_cpu_fraction),
            "%s of %s in the kernel"
            % (format_duration(job.system_cpu), format_duration(job.total_cpu)),
        )
    detail = "%s of %s" % (format_bytes(job.max_rss), mem_text(job))
    if job.max_rss_node:
        detail += ", peak on %s" % job.max_rss_node
    row("MEM", theme.MEM_COLOR, job.mem_utilization, format_percent(job.mem_utilization), detail)
    if job.gpu_count:
        row(
            "GPU",
            theme.GPU_COLOR,
            None,
            "n/a",
            "%d device%s, %.1f GPU-hours - utilization is not recorded by Slurm"
            % (job.gpu_count, "" if job.gpu_count == 1 else "s", job.gpu_hours or 0.0),
        )
    if job.io_bytes:
        row(
            "DISK",
            theme.DISK_COLOR,
            None,
            format_bytes(job.io_rate) + "/s" if job.io_rate else "n/a",
            "read %s, wrote %s" % (format_bytes(job.read_bytes), format_bytes(job.write_bytes)),
        )
    return rows
