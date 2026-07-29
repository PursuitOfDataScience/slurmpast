"""Per-node reliability from your own history.

The signal is real but heavily confounded, and both halves were measured:

* Raw, ``midway3-0385`` shows a 25.5% failure rate against a 16.8% baseline --
  but most of that is 51 ``cot-exp`` timeouts, i.e. a code bug, not the node.
* Holding the workload fixed (``node-evaluation`` only), ``midway3-0385`` hangs
  52.8% of the time (19/36) against ``midway3-0600`` at 5.5% (12/218) -- a 9.6x
  spread on identical work. The signal survives the control.

So this module always controls for workload and always reports a Wilson interval.
A node is only called out when its interval excludes the baseline; otherwise the
honest answer is "not enough evidence", which is what it says.
"""

import math
import re

from .diagnose import looks_like_noop
from .patterns import usable

MIN_SAMPLES = 10
Z = 1.96  # 95%

# Tolerates a suffix after the bracket (``node[1-2]-ib``), which some
# site naming schemes produce; without it the whole string was treated as
# a single node name.
_RANGE = re.compile(r"^([A-Za-z0-9\-]*?)\[(.+?)\](.*)$")


def expand_nodelist(nodelist):
    """``midway3-[0277-0279,0281]`` -> the individual node names.

    Slurm compresses NodeList, so counting occurrences of the raw string
    undercounts multi-node jobs and mis-attributes their failures.
    """
    if not nodelist or nodelist.startswith("None"):
        return []
    out = []
    for chunk in _split_top_level(nodelist):
        match = _RANGE.match(chunk)
        if not match:
            out.append(chunk)
            continue
        prefix, body, suffix = match.group(1), match.group(2), match.group(3)
        for part in body.split(","):
            part = part.strip()
            if "-" in part:
                low, _, high = part.partition("-")
                width = len(low)
                try:
                    for value in range(int(low), int(high) + 1):
                        out.append("%s%0*d%s" % (prefix, width, value, suffix))
                except ValueError:
                    out.append(prefix + part + suffix)
            elif part:
                out.append(prefix + part + suffix)
    return out


def _split_top_level(text):
    """Split on commas that are not inside brackets."""
    parts, depth, current = [], 0, ""
    for ch in text:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "," and depth == 0:
            if current:
                parts.append(current)
            current = ""
        else:
            current += ch
    if current:
        parts.append(current)
    return parts


def wilson_interval(successes, trials, z=Z):
    """Wilson score interval for a proportion. Returns (low, high)."""
    if trials <= 0:
        return (0.0, 1.0)
    phat = successes / float(trials)
    denom = 1.0 + z * z / trials
    centre = (phat + z * z / (2.0 * trials)) / denom
    margin = z * math.sqrt(phat * (1.0 - phat) / trials + z * z / (4.0 * trials * trials)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def _bad(job):
    """Outcomes attributable to the run failing. Cancellations excluded -- ambiguous."""
    return job.failed


def node_table(jobs, workload=None, metric="failure", min_samples=MIN_SAMPLES):
    """Per-node rates.

    ``workload`` restricts to one group key's job name, which is how the
    confound is controlled. ``metric`` is ``failure`` or ``hang``.
    """
    records = usable(jobs)
    if workload:
        records = [j for j in records if j.name == workload]

    predicate = looks_like_noop if metric == "hang" else _bad

    totals, hits = {}, {}
    for job in records:
        flagged = predicate(job)
        for node in expand_nodelist(job.node_list):
            totals[node] = totals.get(node, 0) + 1
            if flagged:
                hits[node] = hits.get(node, 0) + 1

    total_trials = sum(totals.values())
    total_hits = sum(hits.values())
    baseline = (total_hits / float(total_trials)) if total_trials else None

    rows = []
    for node, trials in totals.items():
        if trials < min_samples:
            continue
        bad = hits.get(node, 0)
        low, high = wilson_interval(bad, trials)
        if baseline is None:
            verdict = "unknown"
        elif low > baseline:
            verdict = "worse"
        elif high < baseline:
            verdict = "better"
        else:
            verdict = "inconclusive"
        rows.append(
            {
                "node": node,
                "bad": bad,
                "trials": trials,
                "rate": bad / float(trials),
                "ci_low": low,
                "ci_high": high,
                "verdict": verdict,
            }
        )
    rows.sort(key=lambda r: -r["rate"])
    return {
        "rows": rows,
        "baseline": baseline,
        "trials": total_trials,
        "hits": total_hits,
        "metric": metric,
        "workload": workload,
        "skipped_nodes": sum(1 for n, t in totals.items() if t < min_samples),
    }


def dominant_workload(jobs, metric=None):
    """The job name to hold fixed when comparing nodes.

    Not simply the most common name. Controlling on a workload that never
    exhibits the metric leaves the table structurally unable to say anything: on
    a real 30-day history the most-common workload was 200 runs of ``sw-arr100``
    with **zero** hangs, so every row read ``0/10, 0.0%, inconclusive`` against a
    0.0% baseline -- eight rows of nothing, which is what made this screen read as
    useless. Controlling instead on a workload that does hang (``test``, 19 in 75)
    gives a 25.7% baseline and an actual verdict.

    This picks a sample where the question is answerable rather than selecting on
    the outcome: the confound being held fixed is still the workload, and the
    comparison is still strictly between nodes inside it.

    ``metric`` mirrors :func:`node_table`. Without it the choice is by run count,
    which is all that can be said when no metric is named.
    """
    records = usable(jobs)
    if not records:
        return None
    predicate = None
    if metric == "hang":
        predicate = looks_like_noop
    elif metric:
        predicate = _bad

    counts, events = {}, {}
    for job in records:
        counts[job.name] = counts.get(job.name, 0) + 1
        if predicate is not None and predicate(job):
            events[job.name] = events.get(job.name, 0) + 1
    if events:
        # Most events first, then most runs -- both feed the statistical power to
        # tell one node apart from another.
        return max(events, key=lambda name: (events[name], counts[name]))
    return max(counts.items(), key=lambda kv: kv[1])[0]


def suggest_exclude(table, limit=8):
    """Nodes whose interval is entirely above the baseline."""
    bad = [r["node"] for r in table["rows"] if r["verdict"] == "worse"]
    return bad[:limit]


def compress_nodelist(nodes):
    """Inverse of expand_nodelist, enough for a readable ``--exclude=``."""
    if not nodes:
        return ""
    groups = {}
    plain = []
    for node in sorted(set(nodes)):
        match = re.match(r"^(.*?)(\d+)$", node)
        if not match:
            plain.append(node)
            continue
        prefix, digits = match.group(1), match.group(2)
        groups.setdefault((prefix, len(digits)), []).append(int(digits))

    parts = list(plain)
    for (prefix, width), values in sorted(groups.items()):
        values.sort()
        runs, start, prev = [], values[0], values[0]
        for value in values[1:]:
            if value == prev + 1:
                prev = value
                continue
            runs.append((start, prev))
            start = prev = value
        runs.append((start, prev))
        rendered = []
        for low, high in runs:
            if low == high:
                rendered.append("%0*d" % (width, low))
            else:
                rendered.append("%0*d-%0*d" % (width, low, width, high))
        if len(rendered) == 1 and runs[0][0] == runs[0][1]:
            parts.append("%s%s" % (prefix, rendered[0]))
        else:
            parts.append("%s[%s]" % (prefix, ",".join(rendered)))
    return ",".join(parts)


def note_for_node(jobs, node, workload=None):
    """One-line reliability note for a node, or "" when evidence is thin."""
    if not node:
        return ""
    table = node_table(jobs, workload=workload, metric="failure")
    baseline = table["baseline"]
    for row in table["rows"]:
        if row["node"] != node:
            continue
        if row["verdict"] != "worse" or baseline is None:
            return ""
        return (
            "%s failed %d of your %d jobs there (%.1f%%, 95%% CI %.1f-%.1f%%) against a "
            "%.1f%% baseline%s."
            % (
                node,
                row["bad"],
                row["trials"],
                100 * row["rate"],
                100 * row["ci_low"],
                100 * row["ci_high"],
                100 * baseline,
                (" for %s" % workload) if workload else "",
            )
        )
    return ""
