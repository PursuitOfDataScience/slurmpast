from slurmpast.patterns import (
    find_memory_search,
    find_noop_allocations,
    find_repeat_failures,
    goodput,
    group_key,
    summarize,
)


def codes(findings):
    return {f.code for f in findings}


def find(findings, code):
    for f in findings:
        if f.code == code:
            return f
    return None


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
        jobs = [healthy_job._replace(job_id=str(i), name="mix") for i in range(30)]
        jobs += [cot_exp._replace(job_id="x%d" % i, name="mix") for i in range(5)]
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
        ooms = [
            j for j in oom_series if j.base_state == "OUT_OF_MEMORY" and j.req_mem_bytes
        ]
        ooms.sort(key=lambda j: j.req_mem_bytes)
        monotone = [
            job._replace(job_id=str(60000000 + index)) for index, job in enumerate(ooms)
        ]
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
        # the phantom 62-day, 3-GPU record would have dominated this
        assert stats["gpu_hours_total"] < 10

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
        from tests.conftest import row
        from slurmpast.sacct import parse

        spec = [("48G", "OUT_OF_MEMORY"), ("32G", "OUT_OF_MEMORY"),
                ("17G", "OUT_OF_MEMORY"), ("12G", "OUT_OF_MEMORY"),
                ("32G", "COMPLETED")]
        rows = []
        for index, (mem, state) in enumerate(spec):
            jid = 6000000 + index
            rows.append(row(JobID=str(jid), JobName="tok", Partition="test", State=state,
                            ExitCode="0:0", End="2026-07-01T01:00:00", ElapsedRaw="1200",
                            TimelimitRaw="480", ReqMem=req_mem,
                            AllocTRES="cpu=16,mem=%s,node=1" % mem, AllocCPUS="16"))
            rows.append(row(JobID="%d.batch" % jid, JobName="batch", State=state.split()[0],
                            ElapsedRaw="1200", TotalCPU="00:19:00", MaxRSS="12000000K"))
        return parse("\n".join(rows))

    def test_detected_when_reqmem_is_zero(self):
        findings = find_memory_search(self._series("0n"))
        assert "memory-search" in {f.code for f in findings}

    def test_still_detected_when_reqmem_is_populated(self):
        findings = find_memory_search(self._series("48Gn"))
        assert "memory-search" in {f.code for f in findings}

    def test_contradiction_reported_from_alloc_tres(self):
        finding = [f for f in find_memory_search(self._series("0n"))
                   if f.code == "memory-search"][0]
        assert "COMPLETED at" in finding.evidence
        assert "not the deciding variable" in finding.action
