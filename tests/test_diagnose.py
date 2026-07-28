from slurmpast.diagnose import diagnose, looks_like_noop
from slurmpast.model import CRITICAL, INFO


def codes(verdict):
    return {f.code for f in verdict.findings}


def find(verdict, code):
    for f in verdict.findings:
        if f.code == code:
            return f
    return None


class TestTimeoutIsNotEvidenceOfNeedingMoreTime:
    """The correction at the heart of this tool.

    99 of 115 cot-exp runs hit a 30-minute wall having burned a median of 0.56
    CPU-seconds. Advising 'raise --time' there buys longer hangs. Only the CPU
    counter separates a hang from a job that genuinely ran out of clock.
    """

    def test_hung_timeout_is_diagnosed_as_a_hang(self, cot_exp):
        verdict = diagnose(cot_exp)
        assert "timeout-hang" in codes(verdict)
        assert "timeout-real" not in codes(verdict)

    def test_hung_timeout_explicitly_warns_against_raising_time(self, cot_exp):
        action = find(diagnose(cot_exp), "timeout-hang").action
        assert "not raise --time" in action.lower() or "do not raise --time" in action.lower()

    def test_hung_timeout_is_critical(self, cot_exp):
        assert find(diagnose(cot_exp), "timeout-hang").severity == CRITICAL

    def test_working_timeout_is_diagnosed_as_needing_more_time(self, healthy_job):
        working = healthy_job._replace(state="TIMEOUT", elapsed=7200.0, timelimit=7200.0)
        verdict = diagnose(working)
        assert "timeout-real" in codes(verdict)
        assert "timeout-hang" not in codes(verdict)

    def test_working_timeout_warns_elapsed_is_a_lower_bound(self, healthy_job):
        working = healthy_job._replace(state="TIMEOUT", elapsed=7200.0, timelimit=7200.0)
        assert "below" in find(diagnose(working), "timeout-real").action.lower()


class TestNoopDetection:
    def test_long_elapsed_tiny_cpu_is_noop(self, cot_exp):
        assert looks_like_noop(cot_exp) is True

    def test_real_work_is_not_noop(self, healthy_job):
        assert looks_like_noop(healthy_job) is False

    def test_short_job_is_never_noop(self, cot_exp):
        """A 10-second job with little CPU is normal, not a hang."""
        quick = cot_exp._replace(elapsed=10.0)
        assert looks_like_noop(quick) is False

    def test_open_ended_record_is_never_noop(self, stale_job):
        assert looks_like_noop(stale_job) is False

    def test_unmeasurable_cpu_is_not_claimed_as_noop(self, cot_exp):
        blind = cot_exp._replace(steps=())
        assert looks_like_noop(blind) is False

    def test_completed_noop_is_flagged(self, cot_exp):
        completed = cot_exp._replace(state="COMPLETED")
        assert "noop-allocation" in codes(diagnose(completed))


class TestMemory:
    def test_host_oom_flagged(self, oom_job):
        assert "host-oom" in codes(diagnose(oom_job))

    def test_oom_evidence_calls_out_maxrss_above_limit(self, oom_job):
        """MaxRSS 51.25 GiB vs a 40 GiB limit -- the metric is not a footprint."""
        evidence = find(diagnose(oom_job), "host-oom").evidence
        assert "above the hard limit" in evidence

    def test_oom_action_does_not_tell_you_to_trust_maxrss(self, oom_job):
        assert "do not size --mem from it" in find(diagnose(oom_job), "host-oom").evidence

    def test_rss_above_limit_without_oom_is_its_own_finding(self, healthy_job):
        # The limit must be lowered where the tool actually reads it: AllocTRES.
        inflated = healthy_job._replace(
            req_mem_bytes=None, alloc_tres="billing=4,cpu=4,gres/gpu=3,mem=1M,node=1"
        )
        assert "rss-above-limit" in codes(diagnose(inflated))

    def test_step_spread_reported(self, step_spread_job):
        assert "rss-step-spread" in codes(diagnose(step_spread_job))

    def test_cuda_oom_separated_from_host_oom(self, healthy_job):
        failed = healthy_job._replace(state="FAILED", exit_code=1)
        verdict = diagnose(failed, log_text="torch.cuda.OutOfMemoryError: CUDA out of memory.")
        assert "cuda-oom" in codes(verdict)
        assert "host-oom" not in codes(verdict)

    def test_cuda_oom_says_mem_will_not_help(self, healthy_job):
        failed = healthy_job._replace(state="FAILED", exit_code=1)
        verdict = diagnose(failed, log_text="CUDA out of memory")
        assert "raising --mem changes nothing" in find(verdict, "cuda-oom").evidence


class TestRestraint:
    """A tool that comments on a sound request gets ignored on the bad one."""

    def test_healthy_job_gets_no_critical_finding(self, healthy_job):
        verdict = diagnose(healthy_job)
        assert not [f for f in verdict.findings if f.severity == CRITICAL]

    def test_healthy_job_walltime_not_nagged(self, healthy_job):
        """94% of the limit used -- saying anything here is noise."""
        assert "walltime-slack" not in codes(diagnose(healthy_job))

    def test_genuine_walltime_slack_is_flagged(self, healthy_job):
        wasteful = healthy_job._replace(elapsed=100.0, timelimit=129600.0)
        assert "walltime-slack" in codes(diagnose(wasteful))

    def test_walltime_slack_is_only_info(self, healthy_job):
        wasteful = healthy_job._replace(elapsed=100.0, timelimit=129600.0)
        assert find(diagnose(wasteful), "walltime-slack").severity == INFO

    def test_no_log_means_no_cuda_guess(self, healthy_job):
        failed = healthy_job._replace(state="FAILED", exit_code=1)
        verdict = diagnose(failed, log_text=None)
        assert "cuda-oom" not in codes(verdict)
        assert "exit-nonzero-nolog" in codes(verdict)


class TestExitCodes:
    def test_command_not_found(self, healthy_job):
        job = healthy_job._replace(state="FAILED", exit_code=127)
        assert "command-not-found" in codes(diagnose(job))

    def test_sigkill(self, healthy_job):
        job = healthy_job._replace(state="FAILED", exit_code=137, signal=9)
        assert "sigkill" in codes(diagnose(job))

    def test_nccl_marker(self, healthy_job):
        job = healthy_job._replace(state="FAILED", exit_code=1)
        verdict = diagnose(job, log_text="NCCL WARN Watchdog caught collective operation timeout")
        assert "nccl" in codes(verdict)

    def test_nccl_advice_warns_reported_rank_is_the_victim(self, healthy_job):
        job = healthy_job._replace(state="FAILED", exit_code=1)
        verdict = diagnose(job, log_text="nccl timeout")
        assert "victim" in find(verdict, "nccl").action.lower()

    def test_import_error(self, healthy_job):
        job = healthy_job._replace(state="FAILED", exit_code=1)
        verdict = diagnose(job, log_text="ModuleNotFoundError: No module named 'sglang'")
        assert "import-error" in codes(verdict)

    def test_traceback_tail_extracted(self, healthy_job):
        job = healthy_job._replace(state="FAILED", exit_code=1)
        log = "noise\nTraceback (most recent call last):\n  File x\nValueError: bad\n"
        verdict = diagnose(job, log_text=log)
        assert "ValueError: bad" in find(verdict, "traceback").evidence

    def test_cancelled_marked_ambiguous(self, healthy_job):
        job = healthy_job._replace(state="CANCELLED by 940740146")
        assert "cancelled" in codes(diagnose(job))


class TestOpenEndedRecords:
    def test_open_record_flagged_and_explained(self, stale_job):
        verdict = diagnose(stale_job)
        assert "open-record" in codes(verdict)
        assert "now" in find(verdict, "open-record").evidence

    def test_open_record_suppresses_resource_verdicts(self, stale_job):
        """No claim about utilization from a record whose elapsed is fictional."""
        verdict = diagnose(stale_job)
        assert "cpu-overrequest" not in codes(verdict)
        assert "noop-allocation" not in codes(verdict)


class TestCpuAndGpu:
    def test_idle_cores_flagged(self, healthy_job):
        idle = healthy_job._replace(
            steps=tuple(s._replace(total_cpu=60.0) for s in healthy_job.steps)
        )
        assert "cpu-overrequest" in codes(diagnose(idle))

    def test_single_core_job_not_flagged(self, healthy_job):
        one = healthy_job._replace(
            req_cpus=1,
            alloc_tres="billing=1,cpu=1,mem=200G,node=1",
            steps=tuple(s._replace(total_cpu=1.0) for s in healthy_job.steps),
        )
        assert "cpu-overrequest" not in codes(diagnose(one))

    def test_gpu_suspect_idle_is_hedged_not_asserted(self, healthy_job):
        job = healthy_job._replace(
            steps=tuple(s._replace(total_cpu=30.0) for s in healthy_job.steps)
        )
        verdict = diagnose(job)
        finding = find(verdict, "gpu-suspect-idle")
        if finding is not None:
            assert "suggests" in finding.evidence
            assert "Confirm" in finding.action

    def test_no_gpu_rule_for_cpu_job(self, oom_job):
        assert "gpu-suspect-idle" not in codes(diagnose(oom_job))


class TestNodeNote:
    def test_note_appears_when_supplied(self, cot_exp):
        verdict = diagnose(cot_exp, node_note="midway3-0385 failed 19 of 36")
        assert "node-history" in codes(verdict)

    def test_absent_note_adds_nothing(self, cot_exp):
        assert "node-history" not in codes(diagnose(cot_exp))


class TestShortJobsAreNotJudged:
    """Observed on live data: 2- to 43-second jobs were told their cores were idle.

    Interpreter startup, module loads and conda activation dominate a short job,
    so low utilization there is not evidence about the request. Noise like this
    is what trains a user to ignore the tool.
    """

    def test_very_short_job_gets_no_cpu_complaint(self, healthy_job):
        brief = healthy_job._replace(
            elapsed=22.0,
            steps=tuple(
                s._replace(total_cpu=1.4, cpu_time=88.0, elapsed=22.0) for s in healthy_job.steps
            ),
        )
        assert "cpu-overrequest" not in codes(diagnose(brief))

    def test_long_job_still_gets_the_complaint(self, healthy_job):
        long_idle = healthy_job._replace(
            elapsed=3600.0,
            steps=tuple(
                s._replace(total_cpu=60.0, cpu_time=14400.0, elapsed=3600.0)
                for s in healthy_job.steps
            ),
        )
        assert "cpu-overrequest" in codes(diagnose(long_idle))

    def test_short_job_still_reports_real_failures(self, healthy_job):
        """Suppressing utilization noise must not suppress the actual cause."""
        brief_oom = healthy_job._replace(state="OUT_OF_MEMORY", elapsed=20.0)
        assert "host-oom" in codes(diagnose(brief_oom))
