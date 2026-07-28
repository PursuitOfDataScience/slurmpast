"""Plain-text output, for pipes, CI and terminals where a TUI is wrong.

Everything the dashboard shows is reachable here, because a post-mortem you
cannot paste into a ticket is half a tool.
"""

from __future__ import annotations

import os
import sys

from .diagnose import diagnose
from .duration import format_bytes, format_duration, format_percent
from .index import History, sort_groups
from .model import severity_rank
from .nodes import compress_nodelist, dominant_workload, node_table, suggest_exclude
from .render import job_sections, stamp_short, wrap
from .sizing import recommend, sbatch_lines

_CODES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "yellow": "\033[33m",
    "green": "\033[32m",
    "cyan": "\033[36m",
    "grey": "\033[90m",
}
_SEV = {"critical": ("red", "FAIL"), "warning": ("yellow", "WARN"), "info": ("cyan", "INFO")}
_STATE_COLOR = {
    "COMPLETED": "green",
    "FAILED": "red",
    "TIMEOUT": "red",
    "OUT_OF_MEMORY": "red",
    "NODE_FAIL": "red",
    "CANCELLED": "yellow",
}


class Style:
    def __init__(self, enabled=None, stream=None):
        stream = stream or sys.stdout
        if enabled is None:
            enabled = (
                hasattr(stream, "isatty") and stream.isatty() and not os.environ.get("NO_COLOR")
            )
        self.enabled = bool(enabled)

    def __call__(self, text, *names):
        if not self.enabled or not names:
            return text
        return "".join(_CODES.get(n, "") for n in names) + text + _CODES["reset"]


def render_job(job, log_path=None, log_text=None, node_note="", style=None, show_steps=False):
    style = style or Style()
    verdict = diagnose(job, log_text=log_text, node_note=node_note)
    out = []
    state = job.base_state or "?"
    out.append(
        "%s %s  %s"
        % (
            style("job", "grey"),
            style(job.job_id, "bold"),
            style(state, _STATE_COLOR.get(state, "bold")),
        )
    )
    for title, rows in job_sections(job):
        out.append("")
        out.append(style("  " + title, "bold"))
        for label, value, _bar in rows:
            flag = "red" if "ABOVE THE LIMIT" in value else None
            out.append("    %-16s %s" % (label, style(value, flag) if flag else value))

    if show_steps and job.steps:
        out.append("")
        out.append(style("  steps", "bold"))
        out.append(
            "    %-18s %-11s %8s %9s %9s %9s %9s"
            % ("STEP", "STATE", "ELAPSED", "CPU", "MAXRSS", "READ", "WROTE")
        )
        for step in job.steps:
            out.append(
                "    %-18s %-11s %8s %9s %9s %9s %9s"
                % (
                    step.step_id,
                    (step.state or "").split()[0][:11],
                    format_duration(step.elapsed),
                    format_duration(step.total_cpu),
                    format_bytes(step.max_rss),
                    format_bytes(step.read_bytes),
                    format_bytes(step.write_bytes),
                )
            )

    out.append("")
    out.append(
        "  %s %s" % (style("log", "grey"), log_path or style("not found (pass --log-dir)", "grey"))
    )
    out.append("")
    findings = sorted(verdict.findings, key=lambda f: severity_rank(f.severity))
    if not findings:
        out.append(style("  nothing to flag.", "green"))
    else:
        out.append(style("  findings", "bold"))
        for finding in findings:
            colour, tag = _SEV.get(finding.severity, ("bold", "----"))
            out.append("")
            out.append("  %s %s" % (style("[" + tag + "]", colour), style(finding.title, "bold")))
            for line in wrap(finding.evidence, 72):
                out.append("        " + line)
            for index, line in enumerate(wrap(finding.action, 72)):
                out.append("        %s%s" % (style("-> " if index == 0 else "   ", "grey"), line))
    out.append("")
    return "\n".join(out), verdict


def render_overview(history: History, style=None, limit=25, sort="cost"):
    style = style or Style()
    stats = history.stats
    out = [
        style("workloads — ranked by resource use (GPU-hours, else core-hours)", "bold"),
        style("-" * 96, "grey"),
    ]
    if history.window:
        # The window is the commonest explanation for "why are runs missing?",
        # so it belongs on screen rather than in the reader's memory.
        out.append("  window %s" % style(history.window, "bold"))
    line = "  %d jobs · %s completed" % (
        stats["jobs"],
        format_percent(stats["completion_rate"]),
    )
    if stats["gpu_hours_noop"] and stats["gpu_hours_total"]:
        # The total earns its place as the denominator for the idle figure, not as
        # a standalone fact.
        line += " · " + style(
            "%.0f of %.0f GPU-hours never computed"
            % (stats["gpu_hours_noop"], stats["gpu_hours_total"]),
            "yellow",
        )
    elif stats["gpu_hours_total"]:
        line += " · %.0f GPU-hours" % stats["gpu_hours_total"]
    out.append(line)
    if stats["excluded_open_records"]:
        out.append(
            style(
                "  %d record(s) excluded as unterminated (elapsed would be now minus start)"
                % stats["excluded_open_records"],
                "grey",
            )
        )
    out.append("")
    out.append(
        "  %-4s %-24s %-9s %6s %8s %7s %11s  %-11s %s"
        % (
            "#",
            "WORKLOAD",
            "PARTITION",
            "RUNS",
            "FAILED",
            "NEVER RAN",
            "USED",
            "LAST RUN",
            "VARIANTS",
        )
    )
    groups = sort_groups(history.groups, sort)
    for index, group in enumerate(groups[:limit], start=1):
        burned = (
            "%.0f gpu-h" % group.gpu_hours
            if group.gpu_hours >= 1
            else "%.0f core-h" % group.core_hours
        )
        colour = {"crit": "red", "warn": "yellow"}.get(group.severity)
        label = group.name[:24]
        name = style(label, colour) if colour else label
        variants = "%d names" % group.distinct_names if group.distinct_names > 1 else ""
        out.append(
            "  %-4d %-24s %-9s %6d %8s %7s %11s  %-11s %s"
            % (
                index,
                name,
                group.partition[:9],
                group.total,
                format_percent(group.failure_rate),
                group.noop or "-",
                burned,
                (group.last_seen or "")[:10],
                style(variants, "grey"),
            )
        )
    tail = history.tail_summary(limit)
    if tail:
        out.append(style("  … " + tail, "grey"))
    out.append("")
    return "\n".join(out)


def render_list(jobs, style=None, limit=40):
    style = style or Style()
    # STARTED/ENDED matter here for the same reason they do in the dashboard: a
    # workload with hundreds of identically-named runs is unnavigable without them.
    out = [
        "%-12s %-18s %-12s %-11s %-11s %9s %9s %7s %4s"
        % ("JOBID", "NAME", "STATE", "STARTED", "ENDED", "ELAPSED", "CPU", "UTIL", "GPU"),
        style("-" * 106, "grey"),
    ]
    for job in jobs[:limit]:
        state = job.base_state
        out.append(
            "%-12s %-18s %-12s %-11s %-11s %9s %9s %7s %4s"
            % (
                job.job_id[:12],
                (job.name or "")[:18],
                style("%-12s" % state[:12], _STATE_COLOR.get(state, "bold")),
                stamp_short(job.start) or "-",
                stamp_short(job.end) or "-",
                format_duration(job.elapsed),
                format_duration(job.total_cpu),
                format_percent(job.cpu_utilization),
                job.gpu_count or "-",
            )
        )
    if len(jobs) > limit:
        out.append(style("  … %d more (raise --limit)" % (len(jobs) - limit), "grey"))
    return "\n".join(out)


def render_patterns(history: History, style=None):
    style = style or Style()
    out = [style("cross-run patterns", "bold"), style("-" * 78, "grey"), ""]
    findings = history.patterns
    if not findings:
        out.append(style("  no cross-run pattern met its evidence threshold.", "green"))
        out.append("")
        return "\n".join(out)
    for finding in sorted(findings, key=lambda f: severity_rank(f.severity)):
        colour, tag = _SEV.get(finding.severity, ("bold", "----"))
        out.append("  %s %s" % (style("[" + tag + "]", colour), style(finding.title, "bold")))
        for line in wrap(finding.evidence, 72):
            out.append("        " + line)
        for index, line in enumerate(wrap(finding.action, 72)):
            out.append("        %s%s" % (style("-> " if index == 0 else "   ", "grey"), line))
        out.append("")
    return "\n".join(out)


def render_nodes(history: History, metric="hang", controlled=True, style=None):
    style = style or Style()
    jobs = history.usable_jobs
    workload = dominant_workload(jobs) if controlled else None
    table = node_table(jobs, workload=workload, metric=metric)
    out = [style("node reliability (%s rate)" % metric, "bold"), style("-" * 78, "grey")]
    if workload:
        out.append(
            "  controlled for workload: only %s counted %s"
            % (style(workload, "bold"), style("(placement is not random)", "grey"))
        )
    else:
        out.append(
            style(
                "  UNCONTROLLED — mixes workloads; a node that hosted one bad campaign "
                "will look cursed",
                "yellow",
            )
        )
    out.append(
        "  baseline %s over %d placements%s"
        % (
            format_percent(table["baseline"]),
            table["trials"],
            "; %d nodes below threshold omitted" % table["skipped_nodes"]
            if table["skipped_nodes"]
            else "",
        )
    )
    out.append("")
    out.append("  %-16s %9s %10s %20s  %s" % ("NODE", "N", "RATE", "95% CI", "VERDICT"))
    for row in table["rows"]:
        colour = {"worse": "red", "better": "green"}.get(row["verdict"])
        out.append(
            "  %-16s %9s %10s %20s  %s"
            % (
                row["node"],
                "%d/%d" % (row["bad"], row["trials"]),
                "%.1f%%" % (100 * row["rate"]),
                "%.1f - %.1f%%" % (100 * row["ci_low"], 100 * row["ci_high"]),
                style(row["verdict"], colour) if colour else row["verdict"],
            )
        )
    out.append("")
    excl = compress_nodelist(suggest_exclude(table))
    if excl:
        out.append("  intervals entirely above baseline:")
        out.append("    %s" % style("#SBATCH --exclude=" + excl, "bold"))
        out.append(
            style(
                "    not applied for you — excluding nodes trades availability for reliability.",
                "grey",
            )
        )
    else:
        out.append(style("  no node's interval clears the baseline; nothing to exclude.", "grey"))
    out.append("")
    return "\n".join(out)


def render_sizing(history, style=None, limit=12):
    """Per-workload guidance for the next submission."""
    style = style or Style()
    out = [
        style("what to request next time", "bold"),
        style("-" * 92, "grey"),
        style(
            "  From how each workload actually ran. Over-requesting narrows which nodes "
            "can host it;\n  under-requesting kills the run.",
            "grey",
        ),
        "",
    ]
    shown = 0
    for group in history.groups:
        advice = recommend(group.jobs)
        if not advice:
            continue
        actionable = [a for a in advice if a.actionable]
        if not actionable:
            continue
        shown += 1
        if shown > limit:
            break
        out.append(
            "  %s  %s"
            % (
                style(group.name, "bold"),
                style("%s · %d runs" % (group.partition, group.total), "grey"),
            )
        )
        for a in advice:
            if a.verdict == "keep":
                out.append("    %-17s %s" % (a.flag, style("already about right", "green")))
                continue
            if a.verdict == "unknown":
                out.append("    %-17s %s — %s" % (a.flag, style("no advice", "grey"), a.basis))
                continue
            arrow = "raise to" if a.verdict == "raise" else "lower to"
            out.append(
                "    %-17s %s %s   %s"
                % (
                    a.flag,
                    arrow,
                    style(a.suggestion, "bold"),
                    style("(requested %s, observed %s)" % (a.requested, a.observed), "grey"),
                )
            )
            for line in wrap(a.basis, 84):
                out.append("        " + style(line, "grey"))
            if a.caution:
                for index, line in enumerate(wrap(a.caution, 82)):
                    out.append(
                        "        %s%s" % ("! " if index == 0 else "  ", style(line, "yellow"))
                    )
        for line in sbatch_lines(advice):
            out.append("    " + style(line, "bold"))
        out.append("")
    if not shown:
        out.append(
            style("  every workload is already about right, or lacks the runs to say.", "green")
        )
        out.append("")
    return "\n".join(out)
