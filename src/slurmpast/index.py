"""The scale layer: turning thousands of finished jobs into something navigable.

Measured on a real seven-month history: ``sacct`` returns **21,400 rows in
1.26 s** and they parse into 6,574 jobs. Two consequences drive every decision
here.

**No disk cache.** A 1.26 s cold query does not justify a persistent store, and
a store buys staleness bugs, a schema to version, and an invalidation policy to
get wrong. One query, everything else in memory.

**A flat list of 6,574 jobs is not a user interface.** It is the same failure as
a 153-item ideas document: it hands the selection problem back to the reader.
The primary object is therefore the *workload group* (~60 of them), not the job.
Jobs are what you see after you have chosen a group.

Filtering, sorting and searching are pure in-memory operations over prebuilt
projections, so the UI never re-queries Slurm to answer a keystroke.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import NamedTuple

from .diagnose import looks_like_noop
from .model import Job
from .patterns import find_memory_search, find_repeat_failures, goodput, group_key, usable

# Core-hours one GPU-hour is worth when ranking mixed workloads. See
# GroupStats.cost for why this number and not a site billing weight.
GPU_CORE_EQUIVALENT = 16.0


class GroupStats(NamedTuple):
    """One workload rolled up. The unit the overview is built from."""

    key: tuple
    name: str  # the normalized pattern, e.g. "att-speed-#"
    partition: str
    kind: str  # "gpu" | "cpu"
    distinct_names: int  # how many real job names this pattern covers
    excluded: int  # same-workload records dropped as unterminated (elapsed = now - start)
    jobs: tuple
    total: int
    completed: int
    failed: int
    cancelled: int
    noop: int
    gpu_hours: float
    core_hours: float
    wasted_gpu_hours: float
    first_seen: str
    last_seen: str

    @property
    def failure_rate(self) -> float | None:
        judged = self.completed + self.failed
        return (self.failed / judged) if judged else None

    @property
    def noop_rate(self) -> float | None:
        return (self.noop / self.total) if self.total else None

    @property
    def cost(self) -> float:
        """Ranking weight, in core-hour equivalents.

        Ordering GPU and CPU work in one list needs an exchange rate, and this
        cluster does not supply one -- ``TRESBillingWeights`` is undefined on all
        86 partitions, so there is no site answer to defer to. The hardware ratio
        is the next most defensible thing: GPU nodes here carry 4 devices against
        32-64 cores, i.e. 8-16 cores per GPU. ``GPU_CORE_EQUIVALENT`` takes the
        upper end, which biases toward GPU work on the grounds that it is the
        scarce resource (the ``gpu`` partition is 11 nodes against caslake's 191).

        It is a convention, not a measurement, which is exactly why it is one
        named constant you can change rather than a factor buried in a sort key.
        """
        return self.gpu_hours * GPU_CORE_EQUIVALENT + self.core_hours

    @property
    def severity(self) -> str:
        """Traffic light for the group, from outcomes rather than any single job."""
        rate = self.failure_rate
        if self.total >= 3 and rate is not None and rate >= 0.5:
            return "crit"
        if self.noop_rate is not None and self.noop_rate >= 0.25 and self.total >= 3:
            return "crit"
        if rate is not None and rate >= 0.2:
            return "warn"
        if self.noop_rate is not None and self.noop_rate >= 0.1:
            return "warn"
        return "ok"


def _stamp(job: Job) -> str:
    return job.start or job.submit or ""


def build_groups(jobs: Iterable[Job]) -> list[GroupStats]:
    """Roll jobs up by workload, ranked by resources burned.

    Ranking is by cost, not count: a 5-run group that burned 400 GPU-hours
    matters more than a 400-run group of two-second probes, and a
    count-ordered list buries the former under the latter.
    """
    buckets: dict[tuple, list[Job]] = {}
    for job in usable(jobs):
        buckets.setdefault(group_key(job), []).append(job)

    # Unterminated records are excluded from every aggregate (their elapsed is
    # "now minus start"), but silently dropping them makes a workload look like
    # it lost jobs. Count them per workload so the UI can say so.
    dropped: dict[tuple, int] = {}
    for job in jobs:
        if job.open_ended:
            dropped[group_key(job)] = dropped.get(group_key(job), 0) + 1

    out: list[GroupStats] = []
    for key, members in buckets.items():
        members.sort(key=lambda j: _stamp(j), reverse=True)
        gpu_hours = sum(j.gpu_hours or 0.0 for j in members)
        core_hours = sum(
            (j.elapsed * j.cpu_count / 3600.0) for j in members if j.elapsed and j.cpu_count
        )
        dead = [j for j in members if looks_like_noop(j)]
        stamps = sorted(s for s in (_stamp(j) for j in members) if s)
        out.append(
            GroupStats(
                key=key,
                name=key[0],
                partition=key[1],
                kind=key[2],
                distinct_names=len({j.name for j in members}),
                excluded=dropped.get(key, 0),
                jobs=tuple(members),
                total=len(members),
                completed=sum(1 for j in members if j.completed),
                failed=sum(1 for j in members if j.failed),
                cancelled=sum(1 for j in members if j.cancelled),
                noop=len(dead),
                gpu_hours=gpu_hours,
                core_hours=core_hours,
                wasted_gpu_hours=sum(
                    j.gpu_hours or 0.0 for j in members if j.failed or looks_like_noop(j)
                ),
                first_seen=stamps[0] if stamps else "",
                last_seen=stamps[-1] if stamps else "",
            )
        )
    out.sort(key=lambda g: (-g.cost, -g.total))
    return out


# --- sorting -------------------------------------------------------------
# Ordered as presented in the UI; `s` cycles through them.
SORTS: tuple[tuple[str, str], ...] = (
    ("cost", "resources burned"),
    ("failures", "failed runs"),
    ("rate", "failure rate"),
    ("recent", "most recent"),
    ("runs", "run count"),
    ("name", "name"),
)

_SORT_KEYS: dict[str, Callable[[GroupStats], tuple]] = {
    "cost": lambda g: (-g.cost, -g.total),
    "failures": lambda g: (-(g.failed + g.noop), -g.cost),
    "rate": lambda g: (-(g.failure_rate or 0.0), -g.total),
    "recent": lambda g: (g.last_seen or "", g.name),
    "runs": lambda g: (-g.total, g.name),
    "name": lambda g: (g.name.lower(), g.partition),
}
_DESCENDING = frozenset(["recent"])


def sort_groups(groups: Sequence[GroupStats], mode: str) -> list[GroupStats]:
    key = _SORT_KEYS.get(mode, _SORT_KEYS["cost"])
    return sorted(groups, key=key, reverse=mode in _DESCENDING)


def next_sort(mode: str) -> str:
    names = [name for name, _ in SORTS]
    try:
        return names[(names.index(mode) + 1) % len(names)]
    except ValueError:
        return names[0]


def sort_label(mode: str) -> str:
    for name, label in SORTS:
        if name == mode:
            return label
    return mode


# --- filtering -----------------------------------------------------------

FILTERS: tuple[tuple[str, str], ...] = (
    ("all", "everything"),
    ("problem", "failed, timed out, or idle"),
    ("failed", "failed only"),
    ("noop", "held resources, computed nothing"),
)


def match_job(job: Job, mode: str) -> bool:
    if mode == "failed":
        return job.failed
    if mode == "noop":
        return looks_like_noop(job)
    if mode == "problem":
        return job.failed or looks_like_noop(job)
    return True


def filter_jobs(jobs: Iterable[Job], mode: str = "all", query: str = "") -> list[Job]:
    """Filter and free-text search, in memory.

    Search matches job id, name, state, partition and node list so one box
    serves "what happened to 51170455", "show me cot-exp", and "what died on
    midway3-0385" without a query language.
    """
    needle = (query or "").strip().lower()
    out = []
    for job in jobs:
        if not match_job(job, mode):
            continue
        if needle:
            haystack = " ".join(
                (
                    job.job_id,
                    job.name or "",
                    job.base_state,
                    job.partition or "",
                    job.node_list or "",
                )
            ).lower()
            if needle not in haystack:
                continue
        out.append(job)
    return out


def filter_groups(
    groups: Iterable[GroupStats], mode: str = "all", query: str = ""
) -> list[GroupStats]:
    needle = (query or "").strip().lower()
    out = []
    for group in groups:
        if mode == "failed" and not group.failed:
            continue
        if mode == "noop" and not group.noop:
            continue
        if mode == "problem" and not (group.failed or group.noop):
            continue
        if needle and needle not in ("%s %s" % (group.name, group.partition)).lower():
            continue
        out.append(group)
    return out


class History:
    """Everything loaded, indexed once.

    Built in a worker thread so a 1.26 s query does not block the first paint,
    and rebuilt wholesale on refresh -- incremental merge would be a correctness
    risk (a job's state changes after it finishes) for no measurable gain.
    """

    def __init__(self, jobs: Sequence[Job], window: str = ""):
        self.jobs: tuple[Job, ...] = tuple(jobs)
        self.window = window
        self.groups: list[GroupStats] = build_groups(jobs)
        self.stats = goodput(jobs)
        self._by_id = {job.job_id: job for job in self.jobs}
        self._patterns: list | None = None

    def __len__(self) -> int:
        return len(self.jobs)

    @property
    def usable_jobs(self) -> list[Job]:
        return usable(self.jobs)

    def job(self, job_id: str) -> Job | None:
        return self._by_id.get(job_id)

    def group_for(self, job: Job) -> GroupStats | None:
        key = group_key(job)
        for group in self.groups:
            if group.key == key:
                return group
        return None

    @property
    def patterns(self) -> list:
        """Cross-job findings, computed once on demand.

        Deferred because the overview does not need them and the detectors walk
        every group; paying for it at load time would slow the first paint for
        a panel the user may never open.
        """
        if self._patterns is None:
            found = list(find_repeat_failures(self.jobs))
            found.extend(find_memory_search(self.jobs))
            self._patterns = found
        return self._patterns

    def group_patterns(self, group: GroupStats) -> list:
        """Findings scoped to one workload."""
        found = list(find_repeat_failures(group.jobs, limit=3))
        found.extend(find_memory_search(group.jobs))
        return found

    def tail_summary(self, shown: int) -> str:
        """What sits below the fold, so truncation is never silent.

        The top 20 workloads carry 93.4% of all weighted resource on a real
        history, so a truncated list is the right default -- but a reader who
        cannot see what was dropped has no way to know that.
        """
        hidden = self.groups[shown:]
        if not hidden:
            return ""
        total = sum(g.cost for g in self.groups) or 1.0
        share = sum(g.cost for g in hidden) / total
        runs = sum(g.total for g in hidden)
        return "%d more workloads (%d runs) holding %.1f%% of the resource" % (
            len(hidden),
            runs,
            100.0 * share,
        )

    def headline(self) -> str:
        """One line for the footer: the number that should bother you most."""
        stats = self.stats
        if stats["gpu_hours_noop"] and stats["gpu_hours_total"]:
            return "%.0f of %.0f GPU-hours went to allocations that never computed" % (
                stats["gpu_hours_noop"],
                stats["gpu_hours_total"],
            )
        if stats["failed"]:
            return "%d of %d jobs failed" % (stats["failed"], stats["jobs"])
        return "%d jobs, nothing flagged" % stats["jobs"]
