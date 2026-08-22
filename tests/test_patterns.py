from slurmpast.patterns import (
    find_memory_search,
    find_noop_allocations,
    find_repeat_failures,
    goodput,
    group_key,
    summarize,
)
from slurmpast.sacct import parse
from tests.conftest import make_text, row


def codes(findings):
    return {f.code for f in findings}


def find(findings, code):
    for f in findings:
        if f.code == code:
            return f
    return None


def _timeout(job_id, cpu_seconds, day_index, limit, elapsed):
    """A TIMEOUT run that used ``cpu_seconds`` of CPU. Under 10s is a hang."""
    day = "2026-06-%02d" % (day_index + 1)
    return [
        row(
            JobID=job_id,
            JobName="trainer",
            State="TIMEOUT",
            ExitCode="0:0",
            Submit="%sT01:00:00" % day,
            Start="%sT01:00:01" % day,
            End="%sT01:30:01" % day,
            ElapsedRaw=str(elapsed),
            Elapsed="00:30:00",
            Timelimit=limit,
            ReqCPUS="1",
            AllocTRES="cpu=1,mem=8G,node=1",
            NodeList="n1",
            NTasks="1",
            TotalCPU="%d:%02d" % (int(cpu_seconds) // 60, int(cpu_seconds) % 60),
        ),
        row(
            JobID="%s.batch" % job_id,
            JobName="batch",
            State="TIMEOUT",
            ElapsedRaw=str(elapsed),
            Elapsed="00:30:00",
            NTasks="1",
            TotalCPU="%d:%02d" % (int(cpu_seconds) // 60, int(cpu_seconds) % 60),
            MaxRSS="1000K",
        ),
    ]


class TestGrouping:
    def test_resource_magnitude_excluded_from_identity(self, oom_series):
        """Raising --mem must not fork the history you are trying to learn from."""
        keys = {group_key(j) for j in oom_series}
        assert len(keys) == 1

    def test_name_and_partition_separate_groups(self, cot_exp, oom_job):
        assert group_key(cot_exp) != group_key(oom_job)

    def test_gpu_vs_cpu_separates(self, cot_exp):
        cpu_variant = cot_exp._replace(alloc_tres="billing=6,cpu=6,mem=80G,node=1", req_tres="")
        assert group_key(cot_exp) != group_key(cpu_variant)


class TestRepeatFailure:
    def test_repeated_identical_timeouts_detected(self, repeat_timeouts):
        findings = find_repeat_failures(repeat_timeouts)
        assert "repeat-failure" in codes(findings)

    def test_evidence_names_the_shared_time_limit(self, repeat_timeouts):
        evidence = find(find_repeat_failures(repeat_timeouts), "repeat-failure").evidence
        assert "same --time" in evidence

    def test_action_says_raising_the_limit_will_not_help(self, repeat_timeouts):
        """These runs hung. The generic 'raise --time' advice would be wrong."""
        action = find(find_repeat_failures(repeat_timeouts), "repeat-failure").action
        assert "will not help" in action

    def test_single_failure_is_not_a_pattern(self, cot_exp):
        assert find_repeat_failures([cot_exp]) == []

    def test_healthy_group_not_flagged(self, healthy_job):
        jobs = [healthy_job._replace(job_id=str(i)) for i in range(20)]
        assert find_repeat_failures(jobs) == []

    def test_mostly_successful_group_not_flagged(self, healthy_job, cot_exp):
        # One owner throughout: `group_key` includes the user, and these two
        # fixtures happen to differ there (`youzhi` against an unrecorded ""), which
        # would split the 30 successes away from the 5 failures and leave a group
        # that IS all-failing. The subject here is the success ratio, so the owner
        # is held constant rather than left to the fixtures to decide.
        jobs = [healthy_job._replace(job_id=str(i), name="mix", user="me") for i in range(30)]
        jobs += [cot_exp._replace(job_id="x%d" % i, name="mix", user="me") for i in range(5)]
        assert find_repeat_failures(jobs) == []

    def test_open_ended_records_excluded(self, stale_job):
        jobs = [stale_job._replace(job_id=str(i)) for i in range(20)]
        assert find_repeat_failures(jobs) == []


class TestMemorySearch:
    def test_bisection_detected(self, oom_series):
        assert "memory-search" in codes(find_memory_search(oom_series))

    def test_contradiction_is_reported(self, oom_series):
        """It succeeded at 32G, a value that had already OOM'd twice.

        That is proof --mem was never the deciding variable, and it is the most
        useful thing the tool can say about this series.
        """
        finding = find(find_memory_search(oom_series), "memory-search")
        assert "COMPLETED at" in finding.evidence
        assert "not the deciding variable" in finding.action

    def test_walk_is_shown(self, oom_series):
        finding = find(find_memory_search(oom_series), "memory-search")
        assert "->" in finding.evidence

    def test_contradiction_escalates_to_critical(self, oom_series):
        assert find(find_memory_search(oom_series), "memory-search").severity == "critical"

    def test_too_few_ooms_is_not_a_pattern(self, oom_job):
        assert find_memory_search([oom_job]) == []

    def test_monotone_search_gets_jump_advice(self, oom_series):
        """A patient upward climb with no contradiction gets different advice.

        Job ids must ascend with the request, because submission order is what
        makes a walk monotone -- sorting the objects is not enough, the detector
        re-sorts by job id on purpose.
        """
        ooms = [j for j in oom_series if j.base_state == "OUT_OF_MEMORY" and j.req_mem_bytes]
        ooms.sort(key=lambda j: j.req_mem_bytes)
        monotone = [job._replace(job_id=str(60000000 + index)) for index, job in enumerate(ooms)]
        finding = find(find_memory_search(monotone), "memory-search")
        assert finding is not None
        assert "Jump well past" in finding.action


class TestNoopAllocations:
    def test_detected_and_ranked(self, repeat_timeouts):
        top, all_dead = find_noop_allocations(repeat_timeouts)
        assert len(all_dead) == 12
        assert len(top) <= 10

    def test_ranked_by_gpu_hours(self, repeat_timeouts):
        top, _ = find_noop_allocations(repeat_timeouts)
        hours = [j.gpu_hours for j in top]
        assert hours == sorted(hours, reverse=True)

    def test_healthy_jobs_excluded(self, healthy_job):
        _, dead = find_noop_allocations([healthy_job])
        assert dead == []


class TestGoodput:
    def test_counts_outcomes(self, oom_series):
        stats = goodput(oom_series)
        assert stats["jobs"] == 10
        assert stats["completed"] == 1
        assert stats["failed"] == 8
        assert stats["cancelled"] == 1

    def test_open_ended_records_excluded_from_totals(self, stale_job, healthy_job):
        stats = goodput([stale_job, healthy_job])
        assert stats["jobs"] == 1
        assert stats["excluded_open_records"] == 1
        assert stats["excluded_no_elapsed"] == 0
        # the phantom 62-day, 3-GPU record would have dominated this
        assert stats["gpu_hours_total"] < 10

    def test_a_closed_record_with_no_elapsed_is_not_called_unterminated(self, healthy_job):
        """Both kinds are excluded, but the UI names one of them: "elapsed would
        be now minus start" is simply false about a COMPLETED record that carries
        no Elapsed at all, so the two are counted apart."""
        blank = healthy_job._replace(job_id="9", state="COMPLETED", elapsed=None, steps=())
        stats = goodput([blank, healthy_job])
        assert stats["jobs"] == 1
        assert stats["excluded_open_records"] == 0
        assert stats["excluded_no_elapsed"] == 1

    def test_every_dropped_record_is_accounted_for(self, healthy_job, stale_job):
        blank = healthy_job._replace(job_id="9", state="COMPLETED", elapsed=None, steps=())
        jobs = [blank, stale_job, healthy_job]
        stats = goodput(jobs)
        dropped = stats["excluded_open_records"] + stats["excluded_no_elapsed"]
        assert stats["jobs"] + dropped == len(jobs)

    def test_gpu_goodput_ratio(self, healthy_job, cot_exp):
        stats = goodput([healthy_job, cot_exp])
        assert 0.0 < stats["gpu_goodput"] < 1.0

    def test_noop_hours_tracked(self, repeat_timeouts):
        stats = goodput(repeat_timeouts)
        assert stats["noop_jobs"] == 12
        assert stats["gpu_hours_noop"] > 0

    def test_empty_input_yields_none_not_zero(self):
        stats = goodput([])
        assert stats["gpu_goodput"] is None
        assert stats["completion_rate"] is None


class TestSummarize:
    def test_combines_detectors(self, oom_series, repeat_timeouts):
        findings = summarize(list(oom_series) + list(repeat_timeouts))
        assert "memory-search" in codes(findings)
        assert "repeat-failure" in codes(findings)

    def test_quiet_on_healthy_history(self, healthy_job):
        jobs = [healthy_job._replace(job_id=str(i)) for i in range(40)]
        assert summarize(jobs) == []

    def test_noop_summary_notes_the_ones_already_caught(self, repeat_timeouts):
        quick = [j._replace(elapsed=600.0) for j in repeat_timeouts]
        finding = find(summarize(quick), "noop-allocations")
        assert finding is not None
        assert "already noticed" in finding.evidence


class TestReportVolume:
    """A seven-month history yields 7+ repeat-failure groups at once.

    Printing all of them is the failure mode where volume replaces judgement, so
    the list is ranked by resources burned and capped, with the tail counted.
    """

    def _many_groups(self, repeat_timeouts, count=7):
        jobs = []
        for group in range(count):
            for index, job in enumerate(repeat_timeouts):
                jobs.append(
                    job._replace(
                        job_id="%d%03d" % (group + 1, index),
                        name="workload-" + "abcdefghij"[group],
                    )
                )
        return jobs

    def test_output_is_capped(self, repeat_timeouts):
        findings = find_repeat_failures(self._many_groups(repeat_timeouts))
        shown = [f for f in findings if f.code == "repeat-failure"]
        assert len(shown) == 4

    def test_remainder_is_counted_not_dropped(self, repeat_timeouts):
        findings = find_repeat_failures(self._many_groups(repeat_timeouts))
        tail = [f for f in findings if f.code == "repeat-failure-more"]
        assert len(tail) == 1
        assert "3 further groups" in tail[0].title

    def test_no_tail_note_when_under_the_cap(self, repeat_timeouts):
        findings = find_repeat_failures(self._many_groups(repeat_timeouts, count=2))
        assert not [f for f in findings if f.code == "repeat-failure-more"]

    def test_worst_group_is_kept(self, repeat_timeouts):
        """Ranking is by resources burned, so the GPU-heavy group must survive."""
        jobs = self._many_groups(repeat_timeouts, count=6)
        heavy = [
            j._replace(job_id="99%03d" % i, name="expensive", elapsed=36000.0)
            for i, j in enumerate(repeat_timeouts)
        ]
        findings = find_repeat_failures(jobs + heavy)
        assert "expensive" in findings[0].evidence


class TestMemorySearchUsesTheRealLimit:
    """ReqMem reads "0n" on 2,130 of 6,574 real jobs.

    Keying the memory-search detector off ReqMem made it blind on a third of the
    history -- caught only because the synthetic demo history uses 0n throughout,
    exactly as this cluster's own records do.
    """

    def _series(self, req_mem):
        from slurmpast.sacct import parse
        from tests.conftest import row

        spec = [
            ("48G", "OUT_OF_MEMORY"),
            ("32G", "OUT_OF_MEMORY"),
            ("17G", "OUT_OF_MEMORY"),
            ("12G", "OUT_OF_MEMORY"),
            ("32G", "COMPLETED"),
        ]
        rows = []
        for index, (mem, state) in enumerate(spec):
            jid = 6000000 + index
            rows.append(
                row(
                    JobID=str(jid),
                    JobName="tok",
                    Partition="test",
                    State=state,
                    ExitCode="0:0",
                    End="2026-07-01T01:00:00",
                    ElapsedRaw="1200",
                    TimelimitRaw="480",
                    ReqMem=req_mem,
                    AllocTRES="cpu=16,mem=%s,node=1" % mem,
                    AllocCPUS="16",
                )
            )
            rows.append(
                row(
                    JobID="%d.batch" % jid,
                    JobName="batch",
                    State=state.split()[0],
                    ElapsedRaw="1200",
                    TotalCPU="00:19:00",
                    MaxRSS="12000000K",
                )
            )
        return parse("\n".join(rows))

    def test_detected_when_reqmem_is_zero(self):
        findings = find_memory_search(self._series("0n"))
        assert "memory-search" in {f.code for f in findings}

    def test_still_detected_when_reqmem_is_populated(self):
        findings = find_memory_search(self._series("48Gn"))
        assert "memory-search" in {f.code for f in findings}

    def test_contradiction_reported_from_alloc_tres(self):
        finding = [f for f in find_memory_search(self._series("0n")) if f.code == "memory-search"][
            0
        ]
        assert "COMPLETED at" in finding.evidence
        assert "not the deciding variable" in finding.action


class TestOneWorkloadIsOnePersonsWork:
    """`group_key` had no user in it, and `sacct -u` takes a list.

    Two people's unrelated `run.sh` on one partition became a single fabricated
    workload, and the detector then reported "18 of 18 runs failed; stop
    resubmitting, the failure is deterministic" about something nobody ran
    eighteen times. Nothing in the output names a user, so there was no way to see
    the merge from the screen.
    """

    def test_two_users_are_not_one_workload(self, cot_exp):
        alice = [cot_exp._replace(job_id="a%d" % i, name="run.sh", user="alice") for i in range(6)]
        bob = [cot_exp._replace(job_id="b%d" % i, name="run.sh", user="bob") for i in range(6)]
        assert len({group_key(j) for j in alice + bob}) == 2

    def test_one_user_still_groups_as_before(self, cot_exp):
        runs = [cot_exp._replace(job_id=str(i), name="run.sh", user="alice") for i in range(6)]
        assert len({group_key(j) for j in runs}) == 1

    def test_the_name_is_still_the_first_element(self, cot_exp):
        """Callers read key[0..2] positionally, so the user goes last."""
        assert group_key(cot_exp._replace(name="s1e20"))[0] == "s#e#"


class TestAlreadyOomdMeansAlready:
    """The contradiction sentence makes a checkable claim about time.

    It was tested against the finished set of every OOM'd value, with no regard to
    order, so the EARLIEST run in a group -- one that completed before anything had
    OOM'd at all -- was reported as having "then COMPLETED at a value that had
    already OOM'd". The real history was the opposite: a run that worked, and a
    request that degraded afterwards.
    """

    def _history(self, completed_first):
        """Four runs: one COMPLETED at 32G, three OOM at 48G/32G/64G."""

        def spec(job_id, mem, state):
            return row(
                JobID=job_id,
                JobName="bisect",
                Partition="test",
                User="me",
                State=state,
                ExitCode="0:125" if state == "OUT_OF_MEMORY" else "0:0",
                Submit="2026-03-01T00:00:00",
                Start="2026-03-01T01:00:00",
                End="2026-03-01T02:00:00",
                ElapsedRaw="3600",
                Elapsed="01:00:00",
                Timelimit="04:00:00",
                ReqCPUS="4",
                AllocTRES="cpu=4,mem=%s,node=1" % mem,
                NodeList="n1",
                NTasks="1",
            )

        ooms = [
            ("2", "48G", "OUT_OF_MEMORY"),
            ("3", "32G", "OUT_OF_MEMORY"),
            ("4", "64G", "OUT_OF_MEMORY"),
        ]
        win = ("1" if completed_first else "5", "32G", "COMPLETED")
        specs = [win] + ooms if completed_first else ooms + [win]
        return parse(make_text(*[spec(*s) for s in specs]))

    def test_a_success_before_every_oom_is_not_called_a_contradiction(self):
        findings = find_memory_search(self._history(completed_first=True))
        assert findings, "the bisection itself should still be reported"
        assert "already OOM'd" not in findings[0].evidence, findings[0].evidence

    def test_a_success_after_an_oom_at_the_same_value_still_is(self):
        findings = find_memory_search(self._history(completed_first=False))
        assert "already OOM'd" in findings[0].evidence, findings[0].evidence


class TestTheRepeatFailureActionNamesTheSplitToo:
    """`sizing` and this module reach the same conclusion from the same split, at
    the same half-of-the-timeouts threshold -- and only one of them qualified it.

    `TestTheHangVetoDoesNotSpeakForEveryTimeout` in `test_sizing.py` is the same
    defect, found and fixed in `sizing.py`, and its comment spells out the reason:

        "The veto stands ... but it may not speak for every timeout in the group.
        The threshold is half, so four hangs among eight timeouts fired it, and
        'These runs were blocked, not slow' was then asserted of the other four as
        well ... Name the split, and keep what they proved."

    `find_repeat_failures` made the same claim of the same runs and did not. Four
    hangs and four runs that burned 29:50 of a 30:00 limit produced, on the
    patterns screen and in the workload banner above the rows:

        → 4 of these consumed under 10 CPU-seconds — they hung rather than ran out
          of time. Raising the limit will not help; fix the blocking call.

    while opening any of the other four said "Ran out of wall clock while working
    → Raise --time well above the limit that cut it off." One screen apart, and
    the workload screen shows both at once.

    "Fixed only on one side" is the shape `issues.md` has now named four times, so
    the clause is shared rather than copied: `hung_split_note` lives here and
    `sizing` imports it, because `sizing` already imports from this module and the
    reverse would be a cycle.
    """

    @staticmethod
    def _runs(hung, computing, limit="00:30:00", elapsed=1800):
        rows = []
        for index in range(hung):
            rows += _timeout(("40%02d" % index), 0.5, index, limit, elapsed)
        for index in range(computing):
            rows += _timeout(("50%02d" % index), elapsed - 10, index + 20, limit, elapsed)
        return parse(make_text(*rows))

    def test_the_mixed_case_names_both_groups(self):
        finding = find(find_repeat_failures(self._runs(4, 4)), "repeat-failure")
        assert finding is not None
        assert "4 of these consumed under 10 CPU-seconds" in finding.action
        assert "will not help those" in finding.action, finding.action
        assert "The other 4 did compute" in finding.action, finding.action
        assert "00:30:00" in finding.action, finding.action

    def test_an_all_hang_workload_keeps_the_unqualified_claim(self):
        """The control. Where every timeout hung, "those" qualifies nothing and the
        sentence is the one it always was."""
        finding = find(find_repeat_failures(self._runs(8, 0)), "repeat-failure")
        assert "Raising the limit will not help;" in finding.action, finding.action
        assert "those" not in finding.action, finding.action
        assert "The other" not in finding.action, finding.action

    def test_the_demo_is_unchanged(self):
        """14 of 14 cot-exp runs hung, so the screenshots and the GIF are too."""
        from slurmpast.demo import history

        actions = [
            f.action
            for f in find_repeat_failures(history())
            if "hung rather than" in (f.action or "")
        ]
        assert actions, "the demo lost its hung workload"
        assert "Raising the limit will not help; fix the blocking call." in actions[0]

    def test_both_modules_spend_the_same_clause(self):
        """The drift guard. Two modules, one sentence, and `sizing` is the importer
        because the dependency only runs one way."""
        import pathlib

        from slurmpast.patterns import hung_split_note

        assert hung_split_note(0, []) == ""
        assert hung_split_note(2, [None, None]) == "", "no limit recorded, nothing to claim"
        note = hung_split_note(1, [1800.0])
        assert "The other 1 did compute, and was cut off at 00:30:00" in note

        src = pathlib.Path(__file__).resolve().parent.parent / "src" / "slurmpast"
        sizing = (src / "sizing.py").read_text()
        assert "hung_split_note" in sizing
        assert "did compute, and" not in sizing, "sizing writes the clause itself again"
