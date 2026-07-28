"""Command line entry point.

Shape mirrors slurmwatch: bare invocation opens the dashboard, an argument
targets one thing, and every view is also reachable as plain text for pipes.
"""

from __future__ import annotations

import argparse
import getpass
import json
import re
import sys

from . import report
from ._version import __version__
from .diagnose import diagnose
from .index import History, filter_jobs
from .logs import load_for
from .model import severity_rank
from .nodes import expand_nodelist, note_for_node
from .sacct import Sacct, SacctError, live_job_ids

EPILOG = """\
examples:
  slurmpast                        dashboard over the last 7 days
  slurmpast -S now-30days         ... over the last 30 days
  slurmpast 51170455               post-mortem for one job
  slurmpast --failed --plain       everything that died, as text
  slurmpast --patterns             what keeps failing, across runs
  slurmpast --nodes                which nodes eat your jobs
  slurmpast 51170455 --json        machine readable

`sp` is a short alias for the same entry point.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slurmpast",
        description="Why did your Slurm jobs fail? A post-mortem for finished jobs.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("job_ids", nargs="*", help="job ids to examine")
    parser.add_argument("-u", "--user", default=None, help="user to query (default: you)")
    parser.add_argument("-S", "--since", default="now-7days",
                        help="start of the window, sacct syntax (default: now-7days). "
                             "'-7days' is accepted and rewritten for you")
    parser.add_argument("-E", "--until", default=None, help="end of the window")
    parser.add_argument("-p", "--partition", default=None, help="restrict to a partition")
    parser.add_argument("--failed", action="store_true", help="only jobs that failed")
    parser.add_argument("-n", "--limit", type=int, default=25, help="rows in plain output")

    parser.add_argument("--plain", action="store_true", help="text output, no dashboard")
    parser.add_argument("--overview", action="store_true", help="workload rollup as text")
    parser.add_argument("--patterns", action="store_true", help="cross-run patterns as text")
    parser.add_argument("--nodes", action="store_true", help="node reliability as text")
    parser.add_argument("--metric", choices=["failure", "hang"], default="hang",
                        help="what --nodes measures (default: hang)")
    parser.add_argument("--all-workloads", action="store_true",
                        help="skip the workload control in --nodes (confounded)")
    parser.add_argument("--sort", default="cost",
                        choices=["cost", "failures", "rate", "recent", "runs", "name"],
                        help="workload ordering (default: cost)")

    parser.add_argument("--log-dir", action="append", default=[],
                        help="extra directory to search for job logs")
    parser.add_argument("--no-logs", action="store_true", help="do not read job logs")
    parser.add_argument("--steps", action="store_true", help="per-step accounting")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--demo", action="store_true",
                        help="synthetic history — try it without Slurm, and drive the demo tape")
    parser.add_argument("--ascii", action="store_true", help="ASCII glyphs instead of Unicode")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colour")
    parser.add_argument("--version", action="version", version="slurmpast " + __version__)
    return parser


_VALUE_OPTS = ("-S", "--since", "-E", "--until", "-u", "--user", "-p", "--partition")

# sacct's relative time syntax is `now-7days`. A bare `-7days` is REJECTED
# outright ("Invalid time specification"), but it is the obvious thing to type
# and what this tool's own help used to advertise -- so accept it and rewrite.
_RELATIVE_SPEC = re.compile(r"^-\s*\d+\s*(second|minute|hour|day|week|month)s?$", re.IGNORECASE)


def normalize_time_spec(value):
    """``-7days`` -> ``now-7days``. Anything sacct already understands is left alone."""
    if not value:
        return value
    text = value.strip()
    if _RELATIVE_SPEC.match(text):
        return "now" + text.replace(" ", "")
    return value


def _glue_negative_values(argv):
    """Let ``-S -7days`` work.

    sacct's own relative-time syntax starts with a dash, so that is what people
    type; argparse would treat it as an unknown option and exit 2 on the most
    natural spelling of the most common flag.
    """
    out, index = [], 0
    while index < len(argv):
        token = argv[index]
        if token in _VALUE_OPTS and index + 1 < len(argv):
            value = argv[index + 1]
            if value.startswith("-") and not value.startswith("--"):
                out.append("%s=%s" % (token, value))
                index += 2
                continue
        out.append(token)
        index += 1
    return out


def _mark_open_records(jobs):
    """Reconcile anything unfinished against squeue.

    sacct reports State=RUNNING with End=Unknown for jobs that died long ago;
    its Elapsed is then now-minus-start. One such record read as 62 days and was
    65% of a GPU-hour total. Both a live job and a dead-but-open record have an
    unusable elapsed, so both get flagged.
    """
    if not any(j.base_state == "RUNNING" or j.open_ended for j in jobs):
        return jobs
    if live_job_ids() is None:
        return jobs  # cannot tell -- do not guess
    return [
        j._replace(open_ended=True) if (j.base_state == "RUNNING" or j.open_ended) else j
        for j in jobs
    ]


def _load(args, sacct):
    if getattr(args, "demo", False):
        # Clearly synthetic; see demo.py. Never mixed with real records.
        from .demo import history

        return history()
    if args.job_ids:
        jobs = sacct.jobs(args.job_ids)
        if not jobs:
            raise SacctError("no accounting records for: %s" % ", ".join(args.job_ids))
        return _mark_open_records(jobs)

    user = args.user or getpass.getuser()
    states = ["FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL"] if args.failed else None
    jobs = sacct.history(user=user, since=args.since, until=args.until,
                         states=states, partition=args.partition)
    if not jobs:
        raise SacctError("no jobs for %s since %s%s"
                         % (user, args.since, " matching --failed" if args.failed else ""))
    return _mark_open_records(jobs)


def _logs_for(job, args):
    if args.no_logs:
        return None, None
    return load_for(job, extra_dirs=args.log_dir)


def _node_note(job, history):
    if history is None or len(history) <= 20:
        return ""
    nodes = expand_nodelist(job.node_list)
    if not nodes:
        return ""
    return note_for_node(history.usable_jobs, nodes[0], workload=job.name)


def _job_json(job, log_path, verdict):
    """Every extracted measurement, machine-readable.

    Deliberately exhaustive: if the tool read it, this emits it, so downstream
    analysis never has to re-run sacct with a wider --format. Values that could
    not be read are ``null``, never 0.
    """
    return {
        "identity": {
            "job_id": job.job_id, "job_id_raw": job.job_id_raw, "name": job.name,
            "user": job.user, "uid": job.uid, "group": job.group,
            "account": job.account, "cluster": job.cluster, "partition": job.partition,
            "qos": job.qos, "assoc_id": job.assoc_id, "wckey": job.wckey,
            "work_dir": job.work_dir, "reservation": job.reservation,
        },
        "outcome": {
            "state": job.base_state, "state_raw": job.state,
            "exit_code": job.exit_code, "signal": job.signal,
            "derived_exit_code": job.derived_exit_code, "reason": job.reason,
            "failed": job.failed, "completed": job.completed, "cancelled": job.cancelled,
            "open_ended_record": job.open_ended,
        },
        "timing": {
            "submit": job.submit, "eligible": job.eligible,
            "start": job.start, "end": job.end,
            "elapsed_seconds": job.elapsed, "timelimit_seconds": job.timelimit,
            "walltime_used": job.walltime_used,
            "queue_wait_seconds": job.queue_wait, "suspended_seconds": job.suspended,
            "scheduled_by": job.scheduled_by, "flags": job.flags, "priority": job.priority,
        },
        "shape": {
            "nodes": job.node_count, "node_list": job.node_list,
            "cpus": job.cpu_count, "tasks": job.task_count, "gpus": job.gpu_count,
            "req_cpus": job.req_cpus, "req_nodes": job.req_nodes,
            "alloc_tres": job.alloc_tres, "req_tres": job.req_tres,
            "constraints": job.constraints,
        },
        "cpu": {
            "total_seconds": job.total_cpu,
            "user_seconds": job.user_cpu,
            "system_seconds": job.system_cpu,
            "system_fraction": job.system_cpu_fraction,
            "allocated_core_seconds": job.cpu_time,
            "utilization": job.cpu_utilization,
            "frequency": job.cpu_freq or None,
            "straggler_spread": job.straggler_spread,
            "slowest_task_node": job.slowest_task[0] or None,
            "slowest_task_id": job.slowest_task[1] or None,
            "core_hours": job.core_hours,
        },
        "memory": {
            "limit_bytes": job.mem_limit_bytes,
            "req_mem_raw": job.req_mem_raw,
            "peak_bytes": job.max_rss,
            "peak_node": job.max_rss_node or None,
            "peak_task": job.max_rss_task or None,
            "average_bytes": job.ave_rss,
            "task_imbalance": job.rss_task_imbalance,
            "step_spread": job.rss_step_spread,
            "utilization": job.mem_utilization,
            "virtual_bytes": job.max_vmsize,
            "virtual_to_resident": job.vmsize_to_rss,
            "page_faults": job.max_pages,
            # MaxRSS sums RSS across the process tree and can exceed the cgroup
            # limit; when it does, it is not a working set and must not be used
            # to size --mem.
            "peak_trustworthy": not (
                job.mem_limit_bytes and job.max_rss and job.max_rss > job.mem_limit_bytes
            ),
        },
        "filesystem": {
            "read_bytes": job.read_bytes,
            "write_bytes": job.write_bytes,
            "total_bytes": job.io_bytes,
            "rate_bytes_per_second": job.io_rate,
        },
        "gpu": {
            "count": job.gpu_count,
            "gpu_hours": job.gpu_hours,
            # gres/gpuutil is absent from AccountingStorageTRES on this cluster.
            "utilization": None,
        },
        "energy_joules": job.energy_joules,
        "log": log_path,
        "steps": [
            {
                "step_id": s.step_id, "state": s.state,
                "exit_code": s.exit_code, "signal": s.signal,
                "elapsed_seconds": s.elapsed,
                "total_cpu_seconds": s.total_cpu,
                "user_cpu_seconds": s.user_cpu,
                "system_cpu_seconds": s.system_cpu,
                "ave_cpu_seconds": s.ave_cpu,
                "min_cpu_seconds": s.min_cpu,
                "min_cpu_node": s.min_cpu_node or None,
                "min_cpu_task": s.min_cpu_task or None,
                "cpu_frequency": s.ave_cpu_freq or None,
                "max_rss_bytes": s.max_rss, "max_rss_node": s.max_rss_node or None,
                "max_rss_task": s.max_rss_task or None, "ave_rss_bytes": s.ave_rss,
                "max_vmsize_bytes": s.max_vmsize,
                "max_pages": s.max_pages,
                "read_bytes": s.read_bytes, "write_bytes": s.write_bytes,
                "ntasks": s.ntasks, "nnodes": s.nnodes, "node_list": s.node_list or None,
            }
            for s in job.steps
        ],
        "findings": [
            {"severity": f.severity, "code": f.code, "title": f.title,
             "evidence": f.evidence, "action": f.action}
            for f in sorted(verdict.findings, key=lambda f: severity_rank(f.severity))
        ],
    }


def main(argv=None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(_glue_negative_values(raw))
    args.since = normalize_time_spec(args.since)
    args.until = normalize_time_spec(args.until)
    style = report.Style(enabled=False if args.no_color else None)
    sacct = Sacct()

    wants_text = (
        args.plain or args.json or args.overview or args.patterns or args.nodes or args.job_ids
    )

    if not wants_text:
        # Dashboard. The loader runs inside the app's worker thread so the
        # window paints before the query returns.
        from . import tui

        window = (
            "SYNTHETIC DEMO DATA"
            if args.demo
            else "%s → %s" % (args.since, args.until or "now")
        )
        return tui.run(
            lambda: _load(args, sacct),
            window=window,
            ascii_mode=args.ascii,
            no_logs=args.no_logs,
            log_dirs=args.log_dir,
        )

    try:
        jobs = _load(args, sacct)
    except SacctError as exc:
        sys.stderr.write("slurmpast: %s\n" % exc)
        return 2

    history = History(jobs, window=args.since)

    if args.nodes:
        if args.json:
            from .nodes import dominant_workload, node_table

            workload = None if args.all_workloads else dominant_workload(history.usable_jobs)
            print(json.dumps(
                {"slurmpast": __version__,
                 "nodes": node_table(history.usable_jobs, workload=workload, metric=args.metric)},
                indent=2))
        else:
            print(report.render_nodes(history, metric=args.metric,
                                      controlled=not args.all_workloads, style=style))
        return 0

    if args.patterns:
        if args.json:
            print(json.dumps(
                {"slurmpast": __version__, "summary": history.stats,
                 "findings": [f._asdict() for f in history.patterns]}, indent=2))
        else:
            print(report.render_patterns(history, style=style))
        return 0

    if args.overview:
        if args.json:
            print(json.dumps(
                {"slurmpast": __version__, "summary": history.stats,
                 "workloads": [
                     {"name": g.name, "partition": g.partition, "runs": g.total,
                      "completed": g.completed, "failed": g.failed, "cancelled": g.cancelled,
                      "noop": g.noop, "gpu_hours": g.gpu_hours, "core_hours": g.core_hours,
                      "severity": g.severity, "last_seen": g.last_seen}
                     for g in history.groups]}, indent=2))
        else:
            print(report.render_overview(history, style=style, limit=args.limit, sort=args.sort))
        return 0

    # Per-job. Explicit ids get full detail; a bare --plain/--failed gets a list
    # plus the overview, because 6,574 full post-mortems is not an answer.
    if args.job_ids:
        targets = jobs
    else:
        targets = filter_jobs(history.usable_jobs, "failed" if args.failed else "problem")
        targets.sort(key=lambda j: (j.start or j.submit or "", j.job_id), reverse=True)
        targets = targets[: args.limit]

    if args.json:
        payload = []
        for job in targets:
            log_path, log_text = _logs_for(job, args)
            verdict = diagnose(job, log_text=log_text, node_note=_node_note(job, history))
            payload.append(_job_json(job, log_path, verdict))
        print(json.dumps({"slurmpast": __version__, "summary": history.stats, "jobs": payload},
                         indent=2, default=str))
        return 0

    worst_critical = False
    if args.job_ids:
        for job in targets:
            log_path, log_text = _logs_for(job, args)
            text, verdict = report.render_job(job, log_path=log_path, log_text=log_text,
                                              node_note=_node_note(job, history), style=style,
                                              show_steps=args.steps)
            print(text)
            worst_critical |= any(f.severity == "critical" for f in verdict.findings)
    else:
        print(report.render_overview(history, style=style, limit=args.limit, sort=args.sort))
        if targets:
            print(report.render_list(targets, style=style, limit=args.limit))
            print("")
        print(report.render_patterns(history, style=style))
        worst_critical = any(f.severity == "critical" for f in history.patterns)

    return 1 if worst_critical else 0


if __name__ == "__main__":
    sys.exit(main())
