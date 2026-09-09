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

One interval per node is not one test, though, and the table shows them together.
Each node's interval is right in isolation and the *table* was still wrong: at
Z = 1.96 each row trips about 2.5% of the time by chance, so a 20-node table
handed the user a node to exclude more than half the time when every node was in
truth identical -- an error rate set by how many nodes were tested rather than by
the evidence. Measured on a null where every node shares one true rate, as the
share of tables offering at least one innocent node to ``--exclude``:

    nodes tested           10       20       40
    uncorrected          36.5%    54.8%    77.8%
    Benjamini-Hochberg    2.7%     2.8%     2.4%

So the verdict is Benjamini-Hochberg controlled across the rows of the table (see
:func:`_bh_reject`). What matters is not that the corrected figure is smaller but
that it is *flat*: raising ``Z`` to 2.576 instead only slows the growth, from
13.5% / 21.3% / 33.8% across the same three table sizes -- a wider interval
treats the symptom, and the cause is the number of tests.

Those three figures counted only the ``worse`` half, because they were measured
off ``--exclude``. The family is both halves -- a ``better`` verdict is a claim
from the same table, corrected in the same pass -- and the direction each row is
tested in is *read off that row's own rate*. A tail taken in the winning direction
prices one look when two were available, so the row's p-value came out about half
what the selection was worth, and the table's real rate of offering an innocent
node some verdict ran at roughly twice the ``worse``-only figure. Re-measured on
the same null, as the share of tables reaching **any** verdict:

    per node   rate    nodes    tail in the       priced for the
                                won direction     direction (now)
    30         0.20    10        4.8%              2.5%
    30         0.20    20        4.5%              2.4%
    30         0.20    40        4.7%              1.2%
    30         0.35    20        5.5%              2.7%
    50         0.35    20        6.5%              3.2%
    100        0.35    20        7.8%              3.7%
    100        0.50    20        8.0%              3.8%
    200        0.50    20        8.2%              4.4%

The left column is the promise in FDR_ALPHA and holds only in the top block, where
Fisher's discreteness at 30 placements is doing the work rather than the
correction; give each node more evidence than that and it converges on twice the
target. So the direction costs a factor of two, applied where it is chosen --
:func:`selected_direction_p_value`.

Which regime a real table is in is worth knowing, because it says who sees this.
Held to one workload -- the default, and the whole point of this module -- a
90-day window here tests 34 nodes at a median of 20 placements and a maximum of
80, squarely in the protected block: the workload-controlled screens do not move
by a character. It is ``--all-workloads``, the confounded view, that pools 15,019
runs across 1,258 folds onto 308 rows with 26 of them past 100 placements and the
busiest at 713 -- and that is the view where pricing the direction withdrew three
verdicts, one of them off an ``--exclude`` line.

The cost is power against one truly bad node (0.55 against 0.20 elsewhere, 20
nodes): 55% at 20 placements per node, 82% at 30, 98% at 50, against 65% / 87% /
99% for the unpriced tail. It is concentrated where evidence is thin, which is
where this module already says it wants to hold back.
"""

import math
import re

from .diagnose import looks_like_noop
from .duration import format_rate_range
from .patterns import fold_erased_the_name, newest_name, normalize_name, usable

MIN_SAMPLES = 10
# The smallest loaded history :func:`note_for_allocation` will draw a conclusion
# from. Distinct from MIN_SAMPLES, which floors the placements on the node being
# judged: this floors the whole population the comparison is drawn against, and
# nothing else does. `node_table` has no minimum on `other_trials`, so 10 failures
# on one node beside 2 clean runs on another already clears MIN_SAMPLES, BH and
# the Wilson interval and says "against 0.0% on every other node" -- an "every
# other node" of two placements. That is the case this floor exists for.
#
# It lived in both front ends as a bare `20` (`cli._node_note`, `tui.JobScreen.
# render_body`), which is how the two came to disagree about whether the note
# exists at all: same literal, different `jobs` argument, and no single place to
# read the rule out of. `render.py` cannot hold it -- the analysis modules may not
# import `render` -- so it sits beside the other thresholds it is one of.
MIN_HISTORY = 20
Z = 1.96  # 95%, and the interval the table displays stays a plain 95% interval
# The false-discovery rate the table as a whole is held to. Not a per-row alpha:
# the user reads every row at once and pastes whatever tripped into --exclude, so
# the family is the table.
FDR_ALPHA = 0.05

# The confidence level `Z` is the two-sided critical value for, DERIVED rather than
# written down a second time: erf(Z / sqrt(2)) is 0.9500042 at Z = 1.96. Every
# surface spells the level as the literal text "95% CI" -- six places do, two of
# them column labels -- while `Z` is what actually decides the interval. Deriving
# it here means the payload cannot disagree with the arithmetic, whatever the
# labels say.
CONFIDENCE_LEVEL = math.erf(Z / math.sqrt(2.0))

# The level as every surface SPELLS it -- "95" -- taken from the derived value
# rather than typed again. Same rounding as the `confidence_level` key the payload
# carries, so the prose, the payload and the column label cannot disagree about
# what `Z` means. The three layout-coupled spellings (the `NODE_COLUMNS` label and
# the two dict keys that must match it) are pinned against this rather than
# rebuilt, because their WIDTH is declared beside them.
CONFIDENCE_PERCENT = "%g" % round(CONFIDENCE_LEVEL * 100, 1)

# The first bracketed range in a name, with whatever precedes and follows it.
# The prefix is deliberately unconstrained: a character class enumerating what a
# node name may contain got `cn_[01-02]` and `gpu.node[1-2]` wrong, both of which
# `scontrol show hostnames` expands happily.
_RANGE = re.compile(r"^([^\[\]]*)\[([^\[\]]+)\](.*)$")

# Guard against a pathological expression eating memory. A real allocation is
# thousands of nodes at the very top end; this is far above any of them and only
# exists so a malformed `[0-999999999]` cannot hang the tool.
#
# Enforced *while* expanding, not afterwards. Truncating the finished list left
# the guard doing nothing about the case that needs it: two ranges multiply, so
# `u[1-2000]r[1-2000]` built four million strings and 325 MiB before anything
# trimmed it to this bound, and a third range would not have returned at all.
MAX_EXPANSION = 65536


def expand_nodelist(nodelist):
    """``midway3-[0277-0279,0281]`` -> the individual node names.

    Slurm compresses NodeList, so counting occurrences of the raw string
    undercounts multi-node jobs and mis-attributes their failures.

    Handles the whole hostlist grammar Slurm accepts, verified against
    ``scontrol show hostnames``:

      ``midway3-[0277-0279,0281]``  ranges and singletons, zero-padded
      ``unit[0-3]rack[0-2]``        several ranges in one name, expanded as the
                                    cartesian product -- 12 nodes, not 4
      ``node[0001-0010]-int``       a shared suffix (Slurm 23.11 and later)
      ``cn_[01-02]``                underscores and dots in the prefix
      ``a1,b[2-3],c``               a list, with commas inside brackets kept

    The multi-range form was the expensive one to get wrong: it yielded
    ``unit0rack[0-2]`` as a *node name*, so every node in such an allocation was
    invisible to the reliability table and none of its failures were attributed.
    """
    if not nodelist or nodelist.startswith("None"):
        return []
    out = []
    for chunk in _split_top_level(nodelist):
        out.extend(_expand_one(chunk, MAX_EXPANSION - len(out)))
        if len(out) >= MAX_EXPANSION:
            return out[:MAX_EXPANSION]
    return out


def _expand_one(name, limit=MAX_EXPANSION):
    """Expand every bracketed range in one host expression, left to right.

    ``limit`` bounds what this may return, and is applied at every stage rather
    than to the finished list -- ranges multiply, so a list built first and trimmed
    second is not bounded at all.
    """
    if limit <= 0:
        return []
    match = _RANGE.match(name)
    if not match:
        return [name] if name else []
    prefix, body, rest = match.group(1), match.group(2), match.group(3)

    heads = []
    for part in body.split(","):
        if len(heads) >= limit:
            break
        part = part.strip()
        if not part:
            continue
        low, dash, high = part.partition("-")
        if not dash:
            heads.append(prefix + part)
            continue
        width = len(low)
        try:
            first, last = int(low), int(high)
        except ValueError:
            # Not a numeric range after all; keep it verbatim rather than invent
            # names, so an unfamiliar expression degrades to one unmatched node.
            heads.append(prefix + part)
            continue
        if last < first:
            heads.append(prefix + part)
            continue
        stop = min(last, first + (limit - len(heads)) - 1)
        heads.extend("%s%0*d" % (prefix, width, value) for value in range(first, stop + 1))

    # `rest` may hold further ranges (`unit[0-3]rack[0-2]`) or a plain suffix.
    tails = _expand_one(rest, limit) if rest else [""]
    out = []
    for head in heads:
        for tail in tails:
            if len(out) >= limit:
                return out
            out.append(head + tail)
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


def _hypergeom_log_pmf(k, total, marked, drawn):
    """log P(k marked in a draw of ``drawn`` from ``total`` holding ``marked``)."""
    return (
        math.lgamma(marked + 1)
        - math.lgamma(k + 1)
        - math.lgamma(marked - k + 1)
        + math.lgamma(total - marked + 1)
        - math.lgamma(drawn - k + 1)
        - math.lgamma(total - marked - drawn + k + 1)
        - math.lgamma(total + 1)
        + math.lgamma(drawn + 1)
        + math.lgamma(total - drawn + 1)
    )


def node_p_value(bad, trials, other_bad, other_trials, direction="worse"):
    """One-sided Fisher exact p-value for one node against every other node.

    Fisher rather than a binomial tail against the leave-one-out rate, because
    that rate is *estimated* from the other nodes rather than known. Treating it as
    known makes the zero case degenerate: with no failures anywhere else, a
    binomial test against p = 0 scores a single failure on one node at exactly
    p = 0, which no correction can ever withhold however many nodes were tested.
    Fisher conditions on the margins instead and scores that same 1-of-10 against
    0-of-500 at p = 0.0196 -- borderline, and so still subject to the size of the
    table: it stands in a two-node table and is withheld once a third node is
    there to have been tested too.

    Exact rather than a chi-square, because a node with 3 failures in 12
    placements is a typical row here and no approximation is trustworthy there.
    """
    total = trials + other_trials
    marked = bad + other_bad
    if trials <= 0 or other_trials <= 0 or marked <= 0 or marked >= total:
        return 1.0

    # The hypergeometric support: how many of this node's placements could have
    # been the failing ones at all.
    low = max(0, trials - (total - marked))
    high = min(trials, marked)
    start, stop, step = (bad, high, 1) if direction == "worse" else (bad, low, -1)
    start = min(max(start, low), high)

    term = math.exp(_hypergeom_log_pmf(start, total, marked, drawn=trials))
    tail = term
    mode = trials * marked / float(total)
    for k in range(start, stop, step):
        if step > 0:
            # pmf(k+1)/pmf(k), by cancellation in the ratio of binomials.
            term *= (marked - k) * (trials - k)
            term /= float((k + 1) * (total - marked - trials + k + 1))
        else:
            # pmf(k-1)/pmf(k), the same ratio inverted.
            term *= k * (total - marked - trials + k)
            term /= float((marked - k + 1) * (trials - k + 1))
        tail += term
        # Terms only decay once the mode is behind us, so a small term before
        # then is not a spent tail.
        if term <= 1e-18 * tail and ((step > 0 and k >= mode) or (step < 0 and k <= mode)):
            break
    return min(1.0, max(0.0, tail))


def selected_direction_p_value(bad, trials, other_bad, other_trials, direction):
    """:func:`node_p_value`, priced for a ``direction`` that was read off the data.

    ``node_table`` does not decide in advance which way it suspects a node; it
    compares the node's rate against the rest of the fleet and *then* tests the
    tail it already knows the data fell in. That is two looks, and a one-sided
    tail charges for one. The correction is the factor between them: a row that
    would need p <= t to be believed had two chances to reach t, so 2p is the
    p-value that means what a p-value is supposed to mean here.

    Not folded into :func:`node_p_value`, which stays the plain one-sided tail --
    it is checked against a hand-computed hypergeometric and against
    ``scipy.stats.fisher_exact`` over 5,986 comparisons, and the caller that
    names its direction up front owes nothing. The charge belongs at the site
    that picks the direction, which is the only place the debt is incurred.

    Doubling rather than a two-sided Fisher tail: for these lopsided 2x2 tables
    the two disagree, and the two-sided tail is the smaller and so the weaker
    guarantee. Doubling is also the whole of the arithmetic, which matters for a
    number that decides what goes on an ``--exclude`` line.
    """
    return min(1.0, 2.0 * node_p_value(bad, trials, other_bad, other_trials, direction))


def _bh_reject(pvalues, alpha=FDR_ALPHA):
    """Benjamini-Hochberg step-up: the indices whose null is rejected at FDR ``alpha``.

    Sort the p-values, find the largest rank ``k`` with ``p_(k) <= alpha*k/m``,
    reject the ``k`` smallest. What this buys over Bonferroni or a bigger ``Z`` is
    that it scales with the *evidence* rather than the count: one node that is
    genuinely broken still clears it in a 40-node table, while forty innocent
    nodes do not start tripping just because there are forty of them.
    """
    count = len(pvalues)
    if not count:
        return set()
    order = sorted(range(count), key=lambda i: pvalues[i])
    cut = 0
    for rank, index in enumerate(order, start=1):
        if pvalues[index] <= alpha * rank / count:
            cut = rank
    return set(order[:cut])


def _bad(job):
    """Outcomes attributable to the run failing. Cancellations excluded -- ambiguous."""
    return job.failed


def _informative(job, metric):
    """Whether this placement says anything about the node, for ``metric``.

    A cancellation is the case that differs. ``_bad`` has always excluded it from
    the numerator -- "ambiguous" -- while it stayed in the denominator, which
    scores it as a placement the node handled fine. That is not exclusion; it is
    counting an unknown as a success, and it is the one thing this module does
    that the rest of it argues against. `index` states the position:

        "a cancelled run is neither [completed nor flagged] ... a deliberate kill
        and an abandoned one are identical in accounting"

    Everything else here works hard not to over-claim -- Fisher exact, a
    Benjamini-Hochberg correction, Wilson intervals, MIN_SAMPLES -- and then padded
    the denominator with rows it had itself called uninformative. On a real 90-day
    history 7.3% of placements are cancellations, and censoring them moves 7 of 9
    rows: midway3-0330 from 12.3% to 20.0%, midway3-0376 from 21.8% to 26.6%, and
    two nodes below MIN_SAMPLES, which is the honest answer when the informative
    sample really is that small.

    **The hang metric keeps them, and that is not an inconsistency.** There a
    cancellation is often the evidence itself: 340 of those 1,094 satisfy
    `looks_like_noop`, a job that held its allocation and computed nothing until
    someone killed it. Dropping those would throw away the primary signal for the
    metric that is the default.

    ``OUT_OF_MEMORY`` is censored for the same reason and with less ambiguity than
    a cancellation, because it was in the *numerator*: Slurm records it when the
    job's cgroup passed the memory the job itself asked for, which is a property
    of ``--mem`` and is enforced identically by every node that honours the
    request. The workload control cannot remove this confound the way it removes a
    code bug, because one array's elements do not all need the same memory: on a
    real 90-day history `caai-p10b_scan` asked `mem=6G` for all 142 elements and
    71 of them died OOM across ten nodes, and the table put `midway3-0187` --
    identical hardware to `midway3-0200`, 48 CPUs and 184320 MB each -- into a
    paste-ready ``#SBATCH --exclude=`` on the strength of 14 OOM placements out of
    21. Censoring leaves it 0 of 7 informative placements, i.e. below MIN_SAMPLES,
    which is again the honest answer. `midway3-0250`, whose 32 failures are real
    FAILED rows, still scores worse and is still suggested -- so this narrows the
    claim without costing the signal.

    The hang metric keeps OOM too, and that is likewise not an inconsistency: a
    job that got far enough to be killed for its memory is evidence the node did
    *not* hang, so there the placement is informative.
    """
    if metric == "hang":
        return True
    # TIMEOUT deliberately stays. It is the metric this module was built on -- the
    # docstring's founding measurement is 19 hangs in 36 on midway3-0385 -- and a
    # wall-clock kill really can be the machine (a wedged mount, a stuck GPU),
    # which is exactly what holding the workload fixed is there to separate.
    return not job.cancelled and job.base_state != "OUT_OF_MEMORY"


class Workload(str):
    """The stratum a node comparison holds fixed: one person's piece of work.

    A job *name* is not that identity once a query spans users, and one flag away
    is exactly where it stops being one -- ``-u alice,bob`` and ``--all-users``.
    Measured on this cluster: over two days **25 job names are used by more than
    one person**, `interactive` by eight of them and `ssd_lab_base` by six. Pooled
    under one name, alice's twelve hangs on a node and bob's twelve clean runs on
    the same node report 12/24 = 50% for a node that is 100% for alice and 0% for
    bob -- so the module whose entire reason for existing is holding the workload
    fixed was not holding it fixed.

    `patterns.group_key` had this defect and it was fixed there, in these words:
    "two people's unrelated ``run.sh`` on one partition became a single fabricated
    workload". The fix never reached here.

    **A ``str`` subclass, deliberately.** Its string value is what the screens
    print, so every caller that interpolates or searches a workload keeps working
    and the identity rides along in ``.name`` and ``.user``. A tuple type was
    written first and broke 71 tests in one run: ``"only %s counted" % workload``
    unpacks a tuple instead of formatting it, and ``workload in text`` raises. A
    value whose whole job is to be displayed should be the thing displayed.

    ``user=None`` means "any", which is what a bare name has always meant and is
    correct for the single-user query that is the default -- so a caller passing a
    plain string keeps exactly today's behaviour.

    ``qualified`` puts the owner into the printed label, and is set only when the
    history the workload was chosen from spans more than one user: "alice's
    interactive" precisely where that distinction is load-bearing, "cot-exp"
    otherwise.
    """

    __slots__ = ("name", "user")

    # Annotated as well as slotted: `__slots__` reserves the storage, and mypy
    # needs the declaration to know the attributes exist at all.
    name: str
    user: str | None

    def __new__(cls, name, user=None, qualified=False):
        label = "%s's %s" % (user, name) if (qualified and user) else str(name)
        workload = super().__new__(cls, label)
        workload.name = str(name)
        workload.user = user
        return workload

    def matches(self, job) -> bool:
        if normalize_name(job.name) != normalize_name(self.name):
            return False
        return self.user is None or job.user == self.user


def as_workload(value):
    """A :class:`Workload` from whatever a caller passed, or None."""
    if value is None or isinstance(value, Workload):
        return value
    return Workload(str(value))


def node_table(jobs, workload=None, metric="failure", min_samples=MIN_SAMPLES):
    """Per-node rates.

    ``workload`` restricts to one group key's job name, which is how the
    confound is controlled. ``metric`` is ``failure`` or ``hang``.

    Matched against the *normalised* name, the same fold the rest of the tool groups
    work by. Raw-name equality fragmented a parameter sweep into one stratum per
    arm -- ``s1e20``, ``s2e47``, ``s3e83`` are one piece of work and 1,624 distinct
    strings -- and a fragment is too small to test: every node fell under
    MIN_SAMPLES, so a node failing 27 of 30 placements produced an empty table. The
    module's own reason for existing is holding the workload fixed, and this is what
    "the same workload" means everywhere else in the codebase.
    """
    records = usable(jobs)
    workload = as_workload(workload)
    if workload:
        records = [j for j in records if workload.matches(j)]

    predicate = looks_like_noop if metric == "hang" else _bad

    totals, hits = {}, {}
    for job in records:
        if not _informative(job, metric):
            continue
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
        # Against the REST of the fleet, not against a pooled rate that includes
        # this node's own placements. midway3-0602 holds 403 of 1,098 placements
        # here, so the pooled baseline is 37% made of the node under test and gets
        # dragged toward whatever that node does -- which hides exactly the nodes
        # that ran the most work. Leave-one-out is the comparison the verdict claims
        # to be making.
        other_trials = total_trials - trials
        other_hits = total_hits - bad
        comparison = (other_hits / float(other_trials)) if other_trials else None
        rate = bad / float(trials)
        # Every row gets a test, including the ones no interval singles out --
        # because the size of the family is how many nodes were *examined*, not how
        # many happened to look extreme. Scoring only the extreme rows would set m
        # to the number of candidates and correct for the wrong number of tests.
        if comparison is None or rate == comparison:
            direction, p_value = "", 1.0
        else:
            direction = "worse" if rate > comparison else "better"
            # Priced, not raw: the direction on the line above came out of `rate`
            # and `comparison`, so the tail below it is the one the data already
            # chose. See `selected_direction_p_value` and the module docstring's
            # second null table -- unpriced, this family ran at up to 8.2% against
            # the 5% FDR_ALPHA promises, and the excess is exactly the factor of
            # two a free choice of direction is worth.
            p_value = selected_direction_p_value(bad, trials, other_hits, other_trials, direction)
        rows.append(
            {
                "node": node,
                "bad": bad,
                "trials": trials,
                "rate": rate,
                "ci_low": low,
                "ci_high": high,
                "comparison": comparison,
                "direction": direction,
                "p_value": p_value,
                "verdict": "unknown" if comparison is None else "inconclusive",
            }
        )

    # Both conditions have to hold for a verdict, and each one is doing a
    # different job. BH bounds how often the *table* invents a bad node. The
    # interval keeps the verdict consistent with what the row displays -- "worse"
    # printed beside a 95% CI containing the comparison rate reads as a
    # contradiction, whatever the p-value says. Intersecting BH's rejections with
    # any further condition cannot add false ones, so the FDR bound survives it.
    survived = _bh_reject([r["p_value"] for r in rows])
    for index, row in enumerate(rows):
        if index not in survived or not row["direction"]:
            continue
        if row["direction"] == "worse" and row["ci_low"] > row["comparison"]:
            row["verdict"] = "worse"
        elif row["direction"] == "better" and row["ci_high"] < row["comparison"]:
            row["verdict"] = "better"

    # Rows the table will show with an interval clear of the baseline and no
    # verdict beside it. Counted from the verdict actually reached, not from the
    # branch that reached it, so it cannot drift from what the screens then claim.
    # They need it: the interval is on display, and a user reading it against the
    # verdict column deserves to be told why the two disagree rather than left to
    # conclude the tool is broken.
    #
    # Against `baseline` -- the one rate the screens print (`render.nodes_baseline`)
    # -- and not against the per-row leave-one-out `comparison`, which appears
    # nowhere the reader can see. `render.held_back_note` says "N intervals clear
    # THE BASELINE on their own", so N has to be countable off the CI column beside
    # the printed baseline or the sentence sends the reader looking for a row that
    # is not there. `comparison` over-counts, always in that direction: `baseline`
    # is a convex combination of this row's rate and `comparison`, and a Wilson
    # interval always contains its own rate, so clearing `baseline` implies
    # clearing `comparison` but not the reverse. On a real 90-day history the
    # default screen said "2 intervals clear the baseline on their own" over a
    # table holding one -- midway3-0039 at 1/65, whose 0.3-8.2% interval clears
    # comparison 8.68% but not the 8.2% baseline printed two lines above it.
    held_back = sum(
        1
        for row in rows
        if row["verdict"] == "inconclusive"
        and baseline is not None
        and (row["ci_low"] > baseline or row["ci_high"] < baseline)
    )

    rows.sort(key=lambda r: -r["rate"])
    return {
        "rows": rows,
        "baseline": baseline,
        "trials": total_trials,
        "hits": total_hits,
        "metric": metric,
        # The bare name, and the owner beside it rather than folded into a display
        # label: a consumer of `--nodes --json` filtering on `workload` was reading
        # a name before this and must keep reading one. The qualified "alice's
        # interactive" form is for screens; see Workload.
        "workload": workload.name if workload else None,
        "workload_user": workload.user if workload else None,
        # The two thresholds the rendered table states and the payload did not.
        # The column header says `95% CI` and the verdict paragraph says the
        # correction is "after correcting for N nodes tested"; a consumer holding
        # `ci_low`/`ci_high` had no way to learn what level they are an interval
        # OF -- a 95% and a 99% interval are different claims about the same two
        # numbers -- and one holding `p_value` beside `verdict` could not tell
        # which threshold produced the verdict, so it could neither re-derive the
        # verdicts under its own alpha nor see how close a `same` row came.
        "confidence_level": round(CONFIDENCE_LEVEL, 2),
        "fdr_alpha": FDR_ALPHA,
        "tested_nodes": len(rows),
        "held_back": held_back,
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

    Choosing the densest-failure stratum before testing every node in it does read
    like it should push the same way as the multiple-comparison problem, so it was
    measured once that was fixed. It does not, and the reason is structural: the
    Fisher test in :func:`node_p_value` *conditions on* the total number of
    failures in the table, and the total is precisely what this function selects
    on. Selecting on a statistic the test conditions away cannot bias it. Paired
    against a workload chosen at random on the same 3,000 simulated histories, all
    nodes null within each workload: 3.73% against 3.03% at 10 nodes and 3.17%
    against 2.97% at 20 (SE ~0.35%). At most a fraction of a point, and under the
    5% target either way.

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

    # Counted by normalised name, matching what node_table then filters on. Counting
    # raw names let a workload with one constant name outrank a parameter sweep many
    # times its size -- 120 runs of `routine-check` beating 200 runs spread over 200
    # distinct strings -- so the screen controlled on the wrong stratum and never
    # tested the sweep's genuinely bad node at all.
    # Keyed by (name, user), not by name: see Workload. Under the single-user query
    # that is the default this changes nothing, because the user is constant.
    #
    # Counted over the placements :func:`node_table` will actually test, not over
    # every usable record -- see :func:`_informative`. Selecting on events the
    # table then censors picks a stratum in which the question is no longer
    # answerable, which is the precise failure this function was written to avoid:
    # a workload whose failures are all OUT_OF_MEMORY wins the selection and then
    # arrives at the table with nothing left in the numerator. Falls back to the
    # whole set when the censoring empties it, so a window of nothing but
    # cancellations still names a workload rather than raising on max(()).
    scored = [j for j in records if predicate is None or _informative(j, metric)] or records
    counts, events, members = {}, {}, {}
    for job in scored:
        key = (normalize_name(job.name), job.user)
        counts[key] = counts.get(key, 0) + 1
        members.setdefault(key, []).append(job)
        if predicate is not None and predicate(job):
            events[key] = events.get(key, 0) + 1
    spans_users = len({job.user for job in records}) > 1
    if events:
        # Most events first, then most runs -- both feed the statistical power to
        # tell one node apart from another.
        best = max(events, key=lambda key: (events[key], counts[key]))
    else:
        best = max(counts.items(), key=lambda kv: kv[1])[0]
    name, user = best
    # The signature is the stratum, but it is not always a name: an all-digit job
    # name folds to `#` and a date-stamped one to `#-#`, and this screen then said
    # "controlled for workload: only #-# counted" and "No hangs recorded for #-#",
    # naming nothing the reader could match to a job. A real name from the same
    # group reads, and costs nothing: `Workload.matches` normalises before
    # comparing, so the stratum this selects is unchanged either way -- and
    # `--nodes --json` keeps emitting a name, which is what its consumers read.
    if fold_erased_the_name(name):
        name = newest_name(members[best]) or name
    return Workload(name, user, qualified=spans_users)


def suggest_exclude(table, limit=8):
    """Nodes worse than the rest of the fleet, after correcting for the whole table.

    Both halves of that matter. This is the one output a user acts on directly --
    it is pasted into a submission script -- so it is the one place an uncorrected
    per-row test was actually expensive.
    """
    bad = [r["node"] for r in table["rows"] if r["verdict"] == "worse"]
    return bad[:limit]


def excluded_tail(table, limit=8):
    """How many "worse" nodes :func:`suggest_exclude` left out of its line.

    The cap is deliberate -- excluding a dozen nodes trades away enough of the
    partition to make a job unschedulable -- but it was silent, so a paste-ready
    ``--exclude`` read as the complete answer while the table directly above it
    showed four more rows with the same verdict and comparable evidence. Everything
    else here names its tail; this was the one that did not.
    """
    return max(0, sum(1 for r in table["rows"] if r["verdict"] == "worse") - limit)


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


def note_for_allocation(jobs, nodelist, workload=None):
    """Reliability note for the worst node in one job's allocation, or "".

    Both front ends used to pass ``expand_nodelist(job.node_list)[0]`` -- the first
    node of the allocation and nothing else. On the single-node job that is 99.6% of
    a real history that is the whole allocation and the same answer. On a multi-node
    job it silently examined one node of however many, so the note went missing
    exactly when the job had the most places to have gone wrong: a run on
    ``midway3-[0600-0607]`` whose failures all came from ``0607`` was told nothing,
    because ``0600`` is clean and is what got looked at.

    One table for the whole allocation rather than one per node: :func:`node_table`
    walks the entire history, and the family the correction is applied over has to
    be the table, not a per-node slice of it.

    ``MIN_HISTORY`` is applied here, once, rather than by each caller. Both front
    ends used to hold their own copy of it and hand this function a different
    population, so ``slurmpast <one id> --plain`` was silent about a node that had
    failed 32 of 33 placements while the dashboard's screen for that same id drew
    the sentence. Whoever asks gets the same answer for the same records now, which
    is the only way the two surfaces can be kept from drifting.
    """
    nodes = expand_nodelist(nodelist)
    if not nodes:
        return ""
    # `> MIN_HISTORY`, not `>=`, because that is what both front ends spelled and
    # this move is not the place to shift the number. Counted over `usable` -- the
    # records the table can actually use -- where `cli` counted `len(history)`,
    # every parsed row including the ones `node_table` then discards. On the
    # history this was measured against that is 15,040 against 15,046, so no
    # reader's note changes; it is the quantity the threshold claims to be about.
    if len(usable(jobs)) <= MIN_HISTORY:
        return ""
    table = node_table(jobs, workload=workload, metric="failure")
    wanted = set(nodes)
    # Rows arrive worst-rate first, so the first match is the node most worth
    # naming -- and only one is named. A job on eight bad nodes needs to know that
    # its placement is the problem, not a list of eight intervals.
    for row in table["rows"]:
        if row["node"] in wanted:
            note = _note_from_row(
                row, _stratum_label(workload, jobs), table["trials"] - row["trials"]
            )
            if note:
                return note
    return ""


def _stratum_label(workload, jobs):
    """The stratum's label, folded -- the display rule this module already applies.

    ``Workload.matches`` normalises before comparing, so the stratum IS the fold
    whatever label rides on it, and :func:`dominant_workload` prints that fold,
    substituting a real name only where the fold erased it
    (:func:`patterns.fold_erased_the_name`, whose docstring calls itself "only a
    *display* rule ... callers use this to decide whether the key is fit to be read
    aloud"). The note never applied it: `cli._node_note` and the dashboard both
    build ``Workload(job.name, job.user)``, so the sentence carried ONE job's raw
    name over a finding pooled across the whole fold.

    Measured on this cluster's 90-day history: 92 of 1,258 folds hold more than one
    raw name, and the largest, ``exp-n#``, spans **154 distinct names across 157
    jobs** -- so "for exp-n89" named one 157th of what the sentence's own figures
    cover, while the nodes screen beside it said "only exp-n# counted". Round
    forty-eight recorded the two labels and could not reproduce a wrong count; the
    count was never wrong, the attribution was.

    Label only. The `workload` handed to :func:`node_table` is untouched, so which
    jobs are pooled cannot change -- the same reason `dominant_workload` gives for
    its own substitution.
    """
    if not workload:
        return workload
    signature = normalize_name(workload)
    # A fold with no letters left names nothing a reader can match to a job, so the
    # raw name is the better label there -- the same fallback, in the same order.
    if not signature or fold_erased_the_name(signature):
        return workload
    # Only where the fold actually pooled more than one name. Folding a stratum
    # that holds a single name trades a true, specific label for a true, vaguer
    # one: `caai-p10b_scan` is what the reader submitted and `caai-p#b_scan` is
    # a pattern they never typed. 1,166 of this history's 1,258 folds are that
    # shape, so the specific label is the common case, not the exception.
    matcher = as_workload(workload)
    names = {job.name for job in usable(jobs) if matcher.matches(job)}
    if len(names) <= 1:
        return workload
    return signature


def _note_from_row(row, workload=None, other_trials=None):
    """The note one table row supports, or "" when it supports none.

    **The comparison gets a denominator too.** The sentence was scrupulous about
    its own -- "failed 32 of 33 placements there" -- and then gave the thing it
    was compared against as a bare "against 3.4% on every other node", with no
    indication whether that rate came from 13,000 placements or from two. On this
    cluster's real history it is 13,497 and the omission costs nothing; the
    reachable case is a short window, because ``node_table`` applies no
    ``MIN_HISTORY`` and ``--nodes`` calls it directly. Round fifty measured that
    and declined to add a floor -- the p-value already prices a thin comparison
    arm, and a count floor suppressed a p=0.0007 finding the demo exists to show
    -- which leaves this: say how big the comparison is and let the reader weigh
    it. No verdict changes.

    **Only when the comparison is the weaker half**, and that bar is derived from
    the row rather than picked: below ``row["trials"]``, the thing being compared
    against rests on fewer placements than the node being accused, and the
    reader is entitled to know which side is thin. Above it the number is never
    surprising -- on this cluster's 90-day history it is 13,497 against a node's
    344 -- and spending 25 characters of a one-line job-screen note to say so
    would cost every reader something to tell almost none of them anything.
    That also keeps a previous round's control honest: every figure the sentence
    already carried is untouched, and in the common case so is its wording.

    ``over N placements`` is ``render.nodes_baseline``'s phrasing for the pooled
    value of this very field ("baseline 3.4% over 2675 placements"), and that
    line owns the noun. ``None`` keeps the old wording, for a caller holding a row
    but not the table it came from.

    **``placements``, not "your N jobs".** The denominator is ``row["trials"]``,
    and since :func:`_informative` began censoring cancellations -- and then
    ``OUT_OF_MEMORY`` for the failure metric -- that is no longer a count of runs
    the reader submitted. It is the count of runs whose outcome could have been
    the *node's* doing. On a real 90-day history `sacct` holds 36
    ``caai-p10b_scan`` rows on `midway3-0250` (32 FAILED, 1 COMPLETED, 3
    CANCELLED) and this sentence's denominator is 33; `midway3-0187` has 21 and
    it is 7, because 14 of them are OOM. Censoring the denominator is right --
    an OOM says nothing about the machine, since every node enforces the same
    ``--mem`` -- but "your 33 jobs there" then asserts something about the
    reader's own submissions that is false by three, and invites them to check it
    against `sacct` and conclude the tool cannot count. The possessive is what
    turns a count into that claim, so it goes with the noun.

    **The noun is ``render.nodes_baseline``'s, deliberately.** That sentence
    prints the *pooled* value of this very field -- ``baseline 3.4% over 2675
    placements`` is ``table["trials"]`` where this is ``row["trials"]`` -- so one
    field carried two nouns across two screens and only one of them was
    possessive. ``nodes_empty_reason`` ("No node reached the 10 placements a
    comparison needs") and this module's own docstrings use the same word; the
    table's ``N`` column and ``--json``'s ``trials``/``bad`` are keys rather than
    prose and are left alone. Reusing the word that already exists is the rule
    ``render`` is there to enforce, and it cannot be enforced *from* ``render``
    here: ``render`` imports this module (and ``rich``), which the analysis
    modules may not, so the sentence stays in the one place both front ends
    already share and takes render's vocabulary with it rather than being spelled
    out twice.
    """
    # The rate the verdict was actually reached against -- every other node --
    # rather than the fleet-wide figure this row is itself part of.
    comparison = row.get("comparison")
    if row["verdict"] != "worse" or comparison is None:
        return ""
    # Pre-formatted so the sentence stays in ONE place: a second full spelling of
    # it under an `if` is exactly the drift `render.py` exists to prevent.
    against = "%.1f%%" % (100 * comparison)
    if other_trials is not None and other_trials < row["trials"]:
        against += " over %d placements" % other_trials
    return (
        "%s failed %d of %d placements there (%.1f%%, %s%% CI %s) against "
        "%s on every other node%s."
        % (
            row["node"],
            row["bad"],
            row["trials"],
            100 * row["rate"],
            CONFIDENCE_PERCENT,
            format_rate_range(row["ci_low"], row["ci_high"]),
            against,
            (" for %s" % workload) if workload else "",
        )
    )


def note_for_node(jobs, node, workload=None):
    """One-line reliability note for one named node, or "" when evidence is thin.

    :func:`note_for_allocation` is what a job screen wants; this stays for asking
    about a node on its own.
    """
    if not node:
        return ""
    table = node_table(jobs, workload=workload, metric="failure")
    for row in table["rows"]:
        if row["node"] == node:
            return _note_from_row(
                row, _stratum_label(workload, jobs), table["trials"] - row["trials"]
            )
    return ""
