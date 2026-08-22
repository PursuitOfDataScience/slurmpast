import pytest

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
        assert "Do not size --mem from it" in find(diagnose(oom_job), "host-oom").evidence

    def test_rss_above_limit_without_oom_is_its_own_finding(self, healthy_job):
        # The limit must be lowered where the tool actually reads it: AllocTRES.
        inflated = healthy_job._replace(
            req_mem_bytes=None, alloc_tres="billing=4,cpu=4,gres/gpu=3,mem=1M,node=1"
        )
        assert "rss-above-limit" in codes(diagnose(inflated))

    def test_step_spread_is_measured_but_not_reported(self, step_spread_job):
        """The finding said "any tool reading a single step is wrong by that
        factor" -- a remark about other tools, with no action, about a hazard this
        one already avoids: max_rss takes the maximum across steps. The
        measurement stays; the noise goes."""
        assert step_spread_job.rss_step_spread > 100
        assert "rss-step-spread" not in codes(diagnose(step_spread_job))

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

    def test_the_evidence_names_the_code_the_title_names(self):
        """The evidence hardcoded "Exit 1", so a job that exited 3 produced a
        finding titled "Exited 3" whose evidence discussed exit 1 -- two
        different claims in one paragraph."""
        from slurmpast.model import Job

        finding = find(diagnose(Job(job_id="1", state="FAILED", exit_code=3)), "exit-nonzero-nolog")
        assert "Exited 3" in finding.title
        assert "exit 3" in finding.evidence
        assert "Exit 1" not in finding.evidence

    def test_exit_one_keeps_the_python_exception_note(self):
        """Exit 1 really is the generic Python status; that insight survives for
        the code it is actually about."""
        from slurmpast.model import Job

        finding = find(diagnose(Job(job_id="1", state="FAILED", exit_code=1)), "exit-nonzero-nolog")
        assert "Exit 1" in finding.evidence
        assert "Python" in finding.evidence


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


class TestAStateThatAlreadyExplainsTheMissingCpu:
    """ "Find the blocking call" is advice about the user's own code.

    It is only honest when nothing else accounts for a near-zero CPU total. For
    three states something does, and the noop rule was talking over all of them:
    an OOM-killed job got "raise --mem" and "this is not a resource problem" as
    co-equal CRITICAL findings, and NODE_FAIL and PREEMPTED got sent to debug a
    hang that never happened. TIMEOUT was already handled; these three were not.
    """

    def _stalled(self, healthy_job, state):
        """Long wall clock, no CPU to show for it -- the shape looks_like_noop wants."""
        return healthy_job._replace(
            state=state,
            elapsed=1800.0,
            steps=tuple(s._replace(total_cpu=0.0) for s in healthy_job.steps),
        )

    def test_an_oom_kill_is_not_also_a_hang(self, healthy_job):
        found = codes(diagnose(self._stalled(healthy_job, "OUT_OF_MEMORY")))
        assert "host-oom" in found
        assert "noop-allocation" not in found

    def test_a_dead_node_is_named_rather_than_blamed_on_the_job(self, healthy_job):
        verdict = diagnose(self._stalled(healthy_job, "NODE_FAIL"))
        assert "node-failed" in codes(verdict)
        assert "noop-allocation" not in codes(verdict)
        finding = next(f for f in verdict.findings if f.code == "node-failed")
        assert "missing data" in finding.evidence
        assert "Not your code" in finding.action

    def test_preemption_is_named_rather_than_blamed_on_the_job(self, healthy_job):
        verdict = diagnose(self._stalled(healthy_job, "PREEMPTED"))
        assert "preempted" in codes(verdict)
        assert "noop-allocation" not in codes(verdict)

    def test_a_genuine_hang_still_reports_one(self, healthy_job):
        """The suppression is per-state, not a hole in the rule."""
        assert "noop-allocation" in codes(diagnose(self._stalled(healthy_job, "FAILED")))


class TestSigkillOnlyFiresWhenNothingElseExplainsIt:
    """Slurm reaches for SIGKILL on every one of these once KillWait expires, so
    the signal carries no information the state has not already given -- and the
    finding's action, "look for a wrapper or watchdog killing it", sent the reader
    hunting for a phantom when the killer was their own `scancel`, the wall clock
    or the scheduler.

    Severity was the other half. CANCELLED, PREEMPTED and NODE_FAIL are not graded
    as failures anywhere else (`theme.STATE_HEALTH` grades CANCELLED "none"
    because "colouring it red asserts a judgement the data does not support"), yet
    a CRITICAL here made `slurmpast <jobid>` exit 1 on a run the tool had just
    called not a failure.
    """

    @pytest.mark.parametrize(
        "state,explains",
        [
            ("CANCELLED by 1234", "cancelled"),
            ("TIMEOUT", "timeout-working"),
            ("PREEMPTED", "preempted"),
            ("NODE_FAIL", "node-failed"),
            ("OUT_OF_MEMORY", "oom"),
        ],
    )
    def test_the_state_that_explains_the_kill_wins(self, healthy_job, state, explains):
        job = healthy_job._replace(state=state, exit_code=137, signal=9)
        found = codes(diagnose(job))
        assert "sigkill" not in found, found
        # And the finding that does name the killer is still there, so nothing was
        # suppressed into silence.
        assert found, "a state this specific must still produce a finding"

    def test_a_cancelled_job_does_not_exit_one(self, healthy_job):
        """The consequence, not just the finding. A CRITICAL is what the exit code
        is computed from."""
        job = healthy_job._replace(state="CANCELLED by 1234", exit_code=137, signal=9)
        assert not [f for f in diagnose(job).findings if f.severity == CRITICAL]

    def test_an_unexplained_sigkill_still_fires(self, healthy_job):
        """The control. FAILED is the state where nothing else accounts for the
        signal, and it is the one the original test covered -- which is why the
        rule read as working."""
        job = healthy_job._replace(state="FAILED", exit_code=137, signal=9)
        finding = find(diagnose(job), "sigkill")
        assert finding is not None
        assert finding.severity == CRITICAL
        assert "wrapper or watchdog" in finding.action


class TestAdviceIsPasteable:
    def test_the_memory_slack_flag_is_a_value_sbatch_accepts(self, healthy_job):
        """`format_bytes` is a display formatter, so this said `--mem=52.0 GiB`,
        which sbatch rejects. The same defect `format_duration` closed for
        `--time`, and `sizing.memory_advice` got right all along with "%dG"."""
        import re

        from slurmpast.sacct import parse

        from .conftest import _row, make_text

        # 40 GiB peak against a 400 GiB limit: 10% used, 360 GiB never touched --
        # both gates of the memory-slack rule, with a headline of "Try --mem=52".
        job = parse(
            make_text(
                _row(
                    JobID="1",
                    JobName="w",
                    State="COMPLETED",
                    ExitCode="0:0",
                    ElapsedRaw="3600",
                    TimelimitRaw="60",
                    ReqCPUS="8",
                    AllocTRES="cpu=8,mem=400G,node=1",
                ),
                _row(
                    JobID="1.batch",
                    JobName="batch",
                    State="COMPLETED",
                    ExitCode="0:0",
                    ElapsedRaw="3600",
                    TotalCPU="07:00:00",
                    MaxRSS="41943040K",
                ),
            )
        )[0]
        finding = find(diagnose(job), "memory-slack")
        assert finding is not None, codes(diagnose(job))
        flag = re.search(r"--mem=(\S+)", finding.action)
        assert flag, finding.action
        assert re.fullmatch(r"\d+G", flag.group(1)), flag.group(1)


class TestAnOpenRecordSaysWhatSqueueAnswered:
    """`cli._mark_open_records` asks squeue and now records the answer, so telling
    every reader to "confirm against squeue" was sending them to re-run a query the
    tool had already run and thrown away."""

    def test_a_confirmed_live_job_says_so(self, healthy_job):
        job = healthy_job._replace(state="RUNNING", open_ended=True, live=True)
        assert "still there" in find(diagnose(job), "open-record").action

    def test_a_job_squeue_has_never_heard_of_is_called_stale(self, healthy_job):
        job = healthy_job._replace(state="RUNNING", open_ended=True, live=False)
        action = find(diagnose(job), "open-record").action
        assert "never heard of it" in action
        assert "artefact" in action

    def test_no_answer_still_asks_the_reader_to_check(self, healthy_job):
        """The control: squeue unreachable is not the same claim as "no such job",
        and only one of the two is a measurement."""
        job = healthy_job._replace(state="RUNNING", open_ended=True, live=None)
        assert "Confirm against squeue" in find(diagnose(job), "open-record").action


def _interrupted(base, state, cpu=300.0, **kw):
    """``base`` re-stated as a run something outside the job ended.

    Half an hour of wall clock on sixteen cores. ``cpu`` is the CPU-second total:
    the default 300 is 1.0% utilization -- low enough to trip every "you
    over-requested" rule and far too high to look like a hang, which is the shape
    that exposed the contradiction. Pass a fraction for the hang shape instead.
    """
    step = base.steps[0] if base.steps else None
    fields = {
        "state": state,
        "exit_code": 0,
        "signal": 0,
        "elapsed": 1800.0,
        "timelimit": 3600.0,
        "total_cpu_alloc": cpu,
        "alloc_tres": "cpu=16,mem=64G,node=1",
        "alloc_cpus": 16,
    }
    if step is not None:
        fields["steps"] = (step._replace(max_rss=1_000_000, total_cpu=cpu, elapsed=1800.0),)
    fields.update(kw)
    return base._replace(**fields)


class TestNoFindingContradictsTheOneAboveIt:
    """`_cpu_rules` states the rule its own guard was written for:

        "'Find the blocking call' is advice about the user's own code, and it is
        only honest when nothing else already explains the missing CPU time."

    The guard suppressed the noop finding for OUT_OF_MEMORY, NODE_FAIL and
    PREEMPTED -- and then fell straight through to the next rule, because the
    `return` sits on the branch that *fires*. So the wrong advice was not removed,
    it was replaced:

        [WARN] Most allocated cores were idle
               Utilization 1.0% of 16 cores, i.e. about 0.2 cores of real work.
               → Try --cpus-per-task=1, unless those cores feed dataloader workers.

        [WARN] The node failed under this job
               ... a CPU or memory total near zero here is missing data, not a
               measurement.

    Two findings apart: an instruction computed from a number, and the statement
    that the number is not a measurement. `gpu-suspect-idle` infers from the same
    figure and did the same thing.
    """

    # Every rule that reads `cpu_utilization`, and so every rule the guard has to
    # cover. Named here so a new one has to be added to the set or to this list.
    CPU_DERIVED = {"noop-allocation", "cpu-overrequest", "gpu-suspect-idle"}

    @pytest.mark.parametrize("state", ["NODE_FAIL", "PREEMPTED", "BOOT_FAIL", "DEADLINE"])
    @pytest.mark.parametrize("cpu", [0.1, 300.0], ids=["hang-shaped", "low-but-real"])
    def test_no_sizing_advice_is_offered_for_a_run_cut_short(self, healthy_job, state, cpu):
        """Both shapes, because the guard only ever covered one. At 0.1 CPU-seconds
        the noop rule was suppressed and the run fell through to `cpu-overrequest`;
        at 300 the noop rule never fired and `cpu-overrequest` was reached
        directly. The old guard stopped neither."""
        verdict = diagnose(_interrupted(healthy_job, state, cpu=cpu))
        offered = codes(verdict) & self.CPU_DERIVED
        assert not offered, "%s at %s CPU-seconds still gets %s" % (state, cpu, sorted(offered))

    @pytest.mark.parametrize("state", ["NODE_FAIL", "PREEMPTED", "BOOT_FAIL", "DEADLINE"])
    def test_and_something_says_what_actually_happened(self, healthy_job, state):
        """Suppression alone is not the fix -- it was what left BOOT_FAIL with
        "nothing to flag" on a job whose node never booted."""
        verdict = diagnose(_interrupted(healthy_job, state))
        assert verdict.findings, "%s says nothing at all" % state

    def test_the_gpu_measurement_survives_the_guard(self, healthy_job):
        """The control on the GPU half. `gres/gpuutil` is sampled while the job
        runs, so it says what the cards did however the run ended -- only the
        CPU-based *inference* is suppressed."""
        job = _interrupted(
            healthy_job, "NODE_FAIL", cpu=0.1, alloc_tres="cpu=16,mem=64G,node=1,gres/gpu=4"
        )
        assert job.gpu_count == 4
        assert "gpu-suspect-idle" not in codes(diagnose(job))

    def test_a_completed_run_still_gets_its_advice(self, healthy_job):
        """The control that matters most: the guard must not silence the rule on
        the runs it was written for."""
        job = _interrupted(healthy_job, "COMPLETED")
        assert "cpu-overrequest" in codes(diagnose(job))

    def test_cancelled_is_deliberately_not_in_the_set(self, healthy_job):
        """Its finding says the *outcome* is ambiguous, not that the CPU total is
        unreadable, so a cancelled run that used one core of sixteen is still
        evidence about the request. Recorded as a decision, not an omission."""
        from slurmpast.diagnose import _CPU_TIME_ALREADY_EXPLAINED

        assert "CANCELLED" not in _CPU_TIME_ALREADY_EXPLAINED
        assert "cpu-overrequest" in codes(diagnose(_interrupted(healthy_job, "CANCELLED")))


class TestTheExitCodeFindingsAgreeWithEachOther:
    """`exit-nonzero-nolog` said, of any code it was handed:

        "An exit status does not name a cause: exit 127 is indistinguishable from
        a CUDA OOM, a killed worker or a bad argument without the stderr text."

    printed directly beneath a finding that had just named it:

        "A command in the script was not found (exit 127)"

    127 is the shell's "command not found" and 137 is 128+9; each has a rule of its
    own a few lines above. The generic sentence is true of exit 1 and false of both.

    This is the same self-contradiction the code's own comment records fixing
    *within* one finding -- "a finding whose title said 'Exited 3' and whose
    evidence discussed exit 1" -- reappearing between two, because the fix was to
    generalise the sentence rather than to ask whether it was still true.
    """

    @staticmethod
    def _failed(base, code, signal=0):
        return base._replace(state="FAILED", exit_code=code, signal=signal)

    @pytest.mark.parametrize("code,named", [(127, "command-not-found"), (137, "sigkill")])
    def test_the_status_is_not_called_meaningless_when_a_rule_named_it(
        self, healthy_job, code, named
    ):
        verdict = diagnose(self._failed(healthy_job, code))
        assert named in codes(verdict), codes(verdict)
        nolog = find(verdict, "exit-nonzero-nolog")
        assert nolog is not None, "the log is still worth asking for"
        assert "does not name a cause" not in nolog.evidence, nolog.evidence
        assert "indistinguishable" not in nolog.evidence, nolog.evidence
        assert "named above" in nolog.evidence, nolog.evidence
        assert "no log to confirm it" in nolog.title, nolog.title

    def test_the_advice_is_unchanged_because_the_log_is_still_wanted(self, healthy_job):
        nolog = find(diagnose(self._failed(healthy_job, 127)), "exit-nonzero-nolog")
        assert "--log-dir" in nolog.action

    @pytest.mark.parametrize("code", [1, 2, 3, 42])
    def test_an_unnamed_status_keeps_the_sentence_that_is_true_of_it(self, healthy_job, code):
        """The control. Nothing above named these, so the generic wording stands --
        and exit 1 keeps its own more specific line."""
        nolog = find(diagnose(self._failed(healthy_job, code)), "exit-nonzero-nolog")
        assert "but no log was found to explain it" in nolog.title
        assert "indistinguishable" in nolog.evidence
        if code == 1:
            assert "generic Python-exception status" in nolog.evidence


class TestTheTwoStatesDiagnoseHadNeverHeardOf:
    """`BOOT_FAIL` and `DEADLINE` are counted by `Job.failed`, graded "crit" by
    `theme.STATE_HEALTH`, coloured red by `report._STATE_COLOR` and queried by
    `--failed`. `diagnose` mentioned neither, so the only thing on screen was the
    generic noop rule:

        [FAIL] Allocation did essentially nothing
               → Find the blocking call.

    -- sending the reader to debug their own code for a node that never booted. At
    45 seconds it said "nothing to flag" instead, which is worse.
    """

    def test_boot_fail_says_the_node_never_came_up(self, healthy_job):
        finding = find(diagnose(_interrupted(healthy_job, "BOOT_FAIL")), "boot-failed")
        assert finding is not None
        assert "BOOT_FAIL" in finding.evidence
        assert "Not your code" in finding.action

    def test_deadline_distinguishes_itself_from_the_time_limit(self, healthy_job):
        finding = find(diagnose(_interrupted(healthy_job, "DEADLINE")), "deadline")
        assert finding is not None
        assert "--deadline" in finding.evidence
        assert "A longer --time changes nothing" in finding.action

    def test_a_short_boot_fail_is_no_longer_silent(self, healthy_job):
        """The case that said "nothing to flag": too short for any rule to fire."""
        job = _interrupted(healthy_job, "BOOT_FAIL", elapsed=45.0)
        assert "boot-failed" in codes(diagnose(job))

    def test_the_severities_match_the_states_they_are_siblings_of(self, healthy_job):
        """DEADLINE is CRITICAL like both TIMEOUT findings -- `model.py` groups the
        two ("DEADLINE belongs here for the same reason TIMEOUT does") -- and
        BOOT_FAIL is a WARNING like NODE_FAIL, because nothing the submitter did
        caused it. The pair decides `slurmpast <jobid>`'s exit code."""
        deadline = find(diagnose(_interrupted(healthy_job, "DEADLINE")), "deadline")
        boot = find(diagnose(_interrupted(healthy_job, "BOOT_FAIL")), "boot-failed")
        node = find(diagnose(_interrupted(healthy_job, "NODE_FAIL")), "node-failed")
        assert deadline.severity == CRITICAL
        assert boot.severity == node.severity
        assert boot.severity != CRITICAL

    def test_neither_still_says_find_the_blocking_call(self, healthy_job):
        for state in ("BOOT_FAIL", "DEADLINE"):
            verdict = diagnose(_interrupted(healthy_job, state))
            for finding in verdict.findings:
                assert "blocking call" not in finding.action, (state, finding.code)


class TestMentioningNcclIsNotAnNcclFault:
    """`_NCCL_MARKERS` contained the bare substring `"nccl"`.

    Every distributed PyTorch job prints NCCL at startup and at shutdown, so a
    CRITICAL "Collective communication fault" was manufactured out of ordinary
    lines. Measured over 400 real log files: **ten mention NCCL, none of them
    faulted, and every one of the ten drew the finding.** Two of those jobs had a
    genuine CUDA OOM, so the report showed two CRITICALs -- one real, one sending
    the reader to debug an interconnect that was fine.

    Only real logs could show this. Every fixture in this suite passed a string
    that *was* a fault, so the loose marker was never exercised as a false
    positive -- the test below that reads `"nccl timeout"` still passes, because
    that is a fault shape.
    """

    # Verbatim from real logs on this cluster, or from the vendors' own output.
    BENIGN = (
        "[rank0]:[W818 12:54:11.591239218 ProcessGroupNCCL.cpp:1524] Warning: WARNING: "
        "destroy_process_group() was not called before program exit",
        "INFO 08-02 18:49:04 [parallel_state.py:1208] world_size=1 rank=0 local_rank=0 "
        "distributed_init_method=tcp://127.0.0.1:0 backend=nccl",
        "NCCL version 2.19.3+cuda12.1",
        "NCCL INFO Bootstrap : Using eth0:10.50.221.11<0>",
    )

    FAULTS = (
        "[E ProcessGroupNCCL.cpp:828] [Rank 3] Watchdog caught collective operation timeout",
        "torch.distributed.DistBackendError: NCCL error in: ../torch/csrc/distributed/c10d",
        "RuntimeError: NCCL Error 1: unhandled cuda error (ncclUnhandledCudaError)",
        "ncclInternalError: Internal check failed.",
        "NCCL WARN Call to connect returned Connection refused, retrying",
    )

    def _failed(self, healthy_job):
        return healthy_job._replace(state="FAILED", exit_code=1)

    @pytest.mark.parametrize("line", BENIGN)
    def test_a_healthy_run_that_mentions_nccl_draws_no_finding(self, healthy_job, line):
        assert "nccl" in line.lower(), "the fixture must actually mention it"
        assert "nccl" not in codes(diagnose(self._failed(healthy_job), log_text=line))

    @pytest.mark.parametrize("line", FAULTS)
    def test_every_real_fault_shape_is_still_caught(self, healthy_job, line):
        assert "nccl" in codes(diagnose(self._failed(healthy_job), log_text=line)), line

    def test_the_oom_job_gets_one_critical_not_two(self, healthy_job):
        """The case that showed it: a genuine CUDA OOM whose log also carries the
        shutdown warning. One real finding, and no invented second one."""
        log = (
            "torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB\n"
            "[rank0]:[W818 12:54:11 ProcessGroupNCCL.cpp:1524] Warning: WARNING: "
            "destroy_process_group() was not called before program exit\n"
        )
        found = codes(diagnose(self._failed(healthy_job), log_text=log))
        assert "cuda-oom" in found
        assert "nccl" not in found, found

    def test_the_marker_set_holds_no_bare_mention(self):
        """The guard. A marker that a healthy run prints is the whole defect, so
        the shortest way back into it is adding one."""
        from slurmpast.diagnose import _NCCL_MARKERS

        assert "nccl" not in _NCCL_MARKERS
        for marker in _NCCL_MARKERS:
            assert len(marker) > 8, marker


class TestTheTracebackTailEndsWhereTheTracebackEnds:
    """ "Traceback tail from the log" was showing the tail of the *file*.

    Scanning backwards for the last `Traceback` header is right -- a log can hold
    several and the one that killed the job is the last. Taking everything from
    there to EOF was not: a traceback is frequently not the last thing in the
    file. A wrapper retries, torchrun prints its own summary, a shell banner
    follows, slurmstepd adds a line. The trim then kept the header, an ellipsis,
    and the last four lines of the file:

        Traceback (most recent call last):
          ...
        Validation data: disabled (no held-out file provided)
        Wall time: 999999s, will save checkpoint at 999819s
        ------------------------------------------------------------

    Measured on 27,435 readable logs on this machine: 486 contain a traceback and
    **173 of them -- 36% -- rendered a tail that was not the traceback**. One
    finished on `slurmstepd: error: Detected 1 oom-kill event(s)` while the
    traceback's own last line, the one naming the failure, was
    `torch.distributed.elastic.multiprocessing.errors.ChildFailedError:`.

    Only real logs show it. Every fixture in this suite puts the traceback last,
    which is the 64% case that always worked.
    """

    TRACEBACK = (
        "Traceback (most recent call last):\n"
        '  File "/x/train.py", line 42, in <module>\n'
        "    main()\n"
        '  File "/x/train.py", line 30, in main\n'
        "    model.step()\n"
        "RuntimeError: something broke\n"
    )
    AFTER = (
        "=== job exit 1 | Tue Aug 18 08:06:30 CDT 2026 ===\n"
        "Validation data: disabled (no held-out file provided)\n"
        "Wall time: 999999s, will save checkpoint at 999819s\n"
        "------------------------------------------------------------\n"
    )

    def _tail(self, text):
        from slurmpast.diagnose import _traceback_tail

        return _traceback_tail(text)

    def test_output_after_the_traceback_is_not_shown_as_the_traceback(self):
        tail = self._tail("startup\n" + self.TRACEBACK + self.AFTER)
        assert tail.splitlines()[-1] == "RuntimeError: something broke", tail
        assert "Wall time" not in tail
        assert "exit 1 | Tue" not in tail

    def test_a_traceback_at_the_end_of_the_file_is_unchanged(self):
        """The 75% case, which always worked and must keep working."""
        tail = self._tail("startup\n" + self.TRACEBACK)
        assert tail.splitlines()[0].startswith("Traceback")
        assert tail.splitlines()[-1] == "RuntimeError: something broke"

    def test_the_last_traceback_wins_when_there_are_several(self):
        first = self.TRACEBACK.replace("something broke", "the first one")
        text = first + "retrying\n" + self.TRACEBACK + self.AFTER
        tail = self._tail(text)
        assert "the first one" not in tail
        assert tail.splitlines()[-1] == "RuntimeError: something broke"

    def test_a_torchrun_rank_prefix_does_not_hide_the_frames(self):
        """torchrun prefixes every line, so the indentation that tells a frame from
        the exception line sits behind `[rank0]: `. Without stripping it the first
        frame looks unindented and the traceback is cut to one line.

        The header is matched through the same strip, and that half is load-bearing
        on its own: of 27,435 real logs on this machine, three carry only a
        prefixed traceback, and the rule did not fire on them at all -- a job that
        died on `AttributeError: '_OpNamespace' '_moe_C' object has no attribute
        'grouped_topk'` produced no traceback finding whatsoever.
        """
        prefixed = "".join("[rank0]: %s\n" % line for line in self.TRACEBACK.splitlines())
        tail = self._tail(prefixed + self.AFTER)
        assert tail.splitlines()[-1].endswith("RuntimeError: something broke"), tail
        assert len(tail.splitlines()) > 2, tail

    def test_a_torchrun_only_traceback_is_found_at_all(self, healthy_job):
        """The other half of the same strip, and a separate symptom: when *every*
        copy of the traceback is rank-prefixed, the backward header scan used to
        match nothing, so there was no finding at all -- not a truncated one.

        Three real logs on this machine are shaped exactly this way. torchrun
        usually prints its own wrapper traceback unprefixed beside the worker's,
        which is why the other 50 were found; these three are the ones where it
        did not.
        """
        prefixed = "".join("[rank0]: %s\n" % line for line in self.TRACEBACK.splitlines())
        job = healthy_job._replace(state="FAILED", exit_code=1)
        verdict = diagnose(job, log_text="startup\n" + prefixed + self.AFTER)
        finding = find(verdict, "traceback")
        assert finding is not None, "a rank-prefixed traceback is still a traceback"
        assert "RuntimeError: something broke" in finding.evidence

    def test_no_traceback_is_still_nothing(self):
        assert self._tail("just some output\nand more\n") == ""
        assert self._tail("") == ""

    def test_the_finding_shows_it(self, healthy_job):
        """End to end, since the evidence is what a reader sees."""
        job = healthy_job._replace(state="FAILED", exit_code=1)
        verdict = diagnose(job, log_text="startup\n" + self.TRACEBACK + self.AFTER)
        finding = find(verdict, "traceback")
        assert finding is not None
        assert "RuntimeError: something broke" in finding.evidence
        assert "Wall time" not in finding.evidence
