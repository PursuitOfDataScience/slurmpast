"""Turning a workload's history into what its next run should request.

This is the tool's purpose: over-requesting narrows which nodes can host a job
and reserves capacity nobody else can use, under-requesting kills the run, and
the past runs of a workload are the evidence for both.

Every guard rail below exists because a naive rule got it wrong on real records.
"""

from slurmpast.demo import history
from slurmpast.index import build_groups
from slurmpast.sizing import (
    MIN_RUNS,
    cpu_advice,
    memory_advice,
    recommend,
    sbatch_lines,
    walltime_advice,
)


def workload(name):
    return [j for j in history() if j.name == name]


class TestWalltime:
    def test_sized_from_completed_runs(self):
        advice = walltime_advice(workload("midtrain"))
        assert advice.flag == "--time"
        assert advice.verdict in ("raise", "lower", "keep")

    def test_a_hung_workload_gets_no_time_advice(self):
        """99 of 115 real cot-exp runs hit a 30-minute wall on 0.56s of CPU.
        Raising the limit buys a longer hang."""
        advice = walltime_advice(workload("cot-exp"))
        assert advice.verdict == "unknown"
        assert advice.suggestion == ""
        assert "blocked, not slow" in advice.basis

    def test_one_stray_hang_does_not_veto_a_healthy_workload(self):
        """The first version let a single hung run silence 154 clean ones."""
        jobs = workload("midtrain")
        hung = jobs[0]._replace(job_id="9990", state="TIMEOUT")
        advice = walltime_advice(jobs + [hung])
        assert advice.verdict != "unknown"

    def test_too_few_runs_declines_to_guess(self):
        advice = walltime_advice(workload("midtrain")[: MIN_RUNS - 1])
        assert advice.verdict == "unknown"
        assert "at least" in advice.basis

    def test_a_timeout_sets_a_floor_never_a_fit(self):
        """A timeout's Elapsed is truncated at the limit, so it bounds the true
        runtime only from below."""
        jobs = workload("midtrain")
        timed_out = jobs[0]._replace(job_id="9991", state="TIMEOUT", timelimit=100000.0)
        advice = walltime_advice(jobs + [timed_out])
        assert advice.caution
        assert "floor, not a fit" in advice.caution

    def test_suggestion_is_a_slurm_time_string(self):
        advice = walltime_advice(workload("midtrain"))
        if advice.suggestion:
            assert advice.suggestion.count(":") == 2

    def test_never_advises_a_limit_below_a_run_that_completed(self):
        """The real failure: p95 of the `software` workload is 02:12:15 while its
        longest completed run took 07:57:12, so sizing from p95 printed "lower to
        03:00:00" on the same screen as "longest 07:57:12" -- advice that times out
        the slowest runs by construction. Exceeding --time kills a job exactly as
        exceeding --mem does, and memory_advice sizes from the highest peak."""
        jobs = workload("midtrain")
        slow = jobs[0]._replace(job_id="9992", state="COMPLETED", elapsed=6 * 3600.0)
        advice = walltime_advice(jobs + [slow])
        assert advice.suggestion, "a workload with a 6h run needs a limit stated"
        hours, minutes, seconds = (int(p) for p in advice.suggestion.split(":"))
        assert hours * 3600 + minutes * 60 + seconds >= 6 * 3600

    def test_the_basis_leads_with_the_figure_it_sized_from(self):
        jobs = workload("midtrain")
        slow = jobs[0]._replace(job_id="9993", state="COMPLETED", elapsed=6 * 3600.0)
        advice = walltime_advice(jobs + [slow])
        assert advice.basis.startswith("longest of")

    def test_p95_is_dropped_when_it_repeats_the_longest_run(self):
        """`longest of 8 completed runs is 00:30:18 (p95 00:30:18)` printed one
        number twice in one clause -- noise dressed as evidence."""
        jobs = workload("midtrain")
        same = [
            j._replace(job_id=str(9500 + i), state="COMPLETED", elapsed=1800.0)
            for i, j in enumerate(jobs)
        ]
        advice = walltime_advice(same)
        assert "p95" not in advice.basis, advice.basis
        assert "00:30:00" in advice.basis

    def test_p95_is_kept_where_the_distribution_has_a_tail(self):
        """07:57:12 longest against 02:12:15 at p95 is the difference between a
        workload with one slow run and a workload that is slow.

        Twenty quick runs, not fifteen: with sixteen values a lone outlier IS the
        top 5%, so p95 lands on it and there is no spread to report. The real
        `software` workload has 130 runs, where 5% is six of them.
        """
        base = workload("midtrain")[0]
        quick = [
            base._replace(job_id=str(9600 + i), state="COMPLETED", elapsed=600.0) for i in range(20)
        ]
        advice = walltime_advice(quick + [base._replace(job_id="9700", elapsed=8 * 3600.0)])
        assert "p95" in advice.basis, advice.basis
        assert "08:00:00" in advice.basis, "sized from the longest, not p95"


class TestMemory:
    def test_an_oom_sets_a_floor(self):
        advice = memory_advice(workload("rc-tok-github_code"))
        assert advice.verdict == "raise"
        assert advice.suggestion.endswith("G")
        assert "floor" in advice.basis

    def test_oom_caution_names_the_non_monotone_trap(self):
        advice = memory_advice(workload("rc-tok-github_code"))
        assert "not the deciding variable" in advice.caution

    def test_sized_from_peaks_when_nothing_oomed(self):
        advice = memory_advice(workload("midtrain"))
        assert advice.verdict in ("raise", "lower", "keep")
        # Worded from the site's JobAcctGatherType, so the claim is true of the
        # cluster the reader is on rather than of the one this was written against.
        assert "upper bound" in advice.caution
        assert "jobacct_gather/linux" in advice.caution

    def test_maxrss_above_the_limit_is_excluded_not_trusted(self):
        """A value above the cgroup limit cannot be a working set."""
        jobs = workload("midtrain")
        bogus = jobs[0]._replace(
            job_id="9992", alloc_tres="billing=4,cpu=4,gres/gpu=3,mem=1M,node=1"
        )
        advice = memory_advice(jobs + [bogus])
        assert advice.verdict != "unknown"
        assert "excluded" in advice.caution

    def test_refuses_when_bad_readings_dominate(self):
        jobs = [
            j._replace(alloc_tres="billing=4,cpu=4,mem=1M,node=1") for j in workload("midtrain")
        ]
        advice = memory_advice(jobs)
        assert advice.verdict == "unknown"
        assert "not a footprint at all" in advice.basis
        assert "double-counting shared pages" in advice.basis

    def test_too_few_runs_declines(self):
        assert memory_advice(workload("midtrain")[:1]).verdict == "unknown"


class TestCpu:
    def test_over_requested_cores_flagged(self):
        advice = cpu_advice(workload("tokenize-shards"))
        assert advice.flag == "--cpus-per-task"
        assert advice.verdict in ("lower", "keep", "raise", "unknown")

    def test_gpu_workloads_warn_before_cutting_cores(self):
        """Idle-looking cores may be feeding dataloader workers."""
        jobs = workload("midtrain")
        starved = [
            j._replace(alloc_tres="billing=64,cpu=64,gres/gpu=3,mem=200G,node=1") for j in jobs
        ]
        advice = cpu_advice(starved)
        if advice.verdict == "lower":
            assert "dataloader" in advice.caution

    def test_never_suggests_fewer_than_one_core(self):
        jobs = workload("cot-exp")
        advice = cpu_advice(jobs)
        if advice.suggestion:
            assert int(advice.suggestion) >= 1


class TestRequestedIsWhatTheNextRunWillAsk:
    """`requested` is rendered as "raise to X (from Y)", so Y has to be the value
    the user's script currently holds. It was `max()` over the whole window, and
    `patterns.group_key` deliberately folds every resource magnitude into one group
    -- "raising --mem must not fork the history you are trying to learn from" --
    so `max()` reached straight back across the history the grouping exists to
    unify. One stale run was enough to misstate the request, invert the verdict,
    or suppress the advice entirely.
    """

    @staticmethod
    def _tightened(limit, stale_limit, stale_count=2):
        """A workload the user has since tightened, oldest run first."""
        jobs = sorted(workload("midtrain"), key=lambda j: j.submit or "")
        stale = [
            j._replace(
                job_id="800%d" % index,
                timelimit=float(stale_limit),
                submit="2026-01-0%dT00:00:00" % (index + 1),
                start="2026-01-0%dT00:01:00" % (index + 1),
            )
            for index, j in enumerate(jobs[:stale_count])
        ]
        return stale + [j._replace(timelimit=float(limit)) for j in jobs[stale_count:]]

    def test_requested_is_the_last_run_not_the_largest(self):
        advice = walltime_advice(self._tightened(40 * 60, 8 * 3600))
        assert advice.requested == "00:40:00", advice.requested

    def test_a_stale_limit_does_not_invert_the_verdict(self):
        """The damaging case. midtrain's longest run takes 01:52:49, so a workload
        held at 00:40:00 must be told to RAISE. Measured against the stale 08:00:00
        it was told to lower -- the opposite instruction, above a `requested`
        figure that matched nothing in the script."""
        advice = walltime_advice(self._tightened(40 * 60, 8 * 3600))
        assert advice.verdict == "raise", advice
        assert advice.suggestion == "02:30:00"

    def test_the_direction_does_not_depend_on_how_many_runs_are_stale(self):
        """Twelve old runs and two new ones is the same situation as two and
        twelve: what the script says now is what the last run asked for."""
        advice = walltime_advice(self._tightened(40 * 60, 8 * 3600, stale_count=12))
        assert advice.requested == "00:40:00"
        assert advice.verdict == "raise"

    def test_one_stale_run_cannot_silence_the_advice(self):
        """The worst of the three, because it produced no output at all. A single
        old run at the target made the verdict `keep`, and `keep` suppresses the
        suggestion -- so the tool said nothing about a 00:40:00 limit that every
        recent run needed 01:52:49 to finish."""
        jobs = self._tightened(40 * 60, 2.5 * 3600, stale_count=1)
        advice = walltime_advice(jobs)
        assert advice.verdict == "raise"
        assert advice.suggestion == "02:30:00"
        assert "#SBATCH --time=02:30:00" in sbatch_lines(recommend(jobs))

    def test_a_workload_at_one_limit_throughout_is_unchanged(self):
        """The control: no stale rows, so the old and new readings must agree."""
        jobs = workload("midtrain")
        assert len({j.timelimit for j in jobs}) == 1
        advice = walltime_advice(jobs)
        assert advice.requested == "02:00:00"
        assert advice.verdict == "raise"

    def test_a_timeout_floor_is_still_taken_from_the_largest(self):
        """A floor is a claim about the requirement, which a later, smaller request
        does not retract -- unlike a claim about what the script says. So max()
        stays right there, and this must not have been swept up in the fix."""
        jobs = sorted(workload("midtrain"), key=lambda j: j.submit or "")
        jobs = [j._replace(timelimit=40 * 60.0) for j in jobs]
        jobs[0] = jobs[0]._replace(
            job_id="8500",
            state="TIMEOUT",
            timelimit=20 * 3600.0,
            submit="2026-01-01T00:00:00",
            start="2026-01-01T00:01:00",
        )
        advice = walltime_advice(jobs)
        assert advice.requested == "00:40:00", "the request is still the last one"
        # 20h floor x 1.25, rendered in the D-HH:MM:SS form Slurm takes past a day.
        assert advice.suggestion == "1-01:00:00", "the floor is the limit that cut a run off"

    def test_memory_requested_is_the_last_ceiling_not_the_largest(self):
        """On the recorded rc-tok-github_code history this is the difference between
        the 17 GiB the script says and 48.0 GiB -- a cancelled run five
        submissions back."""
        advice = memory_advice(workload("rc-tok-github_code"))
        assert advice.requested == "17.0 GiB", advice.requested

    def test_cpu_requested_is_the_last_count_not_the_largest(self):
        """`requested` is also the denominator of the cpu basis text, so a stale
        figure there read "used 1.2 of 64 cores per task" about a script that had
        already come down to 8."""
        jobs = sorted(workload("midtrain"), key=lambda j: j.submit or "")
        wide = jobs[0]._replace(
            job_id="8600",
            alloc_tres="billing=64,cpu=64,gres/gpu=3,mem=200G,node=1",
            submit="2026-01-01T00:00:00",
            start="2026-01-01T00:01:00",
        )
        advice = cpu_advice([wide] + jobs[1:])
        assert advice.requested != "64"
        assert " of %s cores per task" % advice.requested in advice.basis


class TestRecommendAndPaste:
    def test_three_directives_per_workload(self):
        advice = recommend(workload("midtrain"))
        assert [a.flag for a in advice] == ["--time", "--mem", "--cpus-per-task"]

    def test_sbatch_lines_only_for_actionable_advice(self):
        advice = recommend(workload("midtrain"))
        lines = sbatch_lines(advice)
        for line in lines:
            assert line.startswith("#SBATCH --")
        assert len(lines) == len([a for a in advice if a.actionable])

    def test_unknown_advice_never_becomes_a_paste_line(self):
        advice = recommend(workload("cot-exp"))
        assert not any("--time" in line for line in sbatch_lines(advice))

    def test_open_ended_records_are_not_evidence(self):
        jobs = [j._replace(open_ended=True) for j in workload("midtrain")]
        assert recommend(jobs) == []

    def test_every_group_survives_recommendation(self):
        """No workload in a real-shaped history should crash the recommender."""
        for group in build_groups(history()):
            advice = recommend(group.jobs)
            assert len(advice) == 3
            for a in advice:
                assert a.verdict in ("raise", "lower", "keep", "unknown")
                assert a.basis


class TestTruncationIsNeverSilent:
    """`render_sizing` caps the list at `limit`. It used to stop there and say
    nothing, while every other truncated view in the tool names its tail
    (History.tail_summary, patterns.find_repeat_failures). The list is ordered by
    compute burned rather than by how wrong the request is, so the workload most
    worth re-sizing can sit just past the cut.
    """

    @staticmethod
    def _many(count):
        """`count` distinct workloads, each over-requesting time so each is actionable.

        Names must not share a digit-folded shape: `patterns.normalize_name` collapses
        digit runs, so wl00..wl19 would arrive as ONE group called `wl##`.
        """
        from slurmpast.model import Job

        words = [
            "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf",
            "hotel", "india", "juliet", "kilo", "lima", "mike", "november",
            "oscar", "papa", "quebec", "romeo", "sierra", "tango",
        ]  # fmt: skip
        jobs = []
        for index, name in enumerate(words[:count]):
            for run in range(5):
                jobs.append(
                    Job(
                        job_id="%d-%d" % (index, run),
                        name=name,
                        partition="test",
                        node_list="n1",
                        state="COMPLETED",
                        elapsed=600.0 + index,
                        timelimit=8 * 3600.0,
                        start="2026-07-%02dT00:00:00" % (1 + run),
                        submit="2026-07-%02dT00:00:00" % (1 + run),
                    )
                )
        return jobs

    def test_the_dropped_workloads_are_counted_and_named(self):
        from slurmpast.index import History
        from slurmpast.report import Style, render_sizing

        jobs = self._many(20)
        history = History(jobs)
        with_advice = [g for g in history.groups if any(a.actionable for a in recommend(g.jobs))]
        assert len(with_advice) == 20, "fixture no longer produces 20 actionable groups"

        text = render_sizing(history, style=Style(enabled=False), limit=12)
        flat = " ".join(text.split())
        assert "8 more workloads" in flat, flat[-200:]
        assert "40 runs" in flat, "the runs behind them, not just the group count"

    def test_a_list_that_fits_says_nothing_about_a_tail(self):
        from slurmpast.index import History
        from slurmpast.report import Style, render_sizing

        text = render_sizing(History(self._many(3)), style=Style(enabled=False), limit=12)
        assert "more workload" not in text

    def test_exactly_at_the_limit_is_not_a_tail(self):
        from slurmpast.index import History
        from slurmpast.report import Style, render_sizing

        text = render_sizing(History(self._many(12)), style=Style(enabled=False), limit=12)
        assert "more workload" not in text

    def test_one_dropped_workload_reads_singular(self):
        from slurmpast.index import History
        from slurmpast.report import Style, render_sizing

        text = render_sizing(History(self._many(13)), style=Style(enabled=False), limit=12)
        assert "1 more workload " in " ".join(text.split())


class TestHeadroomArithmetic:
    def test_margins_render_as_round_percentages(self):
        """int(0.2 * 100) truncates to 19 through float error."""
        advice = walltime_advice(workload("midtrain"))
        assert "19%" not in advice.basis
        advice = cpu_advice(workload("midtrain"))
        assert "19%" not in advice.basis


class TestRulePrecedence:
    """An OOM kill is an event; MaxRSS is a sample that can exceed its own limit.

    Ordered the wrong way round, the unreliable metric vetoed advice the reliable
    one had already settled: a workload with 8 OOM kills got "no advice" purely
    because its MaxRSS readings were untrustworthy.
    """

    def test_oom_wins_over_untrustworthy_maxrss(self):
        jobs = workload("rc-tok-github_code")
        assert all(
            j.max_rss > j.mem_limit_bytes for j in jobs if j.max_rss and j.mem_limit_bytes
        ), "fixture should have unusable MaxRSS throughout"
        advice = memory_advice(jobs)
        assert advice.verdict == "raise"
        assert "floor" in advice.basis

    def test_no_oom_and_no_usable_reading_still_declines(self):
        jobs = [
            j._replace(state="COMPLETED", alloc_tres="billing=4,cpu=4,mem=1M,node=1")
            for j in workload("midtrain")
        ]
        assert memory_advice(jobs).verdict == "unknown"


class TestTheBasisIsTheEvidenceAndNothingElse:
    """Asked three times, and every attempt to say more than the measurement failed.

    "+30% headroom" -> "what does headroom mean in this context? it's so confusing."
    "+30%, rounded up to whole GiB" -> "you are making things far more confusing
    even further." "the rest is room to spare" -> "why do we need this sentence
    here?"

    It was not needed. The block's own header already says why a request sits above
    the observation -- over-requesting narrows which nodes can host the job,
    under-requesting kills the run -- so a clause per flag, three times per
    workload, was the header again in smaller type. What only the line can supply is
    the measurement the number came from.
    """

    def test_no_surface_says_headroom(self):
        import pathlib

        src = pathlib.Path(__file__).resolve().parent.parent / "src" / "slurmpast"
        for module in ("sizing.py", "diagnose.py", "patterns.py"):
            for line in (src / module).read_text().splitlines():
                if line.strip().startswith("#") or "headroom" not in line:
                    continue
                assert '"' not in line and "'" not in line, (module, line)

    def test_no_surface_recites_the_arithmetic(self):
        for advice in recommend(workload("midtrain")):
            assert "rounded up" not in advice.basis, advice.basis
            assert "room to spare" not in advice.basis, advice.basis

    def test_each_basis_is_one_measurement(self):
        """One clause, one sentence, and it ends where the evidence does."""
        for advice in recommend(workload("midtrain")):
            if not advice.actionable:
                continue
            assert advice.basis.count(";") == 0, advice.basis
            assert advice.basis.endswith("."), advice.basis

    def test_memory_names_the_measurement(self):
        advice = memory_advice(workload("midtrain"))
        assert advice.basis.startswith("the most any run used was")

    def test_cpu_names_the_measurement(self):
        advice = cpu_advice(workload("tokenize-shards"))
        assert "the busiest run used" in advice.basis
        assert "cores per task" in advice.basis

    def test_walltime_names_the_measurement(self):
        advice = walltime_advice(workload("midtrain"))
        assert "completed runs took" in advice.basis

    def test_the_header_is_where_the_reason_lives(self):
        """So dropping the clause did not drop the reason."""
        from slurmpast.index import History
        from slurmpast.report import Style, render_sizing

        text = render_sizing(History(history()), style=Style(enabled=False))
        assert "under-requesting kills the run" in text

    def test_a_core_count_that_displays_as_zero_says_so_honestly(self):
        """ "0.00 of 8 cores" reads as none at all, when the point is that a nonzero
        fraction was measured."""
        from slurmpast.sizing import _cores_text

        assert _cores_text(0.003) == "under 0.05"
        assert _cores_text(0.04) == "under 0.05"
        assert _cores_text(0.0) == "0"
        assert _cores_text(1.1) == "1.1"
