import pytest

from slurmpast import sacct
from slurmpast.model import Step
from slurmpast.sacct import _FIELDS as _FIELDS_FOR_TEST
from slurmpast.sacct import Sacct, SacctError, parse, supported_fields
from tests.conftest import row


class TestStepReconciliation:
    def test_total_cpu_comes_from_batch_step(self, cot_exp):
        """The allocation row carries no TotalCPU on Slurm 20.11.

        Reading it there yields None for every job and silently disables all
        utilization analysis -- which is how a fleet of hung jobs stays invisible.
        """
        assert cot_exp.total_cpu == pytest.approx(0.539)

    def test_max_rss_is_max_across_steps(self, step_spread_job):
        """job 51709094: batch 4108K vs extern 16439052K."""
        assert step_spread_job.max_rss == 16439052 * 1024

    def test_step_spread_is_reported(self, step_spread_job):
        """Between work steps only -- .extern is excluded as structural noise."""
        assert step_spread_job.rss_step_spread == pytest.approx(16439052 / 4108.0)

    def test_no_spread_when_single_reading(self, oom_job):
        assert oom_job.rss_step_spread is None

    def test_extern_excluded_from_spread_but_not_from_peak(self, step_spread_job):
        assert step_spread_job.max_rss == 16439052 * 1024

    def test_steps_attached_to_right_job(self, cot_exp):
        assert len(cot_exp.steps) == 2
        assert cot_exp.batch_step.step_id == "47865145.batch"


class TestOpenEndedRecords:
    def test_missing_end_is_flagged(self, stale_job):
        """job 50108238: State=RUNNING, End=Unknown, 62 days of phantom elapsed."""
        assert stale_job.open_ended is True

    def test_closed_record_is_not_flagged(self, healthy_job):
        assert healthy_job.open_ended is False

    def test_phantom_elapsed_still_parses(self, stale_job):
        # The value is parsed faithfully; it is the *flag* that stops it being summed.
        assert stale_job.elapsed > 60 * 86400


class TestDerivedFields:
    def test_gpu_count_from_alloc_tres(self, cot_exp):
        assert cot_exp.gpu_count == 1

    def test_multi_gpu(self, healthy_job):
        assert healthy_job.gpu_count == 3

    def test_no_gpu(self, oom_job):
        assert oom_job.gpu_count == 0

    def test_cpu_utilization(self, healthy_job):
        # 5h31m39s of CPU against 7h31m16s allocated
        assert healthy_job.cpu_utilization == pytest.approx(0.7349, abs=1e-3)

    def test_utilization_none_when_unmeasurable(self, stale_job):
        assert stale_job.cpu_utilization is None

    def test_walltime_used(self, healthy_job):
        assert healthy_job.walltime_used == pytest.approx(6769 / 7200.0)

    def test_gpu_hours(self, healthy_job):
        assert healthy_job.gpu_hours == pytest.approx(6769 * 3 / 3600.0)

    def test_fs_disk_parsed_from_tres(self, healthy_job):
        assert healthy_job.fs_disk_bytes == 112710599158

    def test_base_state_strips_cancelled_uid(self):
        rows = parse(row(JobID="9001", JobName="j", State="CANCELLED by 940740146"))
        assert rows[0].base_state == "CANCELLED"

    def test_req_mem_scope(self, oom_job):
        assert oom_job.req_mem_scope == "node"
        assert oom_job.req_mem_bytes == 40 * 1024**3


class TestArrayAndHetJobs:
    def test_array_task_steps_group_correctly(self):
        text = "\n".join(
            [
                row(JobID="123_4", JobName="arr", State="COMPLETED", ExitCode="0:0"),
                row(
                    JobID="123_4.batch",
                    JobName="batch",
                    State="COMPLETED",
                    ExitCode="0:0",
                    Elapsed="00:10:00",
                    CPUTime="00:40:00",
                    MaxRSS="1024K",
                ),
            ]
        )
        jobs = parse(text)
        assert len(jobs) == 1
        assert jobs[0].job_id == "123_4"
        assert len(jobs[0].steps) == 1

    def test_het_job_component_is_its_own_allocation(self):
        text = row(JobID="500+0", JobName="het", State="COMPLETED", ExitCode="0:0")
        jobs = parse(text)
        assert jobs[0].job_id == "500+0"


class TestFieldProbing:
    def test_unsupported_optional_fields_dropped(self):
        """Slurm 20.11 rejects the whole query if one field is unknown.

        So optional fields must be filtered against --helpformat, not requested
        hopefully.
        """
        probe = "JobID JobName User Account Partition State ExitCode Elapsed Timelimit "
        probe += "ReqMem ReqCPUS AllocTRES ReqTRES NodeList TotalCPU CPUTime MaxRSS "
        probe += "Submit Eligible Start End"
        sacct = Sacct(probe=probe)
        fields = sacct.fields
        assert "WorkDir" not in fields
        assert "Constraints" not in fields
        assert "JobID" in fields
        assert "MaxRSS" in fields

    def test_supported_fields_parses_helpformat(self):
        names = supported_fields("JobID JobName  WorkDir\nMaxRSS,Elapsed")
        assert {"jobid", "jobname", "workdir", "maxrss", "elapsed"} <= names

    def test_mandatory_fields_survive_missing_probe(self):
        sacct = Sacct(probe="JobID")
        assert "Elapsed" in sacct.fields

    def test_query_builds_expected_command(self):
        calls = []

        def runner(args):
            calls.append(args)
            return ""

        sacct = Sacct(runner=runner, probe="JobID JobName Elapsed")
        sacct.jobs(["123"])
        assert calls[0][0] == "sacct"
        assert "--parsable2" in calls[0]
        assert "-j" in calls[0] and "123" in calls[0]

    def test_empty_job_list_does_not_call_sacct(self):
        def runner(args):
            raise AssertionError("should not be called")

        assert Sacct(runner=runner, probe="JobID").jobs([]) == []

    def test_runner_failure_raises(self):
        def runner(args):
            raise SacctError("boom")

        with pytest.raises(SacctError):
            Sacct(runner=runner, probe="JobID").history(user="x", since="-1days")


class TestParserRobustness:
    def test_header_line_ignored(self):
        text = "JobID|JobName\n" + row(JobID="77", JobName="x", State="COMPLETED")
        jobs = parse(text)
        assert len(jobs) == 1
        assert jobs[0].job_id == "77"

    def test_blank_lines_ignored(self):
        text = "\n\n" + row(JobID="78", JobName="y", State="FAILED", ExitCode="1:0") + "\n\n"
        assert len(parse(text)) == 1

    def test_short_rows_do_not_crash(self):
        """A row with fewer columns than the field list defaults the rest.

        This was `assert parse(text) == parse(text)` -- a call compared with itself,
        which can only fail if `parse` raises. It is the only test that feeds a row
        shorter than `_FIELDS`, so `get`'s bounds check had nothing holding it:
        turning `return ""` into a wraparound read (`row[pos % len(row)]`) corrupted
        every field past the row's end and the whole suite still passed.

        The three columns present are JobID, JobIDRaw and JobName, in that order.
        """
        jobs = parse("79|z|COMPLETED")
        assert len(jobs) == 1
        job = jobs[0]
        assert (job.job_id, job.job_id_raw, job.name) == ("79", "z", "COMPLETED")
        # Past the row's own end: defaulted, not read from a column that is not there.
        assert job.state == ""
        assert job.user == ""
        assert job.node_list == ""
        assert job.elapsed is None
        assert job.timelimit is None
        assert job.max_rss is None
        assert job.steps == ()

    def test_a_field_list_without_jobid_reports_rather_than_crashing(self):
        """Every row is keyed by JobID. Without it this raised a bare KeyError
        from inside the row loop, which reads as a parser bug rather than as the
        caller's mistake it is."""
        with pytest.raises(SacctError, match="JobID"):
            parse("a|b", fields=["JobName", "State"])

    def test_orphan_step_without_allocation_is_dropped(self):
        """A step whose allocation row is absent must not invent a job."""
        text = row(JobID="999.batch", JobName="batch", State="COMPLETED")
        assert parse(text) == []

    def test_exit_code_and_signal(self):
        text = row(JobID="80", JobName="k", State="FAILED", ExitCode="137:9")
        job = parse(text)[0]
        assert job.exit_code == 137
        assert job.signal == 9


class TestMemoryLimitPrecedence:
    """ReqMem reads 0n on 2,130 of 6,574 real jobs -- the most common value.

    Reading it as a limit produces `limit 0 B`, which then makes every MaxRSS
    look like an overrun and emits a confident false accusation. seff reads
    ReqMem. The truth is in AllocTRES.
    """

    def _job(self, req_mem="0n", alloc="billing=6,cpu=6,gres/gpu=1,mem=80G,node=1", req_tres=""):
        return parse(
            row(
                JobID="9100",
                JobName="j",
                Partition="test",
                State="TIMEOUT",
                ExitCode="0:0",
                End="2026-01-01T00:30:00",
                Elapsed="00:30:00",
                Timelimit="00:30:00",
                ReqMem=req_mem,
                ReqCPUS="6",
                AllocTRES=alloc,
                ReqTRES=req_tres,
                NodeList="midway3-0385",
            )
        )[0]

    def test_zero_reqmem_is_none_not_zero(self):
        assert self._job(req_mem="0n").req_mem_bytes is None

    def test_alloc_tres_supplies_the_real_limit(self):
        assert self._job(req_mem="0n").mem_limit_bytes == 80 * 1024**3

    def test_alloc_tres_wins_over_reqtres_default(self):
        """ReqTRES shows DefMemPerCPU x cores (22860M), not the 80G granted."""
        job = self._job(req_mem="0n", req_tres="billing=6,cpu=6,mem=22860M,node=1")
        assert job.mem_limit_bytes == 80 * 1024**3

    def test_reqmem_used_when_alloc_tres_has_no_mem(self):
        job = self._job(req_mem="40Gn", alloc="billing=6,cpu=6,node=1")
        assert job.mem_limit_bytes == 40 * 1024**3

    def test_reqtres_is_last_resort(self):
        job = self._job(req_mem="0n", alloc="cpu=6", req_tres="cpu=6,mem=22860M")
        assert job.mem_limit_bytes == 22860 * 1024**2

    def test_no_memory_anywhere_is_none(self):
        assert self._job(req_mem="0n", alloc="cpu=6", req_tres="cpu=6").mem_limit_bytes is None

    def test_no_false_overrun_when_limit_unknown(self):
        """The bug this closes: limit 0 B made a 59 GiB MaxRSS an 'overrun'."""
        from slurmpast.diagnose import diagnose

        job = self._job(req_mem="0n", alloc="cpu=6", req_tres="cpu=6")
        job = job._replace(
            steps=(
                Step(
                    step_id="9100.batch",
                    name="batch",
                    state="TIMEOUT",
                    exit_code=0,
                    signal=None,
                    elapsed=1800.0,
                    total_cpu=0.5,
                    cpu_time=10800.0,
                    max_rss=59 * 1024**3,
                ),
            )
        )
        codes = {f.code for f in diagnose(job).findings}
        assert "rss-above-limit" not in codes


class TestStateFilterNeedsEndTime:
    """`sacct --state=X` returns ZERO rows unless -E is also passed.

    Verified on Slurm 20.11.8: `-S 2026-07-01 --state=TIMEOUT` yields nothing
    while 15 such jobs exist; adding `-E now` returns all 15. It does not warn.
    A post-mortem tool that omits -E reports "no failures" and is believed.
    """

    def _captured(self, **kwargs):
        calls = []

        def runner(args):
            calls.append(args)
            return ""

        Sacct(runner=runner, probe=" ".join(_FIELDS_FOR_TEST)).history(**kwargs)
        return calls[0]

    def test_state_filter_always_gets_an_end_time(self):
        args = self._captured(user="u", since="-7days", states=["TIMEOUT"])
        assert "--state" in args
        assert "-E" in args
        assert args[args.index("-E") + 1] == "now"

    def test_explicit_until_is_respected(self):
        args = self._captured(user="u", since="-7days", states=["FAILED"], until="2026-07-28")
        assert args[args.index("-E") + 1] == "2026-07-28"

    def test_no_end_time_injected_without_a_state_filter(self):
        args = self._captured(user="u", since="-7days")
        assert "-E" not in args

    def test_multiple_states_joined(self):
        args = self._captured(user="u", since="-1days", states=["FAILED", "TIMEOUT"])
        assert args[args.index("--state") + 1] == "FAILED,TIMEOUT"


class TestWhoTheQueryIsAbout:
    """`--allusers` existed in `history` but nothing could reach it: the CLI ran
    `args.user or getpass.getuser()`, so the empty-string sentinel became your own
    name and `-u ""` reported *your* jobs while looking like it asked for everyone's.
    """

    def _captured(self, **kwargs):
        calls = []

        def runner(args):
            calls.append(args)
            return ""

        Sacct(runner=runner, probe=" ".join(_FIELDS_FOR_TEST)).history(**kwargs)
        return calls[0]

    def test_one_user(self):
        args = self._captured(user="alice", since="-7days")
        assert args[args.index("-u") + 1] == "alice"
        assert "--allusers" not in args

    def test_a_comma_separated_list_goes_through_untouched(self):
        """`sacct -u` takes a list; splitting it here would only be able to
        re-join it."""
        args = self._captured(user="alice,bob", since="-7days")
        assert args[args.index("-u") + 1] == "alice,bob"

    def test_all_users_spans_the_cluster(self):
        args = self._captured(all_users=True, since="-7days")
        assert "--allusers" in args
        assert "-u" not in args

    def test_all_users_wins_over_a_leftover_user(self):
        args = self._captured(all_users=True, user="alice", since="-7days")
        assert "--allusers" in args
        assert "-u" not in args

    def test_the_empty_string_is_still_the_older_spelling_of_all_users(self):
        args = self._captured(user="", since="-7days")
        assert "--allusers" in args
        assert "-u" not in args

    def test_no_user_at_all_lets_sacct_default_to_the_caller(self):
        args = self._captured(since="-7days")
        assert "-u" not in args
        assert "--allusers" not in args


class TestSentinelsAreNotNames:
    """The sentinel table is a claim about a measurement, not about a name.

    `Reason` really does read "none", `Timelimit` really does read "UNLIMITED",
    `End` really does read "Unknown". But nothing stops a job being *named* `None`
    -- which is what an f-string over an unset variable produces -- or a partition
    being called `unknown`. Blanking those threw away the only thing identifying
    the record, and since `job.name` feeds `patterns.group_key`, such a job stopped
    being itself and joined the bucket of jobs that never had a name.
    """

    def test_a_job_really_named_none_keeps_its_name(self):
        job = parse(row(JobID="1", JobName="None", State="COMPLETED", ExitCode="0:0"))[0]
        assert job.name == "None"

    def test_a_partition_really_called_unknown_keeps_its_name(self):
        job = parse(
            row(JobID="1", JobName="w", Partition="unknown", State="COMPLETED", ExitCode="0:0")
        )[0]
        assert job.partition == "unknown"

    def test_two_such_jobs_do_not_collide_with_the_unnamed(self):
        from slurmpast.patterns import group_key

        named = parse(row(JobID="1", JobName="None", State="COMPLETED", ExitCode="0:0"))[0]
        blank = parse(row(JobID="2", JobName="", State="COMPLETED", ExitCode="0:0"))[0]
        assert group_key(named) != group_key(blank)

    def test_a_real_sentinel_is_still_blanked(self):
        """Where sacct genuinely speaks for itself, nothing changes."""
        job = parse(
            row(
                JobID="1",
                JobName="w",
                State="COMPLETED",
                ExitCode="0:0",
                Timelimit="UNLIMITED",
                End="Unknown",
            )
        )[0]
        assert job.timelimit is None
        assert not job.end


class TestAnInjectedRunnerIsUsedForTheProbeToo:
    """`supported_fields` shelled out to the module-level `_run` unconditionally,
    so `Sacct(runner=...)` -- a recorded history being replayed, or a remote
    cluster reached over ssh -- negotiated its field list against whatever sacct
    was on the local PATH while every real query went to the injected runner.

    Trap 1 at the top of the module is why that is not a degraded answer: one
    unknown field makes sacct reject the entire query, so probing the wrong Slurm
    produces no answer at all.
    """

    @staticmethod
    def _spies(monkeypatch):
        escaped, injected = [], []

        def module_run(args):
            escaped.append(list(args))
            return "JobID JobName User State"

        def mine(args):
            injected.append(list(args))
            return "JobID JobName User State" if "--helpformat" in args else ""

        monkeypatch.setattr(sacct, "_run", module_run)
        return injected, escaped, mine

    def test_the_probe_goes_to_the_injected_runner(self, monkeypatch):
        injected, escaped, mine = self._spies(monkeypatch)
        sacct.Sacct(runner=mine).history(user="alice", since="now-1day")
        assert escaped == [], escaped
        assert ["sacct", "--helpformat"] in injected, injected

    def test_the_query_still_goes_there_as_well(self, monkeypatch):
        injected, _escaped, mine = self._spies(monkeypatch)
        sacct.Sacct(runner=mine).history(user="alice", since="now-1day")
        assert any("-u" in call for call in injected), injected

    def test_an_explicit_probe_still_wins(self, monkeypatch):
        """The control: `probe=` is canned --helpformat text and short-circuits the
        call entirely, so neither runner is asked."""
        injected, escaped, mine = self._spies(monkeypatch)
        sacct.Sacct(runner=mine, probe="JobID,JobName,State").history(user="alice")
        assert escaped == []
        assert ["sacct", "--helpformat"] not in injected, injected

    def test_no_runner_at_all_still_shells_out(self, monkeypatch):
        """The other control: the default is unchanged for a caller that injects
        nothing."""
        _injected, escaped, _mine = self._spies(monkeypatch)
        sacct.Sacct().history(user="alice")
        assert ["sacct", "--helpformat"] in escaped, escaped
