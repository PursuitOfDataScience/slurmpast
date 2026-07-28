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
        assert "MaxRSS over-reports" in advice.caution

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
        assert "double-counts shared pages" in advice.basis

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
