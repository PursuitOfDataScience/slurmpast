"""Turning a workload's history into what its next run should request.

This is the tool's purpose: over-requesting narrows which nodes can host a job
and reserves capacity nobody else can use, under-requesting kills the run, and
the past runs of a workload are the evidence for both.

Every guard rail below exists because a naive rule got it wrong on real records.
"""

import pytest

from slurmpast.demo import history
from slurmpast.index import build_groups
from slurmpast.sacct import parse
from slurmpast.sizing import (
    MIN_RUNS,
    cpu_advice,
    memory_advice,
    recommend,
    sbatch_lines,
    walltime_advice,
)
from tests.conftest import make_text, row


def workload(name):
    return [j for j in history() if j.name == name]


def _sized_run(job_id, day, elapsed, cpu_seconds, max_rss, cores, mem_gib, limit_seconds):
    """One COMPLETED run whose every denominator is stated, not inherited.

    `CPUTime` is written explicitly on both rows because `Job.cpu_time` takes the
    largest of the allocation row, `elapsed x cores` and every work step -- so a
    row that omits it inherits nothing, and a row that copies it from elsewhere
    poisons every utilization derived from it.
    """
    cpu_time = elapsed * cores

    def clock(seconds):
        seconds = int(seconds)
        return "%02d:%02d:%02d" % (seconds // 3600, seconds % 3600 // 60, seconds % 60)

    return [
        row(
            JobID=job_id,
            JobName="trainer",
            State="COMPLETED",
            ExitCode="0:0",
            Submit="%sT01:00:00" % day,
            Start="%sT01:00:01" % day,
            End="%sT02:00:01" % day,
            ElapsedRaw=str(elapsed),
            Elapsed=clock(elapsed),
            Timelimit=clock(limit_seconds),
            ReqCPUS=str(cores),
            AllocTRES="cpu=%d,mem=%dG,node=1" % (cores, mem_gib),
            ReqTRES="cpu=%d,mem=%dG,node=1" % (cores, mem_gib),
            ReqMem="%dG" % mem_gib,
            NodeList="n1",
            NTasks="1",
            TotalCPU=clock(cpu_seconds),
            CPUTime=clock(cpu_time),
        ),
        row(
            JobID="%s.batch" % job_id,
            JobName="batch",
            State="COMPLETED",
            ElapsedRaw=str(elapsed),
            Elapsed=clock(elapsed),
            NTasks="1",
            TotalCPU=clock(cpu_seconds),
            CPUTime=clock(cpu_time),
            MaxRSS="%dK" % (max_rss // 1024),
        ),
    ]


def _timeout_run(job_id, cpu_seconds, day, limit="01:00:00"):
    """A run cut off at its limit, having used `cpu_seconds` of CPU.

    Under 10s of CPU is what `looks_like_noop` calls a hang; near the whole limit is
    a run that genuinely needed more wall clock.
    """
    return [
        row(
            JobID=job_id,
            JobName="trainer",
            State="TIMEOUT",
            ExitCode="0:0",
            Submit="%sT01:00:00" % day,
            Start="%sT01:00:01" % day,
            End="%sT02:00:05" % day,
            ElapsedRaw="3605",
            Elapsed="01:00:05",
            Timelimit=limit,
            ReqCPUS="1",
            AllocTRES="cpu=1,mem=8G,node=1",
            NodeList="n1",
            NTasks="1",
            TotalCPU="%d:%02d" % (int(cpu_seconds) // 60, int(cpu_seconds) % 60),
            CPUTime="01:00:05",
        )
    ]


def _cpu_run(job_id, cpus, util, day):
    """A completed run of `cpus` cores per task, busy for `util` of its wall clock."""
    elapsed = 3600
    total_cpu = elapsed * cpus * util
    tres = "cpu=%d,mem=8G,node=1" % cpus
    return [
        row(
            JobID=job_id,
            JobName="trainer",
            State="COMPLETED",
            ExitCode="0:0",
            Submit="%sT01:00:00" % day,
            Start="%sT01:00:01" % day,
            End="%sT02:00:01" % day,
            ElapsedRaw=str(elapsed),
            Elapsed="01:00:00",
            Timelimit="04:00:00",
            ReqCPUS=str(cpus),
            AllocTRES=tres,
            NodeList="n1",
            NTasks="1",
            TotalCPU="%d:%02d" % (int(total_cpu) // 60, int(total_cpu) % 60),
            CPUTime="%02d:00:00" % cpus,
        )
    ]


def _mem_run(job_id, ceiling, state, day, peak=None):
    """One allocation row, plus the batch step that carries MaxRSS when there is one.

    MaxRSS lives on the step rows, not the allocation, so a fixture that sets it
    on the allocation alone produces a job with no memory reading at all -- which
    is a different case from the one under test.
    """
    tres = "cpu=4,mem=%s,node=1" % ceiling
    rows = [
        row(
            JobID=job_id,
            JobName="tok",
            State=state,
            ExitCode="0:125" if state == "OUT_OF_MEMORY" else "0:0",
            Submit="%sT01:00:00" % day,
            Start="%sT01:00:01" % day,
            End="%sT02:00:00" % day,
            Elapsed="01:00:00",
            Timelimit="08:00:00",
            ReqMem="%sn" % ceiling,
            ReqCPUS="4",
            AllocTRES=tres,
            NodeList="n1",
            NTasks="1",
            TotalCPU="00:50:00",
            CPUTime="04:00:00",
        )
    ]
    if peak:
        rows.append(
            row(
                JobID="%s.batch" % job_id,
                JobName="batch",
                State="COMPLETED",
                ExitCode="0:0",
                Elapsed="01:00:00",
                MaxRSS=peak,
                AllocTRES=tres,
                NTasks="1",
                TotalCPU="00:50:00",
                CPUTime="04:00:00",
            )
        )
    return rows


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


class TestAnOomFloorIsNotTheWholeAnswer:
    """A workload that OOM'd and was then FIXED must not be told to cut back.

    The OOM branch used to return with ``verdict`` hard-coded to ``"raise"``,
    having consulted neither what the last run requested nor the runs that
    succeeded after the request went up. So a workload that OOM'd at 16 GiB and
    was raised to 64 GiB was told to "raise to 21G" -- a two-thirds cut, labelled
    as an increase, emitted as a paste-ready ``#SBATCH --mem=21G`` that walks
    straight back into the OOM the user had already fixed. This is issues.md #2
    in the one branch that fix did not reach; ``walltime_advice`` never had it,
    because it folds its TIMEOUT floor into the same target everything else is
    judged against instead of short-circuiting past the comparison.
    """

    def _fixed_history(self, oomed_at="16G", now_at="64G", peak="20971520K"):
        """OOM'd five times at one ceiling, then six clean runs at a higher one."""
        jobs = []
        for index in range(5):
            jobs += _mem_run(
                "40%d" % index, oomed_at, "OUT_OF_MEMORY", "2026-06-%02d" % (index + 1)
            )
        for index in range(6):
            jobs += _mem_run(
                "50%d" % index, now_at, "COMPLETED", "2026-07-%02d" % (index + 1), peak=peak
            )
        return parse(make_text(*jobs))

    def test_a_fixed_workload_is_not_told_to_raise_to_a_smaller_number(self):
        advice = memory_advice(self._fixed_history())
        assert advice.verdict == "lower", advice
        assert advice.requested == "64.0 GiB"

    def test_the_suggestion_still_clears_what_the_successful_runs_used(self):
        """26 GiB covers a 20 GiB peak; the old code said 21G, sized off the floor."""
        advice = memory_advice(self._fixed_history())
        assert advice.suggestion == "26G", advice
        assert "peaked higher still" in advice.basis

    def test_no_sbatch_line_ever_undercuts_the_measured_peak(self):
        """The paste-ready line is the one output a user acts on directly."""
        jobs = self._fixed_history()
        peak = max(j.max_rss for j in jobs if j.max_rss and j.max_rss <= j.mem_limit_bytes)
        lines = [line for line in sbatch_lines(recommend(jobs)) if "--mem" in line]
        assert lines, "expected a --mem line"
        suggested = int(lines[0].split("=")[1].rstrip("G")) * 1024**3
        assert suggested > peak, "%s undercuts the %d-byte peak" % (lines[0], peak)

    def test_a_request_already_at_the_floor_is_left_alone(self):
        """Neither raise nor lower: 'keep' suppresses the suggestion, correctly."""
        advice = memory_advice(self._fixed_history(oomed_at="16G", now_at="21G", peak=None))
        assert advice.verdict == "keep", advice
        assert advice.suggestion == ""

    def test_the_floor_still_holds_when_no_run_has_a_usable_peak(self):
        """With nothing trustworthy to measure, floor-only sizing is all there is."""
        advice = memory_advice(self._fixed_history(oomed_at="40G", now_at="40G", peak=None))
        assert advice.verdict == "raise", advice
        assert advice.suggestion == "52G"
        assert "floor" in advice.basis


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
        """On the rc-tok-github_code history this is the difference between the
        32 GiB the script currently says and 48.0 GiB -- a cancelled run nine
        submissions back, and the largest of the ten.

        This asserted 17.0 GiB, which was neither: it was the ceiling of job
        5100038, which the demo's own scrambled timestamps (`jid % 9`, wrapping
        every ninth job within a day) presented as the most recent attempt. So the
        test that exists to prove `_latest` picks the *last* request was pinned to
        a value `_latest` only returned because the fixture's clock ran backwards
        -- and it would have gone on passing had `_latest` broken. The last run of
        the series is 5100044.
        """
        runs = workload("rc-tok-github_code")
        last = max(runs, key=lambda j: (j.start or j.submit or "", j.job_id))
        assert last.job_id == "5100044", last.job_id
        advice = memory_advice(runs)
        assert advice.requested == "32.0 GiB", advice.requested

    def test_cpu_requested_is_the_last_count_not_the_largest(self):
        """A stale figure read "used 1.2 of 64 cores per task" about a script that
        had already come down to 8.

        `requested` is the last run's ask, and it reaches the screen as "(from X)".
        It is no longer the denominator of the basis sentence: that has to be the
        ceiling the busiest run itself had, or the two halves come from different
        runs and the sentence describes neither. See
        TestTheBasisDescribesOneRun.
        """
        jobs = sorted(workload("midtrain"), key=lambda j: j.submit or "")
        wide = jobs[0]._replace(
            job_id="8600",
            alloc_tres="billing=64,cpu=64,gres/gpu=3,mem=200G,node=1",
            submit="2026-01-01T00:00:00",
            start="2026-01-01T00:01:00",
        )
        advice = cpu_advice([wide] + jobs[1:])
        assert advice.requested != "64"


class TestTheBasisDescribesOneRun:
    """The busiest run's usage, against that same run's own ceiling.

    Pairing the peak with `_latest`'s figure printed "the busiest run used 12.0 of 2
    cores per task" -- six times its own allocation, which cannot happen. Both
    numbers were right; they came from different runs.
    """

    def _mixed_history(self):
        """One old wide run that did the work, three recent narrow ones."""
        jobs = _cpu_run("7000", cpus=16, util=0.75, day="2026-05-01")
        for index in range(3):
            jobs += _cpu_run("80%d" % index, cpus=2, util=0.25, day="2026-07-%02d" % (index + 1))
        return parse(make_text(*jobs))

    def test_the_denominator_is_the_busiest_runs_own_ceiling(self):
        advice = cpu_advice(self._mixed_history())
        assert "of 16 cores per task" in advice.basis, advice.basis

    def test_the_latest_ask_is_still_what_requested_reports(self):
        """The fix must not walk back issues.md #2: "from X" is the current ask."""
        advice = cpu_advice(self._mixed_history())
        assert advice.requested == "2", advice.requested

    def test_the_basis_never_claims_more_cores_than_it_names(self):
        advice = cpu_advice(self._mixed_history())
        used, _, ceiling = advice.basis.partition(" of ")
        used_cores = float(used.rsplit(" ", 1)[-1])
        named = float(ceiling.split()[0])
        assert used_cores <= named, advice.basis


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


class TestTheHangVetoDoesNotSpeakForEveryTimeout:
    """The veto stands; it may not describe runs it did not measure.

    Its threshold is half, so four hangs among eight timeouts fired it -- and
    "These runs were blocked, not slow" was then asserted of the other four too:
    runs that burned nearly their whole limit doing real work. `looks_like_noop`
    needs CPU under 10s, so those are never hangs by this module's own definition.
    """

    def _mixed(self):
        """4 true hangs + 4 compute-bound timeouts + 12 completed runs."""
        rows = []
        for index in range(4):
            rows += _timeout_run("10%d" % index, cpu_seconds=0.5, day="2026-06-%02d" % (index + 1))
        for index in range(4):
            rows += _timeout_run("20%d" % index, cpu_seconds=3590, day="2026-06-1%d" % index)
        for index in range(12):
            rows += _cpu_run("30%d" % index, cpus=1, util=0.9, day="2026-07-%02d" % (index + 1))
        return parse(make_text(*rows))

    def test_the_veto_still_withholds_a_number(self):
        advice = walltime_advice(self._mixed())
        assert advice.verdict == "unknown"
        assert advice.suggestion == ""

    def test_the_basis_names_the_split_instead_of_generalising(self):
        advice = walltime_advice(self._mixed())
        assert "4 of 8 timed-out runs" in advice.basis, advice.basis

    def test_what_the_computing_timeouts_proved_is_not_thrown_away(self):
        advice = walltime_advice(self._mixed())
        assert "The other 4 did compute" in advice.caution, advice.caution
        assert "01:00:00" in advice.caution, advice.caution

    def test_an_all_hang_workload_still_reads_as_before(self):
        advice = walltime_advice(workload("cot-exp"))
        assert advice.verdict == "unknown"
        assert "blocked, not slow" in advice.basis


class TestAHungRunIsNotEvidenceOfNeedingMoreTime:
    """Rule 2 of the module header, applied to the floor and not only to the veto.

    `hangs_dominate` needs three hangs AND half the timeouts AND a fifth of the
    workload, so a *minority* of hangs never reaches it -- and the TIMEOUT floor
    below took `max()` over every timeout regardless. Two hung runs carrying a
    stale `--time=24:00:00` turned "raise to 02:30:00" into "raise to 1-06:00:00"
    for a workload whose longest completed run took an hour: a 12x over-request,
    printed above a basis line still reading "longest ... took 01:00:00".
    """

    @staticmethod
    def _history(hangs=2):
        rows = []
        for index in range(10):
            rows += _cpu_run("9100%d" % index, 1, 0.95, "2026-05-%02d" % (index + 1))
        for index in range(6):
            rows += _timeout_run(
                "9200%d" % index, 3500, "2026-05-%02d" % (index + 11), limit="02:00:00"
            )
        # Oldest, so they cannot move `requested` -- only the floor.
        for index in range(hangs):
            rows += _timeout_run(
                "9300%d" % index, 0, "2026-04-%02d" % (index + 1), limit="24:00:00"
            )
        return parse(make_text(*rows))

    def test_the_floor_comes_from_the_timeouts_that_computed(self):
        advice = walltime_advice(self._history())
        assert advice.verdict == "raise"
        assert advice.suggestion == "02:30:00", "the 02:00:00 limit that cut real work off"

    def test_the_hangs_change_nothing(self):
        """The control: the same history without them has to give the same answer."""
        assert (
            walltime_advice(self._history(hangs=0)).suggestion
            == walltime_advice(self._history(hangs=2)).suggestion
        )

    def test_a_hang_never_reaches_the_paste_ready_line(self):
        jobs = self._history()
        assert "#SBATCH --time=02:30:00" in sbatch_lines(recommend(jobs))

    def test_the_caution_counts_only_what_the_floor_rests_on(self):
        """It said "8 runs timed out, so the requirement is at least the limit that
        cut them off" of a set holding two runs that never computed -- asserting of
        them the one thing this module says a hang can never show."""
        caution = walltime_advice(self._history()).caution
        assert "6 runs timed out while computing" in caution
        assert "2 further timeouts consumed almost no CPU" in caution

    def test_the_veto_still_fires_when_hangs_dominate(self):
        """The other side of the split: this must not have been swept up in the fix."""
        rows = []
        for index in range(6):
            rows += _timeout_run("9400%d" % index, 0, "2026-06-%02d" % (index + 1))
        for index in range(2):
            rows += _timeout_run("9500%d" % index, 3500, "2026-06-%02d" % (index + 11))
        advice = walltime_advice(parse(make_text(*rows)))
        assert advice.verdict == "unknown"
        assert "blocked, not slow" in advice.basis


class TestCoreCountsArePluralisedByTheNumberBesideThem:
    """`"core" if peak < 2` printed "1.5 core busy per task" for every value from
    1.0 to 1.9 -- the one range where the figure is displayed to a decimal and so
    the one range where getting it wrong is visible."""

    @staticmethod
    def _observed(peak_cores, allocated=8):
        rows = []
        for i in range(3):
            rows += _cpu_run(
                str(100 + i), allocated, peak_cores / allocated, "2026-01-0%d" % (i + 1)
            )
        return cpu_advice(parse("\n".join(rows))).observed

    @pytest.mark.parametrize(
        "peak,expected",
        [(1.0, "1.0 core "), (1.5, "1.5 cores"), (1.9, "1.9 cores"), (0.5, "0.5 cores")],
    )
    def test_only_exactly_one_is_singular(self, peak, expected):
        assert self._observed(peak).startswith(expected), self._observed(peak)

    def test_the_denominator_is_pluralised_too(self):
        """ "used 1.0 of 1 cores per task" is the same defect on the other number."""
        rows = []
        for i in range(3):
            rows += _cpu_run(str(100 + i), 1, 1.0, "2026-01-0%d" % (i + 1))
        assert "of 1 cores" not in cpu_advice(parse("\n".join(rows))).basis


class TestTheHungTimeoutCautionParsesOnItsOwn:
    """ "2 further timeouts are left out of that floor" was printed with no
    preceding sentence establishing a floor: below VETO_MIN_COUNT there are hung
    timeouts and no computing ones, so the clause the wording depends on is
    absent."""

    @staticmethod
    def _completed(jid, day):
        return [
            row(
                JobID=str(jid),
                JobName="w",
                State="COMPLETED",
                ExitCode="0:0",
                ElapsedRaw="1800",
                TimelimitRaw="60",
                TotalCPU="00:30:00",
                Start="2026-01-%02dT01:00:00" % day,
                ReqCPUS="4",
                AllocTRES="cpu=4,mem=8G,node=1",
            )
        ]

    def _advice(self, extra):
        rows = []
        for i in range(3):
            rows += self._completed(100 + i, i + 1)
        return walltime_advice(parse("\n".join(rows + extra)))

    def test_no_floor_no_reference_to_one(self):
        caution = self._advice(_timeout_run("200", 2, 10) + _timeout_run("201", 3, 11)).caution
        assert "further" not in caution, caution
        assert "that floor" not in caution, caution
        assert "left out of the figure above" in caution, caution

    def test_a_floor_that_exists_is_still_referred_to(self):
        """The control: with a computing timeout the sentence above does establish
        a floor, and the original wording is the right one."""
        caution = self._advice(_timeout_run("200", 2, 10) + _timeout_run("300", 3500, 12)).caution
        assert "this is a floor, not a fit" in caution, caution
        assert "further timeout" in caution, caution
        assert "left out of that floor" in caution, caution


class TestNoSuggestionFallsBelowWhatTheWorkloadNeeded:
    """The module header's own asymmetry, as a property over generated histories:

        "Over-requesting narrows which nodes can host the job ... Under-requesting
        kills the run."

    Every individual rule is tested above; nothing tested the promise they exist to
    keep. This generates 400 workloads with a known answer -- a planted peak for
    walltime, memory and per-task cores -- and asserts no actionable suggestion
    lands under it. 569 suggestions, none of them below.

    **Build the runs, do not `_replace` a demo job.** `Job.cpu_time` is
    ``max(cpu_time_alloc, elapsed x cores, *[s.cpu_time for s in work_steps])``, so
    a synthetic run made by replacing three fields on a real one keeps that job's
    denominator in two places and every utilization it computes is wrong. The first
    version of this test reported thirteen violations that were all its own
    fixture's. Recorded because the trap is invisible and the next property test
    over `sizing` will walk into it.
    """

    CORES = 8
    MEM_GIB = 64

    def _workload(self, peak_seconds, peak_rss, peak_cores, runs=6):
        """``runs`` completed jobs whose maxima are exactly the three peaks."""
        rows = []
        for index in range(runs):
            # The last run carries every peak; the rest sit below it.
            share = 1.0 if index == runs - 1 else 0.5
            elapsed = int(peak_seconds * share)
            cpu_seconds = peak_cores * elapsed if index == runs - 1 else peak_cores * elapsed * 0.5
            rows += _sized_run(
                job_id="70%02d" % index,
                day="2026-06-%02d" % (index + 1),
                elapsed=elapsed,
                cpu_seconds=cpu_seconds,
                max_rss=int(peak_rss * share),
                cores=self.CORES,
                mem_gib=self.MEM_GIB,
                limit_seconds=peak_seconds * 4,
            )
        return parse(make_text(*rows))

    def test_the_fixture_is_honest_about_its_own_denominator(self):
        """Guard on the guard. If `cpu_time` is not `elapsed x cores` the planted
        peak is not the peak and every assertion below is vacuous."""
        jobs = self._workload(3600, 8 << 30, peak_cores=5)
        for job in jobs:
            assert job.cpu_time == job.elapsed * job.cpu_count, (
                job.job_id,
                job.cpu_time,
                job.elapsed,
                job.cpu_count,
            )
        busiest = max(j.cpu_utilization * j.cpus_per_task for j in jobs)
        assert abs(busiest - 5.0) < 0.01, busiest

    @pytest.mark.parametrize("peak_seconds", [300, 3600, 20000])
    @pytest.mark.parametrize("peak_cores", [1, 3, 7])
    @pytest.mark.parametrize("peak_gib", [1, 9, 40])
    def test_no_actionable_suggestion_lands_under_the_peak(
        self, peak_seconds, peak_cores, peak_gib
    ):
        from slurmpast.duration import parse_bytes, parse_duration

        peak_rss = peak_gib << 30
        jobs = self._workload(peak_seconds, peak_rss, peak_cores)
        for advice in recommend(jobs):
            if not advice.actionable:
                continue
            if advice.flag == "--time":
                got = parse_duration(advice.suggestion)
                assert got >= peak_seconds, (advice.suggestion, peak_seconds)
            elif advice.flag == "--mem":
                got = parse_bytes(advice.suggestion)
                assert got >= peak_rss, (advice.suggestion, peak_gib)
            elif advice.flag == "--cpus-per-task":
                assert int(advice.suggestion) >= peak_cores, (advice.suggestion, peak_cores)

    def test_a_lower_verdict_really_lowers_and_a_raise_really_raises(self):
        """The other half: a verdict that points the wrong way is worse than none."""
        from slurmpast.duration import parse_bytes, parse_duration

        for peak_seconds, peak_cores, peak_gib in ((300, 1, 1), (20000, 7, 40)):
            jobs = self._workload(peak_seconds, peak_gib << 30, peak_cores)
            for advice in recommend(jobs):
                if not advice.actionable:
                    continue
                if advice.flag == "--time":
                    now, then = parse_duration(advice.requested), parse_duration(advice.suggestion)
                elif advice.flag == "--mem":
                    now, then = parse_bytes(advice.requested), parse_bytes(advice.suggestion)
                else:
                    now, then = self.CORES, int(advice.suggestion)
                if now is None or then is None:
                    continue
                if advice.verdict == "lower":
                    assert then < now, (advice.flag, advice.requested, advice.suggestion)
                else:
                    assert then > now, (advice.flag, advice.requested, advice.suggestion)


class TestAnUpwardAdviceCannotExceedTheNode:
    """`--sizing` advised `--cpus-per-task=34` on a partition whose nodes have 28.

    Found on 7 days of all-users data: `twistedBD`, 401 runs, "the busiest run
    used 27.9 of 28 cores per task" -- a correct reading -- and then a
    ready-to-paste line that `sbatch` refuses outright:

        $ sbatch --test-only --partition=broadwl --cpus-per-task=34 …
        allocation failure: Requested node configuration is not available

    The value it recommended raising *from* was already the ceiling. One missing
    guard, not a misjudged feature.

    Only upward advice is clamped. A downward recommendation was verified on that
    same cluster to round-trip through `sbatch --test-only` and complete inside
    the tightened limits, and a ceiling cannot make a smaller number
    unschedulable.
    """

    @staticmethod
    def _saturated(monkeypatch, ceiling, cores=28, busy="27:54:00"):
        from slurmpast import sizing

        monkeypatch.setattr(sizing, "partition_ceiling", lambda name: (ceiling, None))
        rows = []
        for index in range(6):
            rows.append(
                row(
                    JobID=str(9000 + index),
                    JobName="twistedBD",
                    User="u",
                    Partition="broadwl",
                    State="COMPLETED",
                    Submit="2026-08-23T09:00:00",
                    Start="2026-08-23T09:00:00",
                    End="2026-08-23T10:00:00",
                    ElapsedRaw="3600",
                    NCPUS=str(cores),
                    AllocCPUS=str(cores),
                    ReqCPUS=str(cores),
                    NNodes="1",
                    AllocTRES="billing=%d,cpu=%d,mem=100G,node=1" % (cores, cores),
                )
            )
            rows.append(
                row(
                    JobID=str(9000 + index) + ".batch",
                    JobName="batch",
                    State="COMPLETED",
                    ElapsedRaw="3600",
                    TotalCPU=busy,
                    NCPUS=str(cores),
                    AllocCPUS=str(cores),
                )
            )
        return parse(make_text(*rows))

    def test_no_unschedulable_line_is_emitted(self, monkeypatch):
        """The defect as filed: the paste-ready line is what gets submitted."""
        advice = cpu_advice(self._saturated(monkeypatch, 28))
        assert "--cpus-per-task" not in " ".join(sbatch_lines([advice]))

    def test_it_does_not_claim_the_request_is_already_right(self, monkeypatch):
        """Clamping alone turns "raise to 34" into "already about right", which is
        a different wrong answer -- the workload is using 27.9 of 28 and would take
        more. Saturation gets its own verdict so it can say so."""
        advice = cpu_advice(self._saturated(monkeypatch, 28))
        assert advice.verdict == "capped", advice.verdict
        assert advice.actionable is False

    def test_the_caution_names_the_actual_remedy(self, monkeypatch):
        advice = cpu_advice(self._saturated(monkeypatch, 28))
        assert "ceiling of 28 cores per node" in advice.caution, advice.caution
        assert "partition with more cores per node" in advice.caution

    def test_the_measurement_survives(self, monkeypatch):
        """The reading was right and is the evidence for moving partition."""
        advice = cpu_advice(self._saturated(monkeypatch, 28))
        assert "of 28 cores per task" in advice.basis, advice.basis

    def test_a_raise_below_the_ceiling_is_untouched(self, monkeypatch):
        """The control. A partition with room still gets its number."""
        advice = cpu_advice(self._saturated(monkeypatch, 64))
        assert advice.verdict == "raise", advice.verdict
        assert int(advice.suggestion) > 28
        assert int(advice.suggestion) <= 64

    def test_an_unknown_ceiling_changes_nothing(self, monkeypatch):
        """No `sinfo`, or a partition it cannot see, must leave today's behaviour
        alone -- an unclamped number is what shipped, while a wrong clamp would
        suppress advice a user needs."""
        advice = cpu_advice(self._saturated(monkeypatch, None))
        assert advice.verdict == "raise", advice.verdict
        assert advice.suggestion

    def test_a_downward_recommendation_is_never_clamped(self, monkeypatch):
        """Verified end to end on a second cluster, and a ceiling cannot make a
        smaller request unschedulable."""
        idle = self._saturated(monkeypatch, 28, busy="00:30:00")
        advice = cpu_advice(idle)
        assert advice.verdict == "lower", advice.verdict
        assert int(advice.suggestion) < 28


class TestNoDataIsNotAnAllClear:
    """`--sizing`'s only output on a thin history was an affirmative green pass.

    "every workload is already about right, or lacks the runs to say" merges two
    states that mean opposite things, in the screen's most reassuring colour, for
    the state that is actually "I have no idea". Measured on the reporting
    cluster: 61 of 69 workloads dropped, **every one for lack of runs and none
    because it was correctly sized** — so the sentence was 0% its first half and
    100% its second. This is the first thing a new user sees on a new cluster,
    which is the open-box case the whole exercise is about.

    A second omission sat beside it. `hidden_groups` counts only workloads *with*
    advice pushed past the limit, so with 8 shown and 61 dropped it never fires
    and the 61 leave with no tally. Naming a tail is this file's own stated
    standard, met by the branch two lines below the filter that broke it.

    `--json` needed no change: it carries every workload with a per-flag `unknown`
    verdict and a basis saying which state it is in. Purely a render defect.
    """

    def _runs(self, count, name="xtool"):
        rows = []
        for index in range(count):
            rows.append(
                row(
                    JobID=str(48819683 + index),
                    JobName=name,
                    User="u",
                    Partition="build",
                    State="COMPLETED",
                    Submit="2026-08-23T09:00:00",
                    Start="2026-08-23T09:00:00",
                    End="2026-08-23T09:10:00",
                    ElapsedRaw="600",
                    Timelimit="00:15:00",
                    TimelimitRaw="15",
                    ReqMem="6G",
                    NCPUS="1",
                    AllocCPUS="1",
                    NNodes="1",
                    AllocTRES="billing=1,cpu=1,mem=6G,node=1",
                )
            )
            rows.append(
                row(
                    JobID=str(48819683 + index) + ".batch",
                    JobName="batch",
                    State="COMPLETED",
                    ElapsedRaw="600",
                    TotalCPU="00:09:30",
                    NCPUS="1",
                    AllocCPUS="1",
                    MaxRSS="1580836K",
                )
            )
        return parse(make_text(*rows))

    def _screen(self, jobs):
        from slurmpast.index import History
        from slurmpast.report import Style, render_sizing

        return render_sizing(History(jobs), style=Style(enabled=False))

    def test_no_runs_and_all_correctly_sized_do_not_print_the_same_line(self):
        """The test the report asks for by name. Both states leave the screen
        empty; they must not leave the same sentence on it."""
        no_data = self._screen(self._runs(1))
        # Three runs of a request that is already right: judged, and left alone.
        sized = self._screen(
            [
                job._replace(req_mem_bytes=2 * 1024**3, alloc_tres="billing=1,cpu=1,mem=2G,node=1")
                for job in self._runs(3)
            ]
        )
        assert no_data.strip() != sized.strip()

    def test_the_no_data_screen_says_it_has_no_data(self):
        screen = self._screen(self._runs(1))
        assert "no workload has the 3 completed runs" in screen, screen
        assert "already about right" not in screen

    def test_it_counts_what_it_could_not_judge(self):
        """A number, because "some workloads" is the omission being fixed."""
        screen = self._screen(self._runs(1))
        assert "1 workload, 1 run" in screen, screen

    def test_a_shown_workload_does_not_hide_the_unjudged_ones(self):
        """The second omission: with something actionable on screen, the dropped
        workloads had no tally at all."""
        jobs = self._runs(3) + self._runs(1, name="swtwo")
        screen = self._screen(jobs)
        assert "--mem" in screen, "the judged workload should still be shown"
        assert "too few runs to judge" in screen, screen

    def test_a_genuine_all_clear_keeps_its_plain_sentence(self):
        """The control. When every workload really was judged and left alone, the
        reassuring sentence is the true one and must survive."""
        sized = self._screen(
            [
                job._replace(req_mem_bytes=2 * 1024**3, alloc_tres="billing=1,cpu=1,mem=2G,node=1")
                for job in self._runs(3)
            ]
        )
        assert "already about right" in sized, sized
        assert "too few runs" not in sized
