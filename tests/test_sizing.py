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


class TestTheBasisCanBeReproduced:
    """Asked of "+30% headroom": "what does headroom mean in this context? it's so
    confusing." It said neither what the 30% was a percentage OF nor that it had
    already been applied to the figure beside it -- and it did not get you there.
    Every basis now states each step, and the steps reach the printed number.
    """

    def test_no_surface_still_says_headroom(self):
        import pathlib

        src = pathlib.Path(__file__).resolve().parent.parent / "src" / "slurmpast"
        for module in ("sizing.py", "diagnose.py", "patterns.py"):
            text = (src / module).read_text()
            # Comments may explain the word; no string a reader sees may use it.
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or "headroom" not in line:
                    continue
                assert '"' not in line and "'" not in line, (module, line)

    def test_memory_names_the_rounding_that_produces_the_figure(self):
        advice = memory_advice(workload("midtrain"))
        assert "rounded up to whole GiB" in advice.basis
        assert "headroom" not in advice.basis

    def test_cpu_names_the_rounding_that_produces_the_figure(self):
        """The worst of the three: 1.0 core plus 20% is 1.2, and the advice is 2.
        The ceiling to a whole core was doing the work and went unmentioned."""
        advice = cpu_advice(workload("tokenize-shards"))
        assert "rounded up to a whole core" in advice.basis
        assert "headroom" not in advice.basis

    def test_walltime_names_the_step_it_rounded_to(self):
        advice = walltime_advice(workload("midtrain"))
        assert "rounded up to the next" in advice.basis
        assert "minutes" in advice.basis
        assert "headroom" not in advice.basis

    def test_the_walltime_step_matches_the_magnitude(self):
        from slurmpast.sizing import _walltime_step

        assert _walltime_step(1800) == "5 minutes"
        assert _walltime_step(7200) == "15 minutes"

    def test_a_core_count_that_displays_as_zero_says_so_honestly(self):
        """ "0.00 of 8 cores, rounded up to a whole core" cannot yield the 1 printed
        beside it -- rounding zero up is zero. Any nonzero fraction of a core rounds
        up to exactly one, so that is what it claims."""
        from slurmpast.sizing import _cores_text

        assert _cores_text(0.003) == "under 0.05"
        assert _cores_text(0.04) == "under 0.05"
        assert _cores_text(0.0) == "0"
        assert _cores_text(1.1) == "1.1"

    def test_an_exactly_idle_workload_names_the_floor(self):
        """There the ceiling really does give zero, and a floor supplies the 1."""
        # total_cpu is derived from the steps, so the steps are what to zero.
        jobs = [
            j._replace(steps=tuple(st._replace(total_cpu=0.0) for st in j.steps))
            for j in workload("midtrain")
        ]
        advice = cpu_advice(jobs)
        if advice.suggestion == "1":
            assert "never below one core" in advice.basis, advice.basis
