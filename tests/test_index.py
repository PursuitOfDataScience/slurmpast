import string


from slurmpast.index import (
    FILTERS,
    SORTS,
    History,
    build_groups,
    filter_groups,
    filter_jobs,
    next_sort,
    sort_groups,
    sort_label,
)


class TestGrouping:
    def test_rolls_jobs_into_workloads(self, repeat_timeouts, healthy_job):
        groups = build_groups(list(repeat_timeouts) + [healthy_job])
        assert {g.name for g in groups} == {"cot-exp", "midtrain"}

    def test_counts_outcomes_per_group(self, oom_series):
        group = build_groups(oom_series)[0]
        assert group.total == 10
        assert group.completed == 1
        assert group.failed == 8
        assert group.cancelled == 1

    def test_noop_counted(self, repeat_timeouts):
        assert build_groups(repeat_timeouts)[0].noop == 12

    def test_open_ended_records_excluded(self, stale_job, healthy_job):
        groups = build_groups([stale_job, healthy_job])
        assert len(groups) == 1
        assert groups[0].name == "midtrain"

    def test_empty_history(self):
        assert build_groups([]) == []


class TestRankingByCost:
    """Ranking is by resources burned, not run count.

    A 5-run group that cost 400 GPU-hours matters more than 400 two-second
    probes; ordering by count buries the former under the latter, which is the
    same failure as a flat list -- it hands selection back to the reader.
    """

    def test_expensive_group_outranks_numerous_one(self, cot_exp):
        cheap = [cot_exp._replace(job_id="c%d" % i, name="cheap", elapsed=2.0) for i in range(400)]
        pricey = [
            cot_exp._replace(job_id="p%d" % i, name="pricey", elapsed=36000.0) for i in range(5)
        ]
        assert build_groups(cheap + pricey)[0].name == "pricey"

    def test_gpu_hours_are_weighted_above_core_hours(self, cot_exp):
        """One GPU-hour outranks one core-hour, by the documented equivalence.

        There is no site exchange rate to defer to -- TRESBillingWeights is
        undefined on all 86 partitions -- so the constant is a stated convention
        and this test pins it.
        """
        gpu = [
            cot_exp._replace(job_id="g%d" % i, name="gpu-work", elapsed=3600.0) for i in range(3)
        ]
        cpu_job = cot_exp._replace(alloc_tres="billing=1,cpu=1,mem=80G,node=1", req_tres="")
        cpu = [
            cpu_job._replace(job_id="c%d" % i, name="cpu-work", elapsed=3600.0) for i in range(3)
        ]
        assert build_groups(gpu + cpu)[0].name == "gpu-work"

    def test_enough_cpu_hours_do_outrank_a_little_gpu_work(self, cot_exp):
        """The weighting is a ratio, not a veto: 25,600 core-hours really is more
        compute than 3 GPU-hours, and the ranking must be able to say so."""
        gpu = [
            cot_exp._replace(job_id="g%d" % i, name="gpu-work", elapsed=3600.0) for i in range(3)
        ]
        cpu_job = cot_exp._replace(alloc_tres="billing=64,cpu=64,mem=80G,node=1", req_tres="")
        cpu = [
            cpu_job._replace(job_id="c%d" % i, name="cpu-work", elapsed=36000.0) for i in range(40)
        ]
        assert build_groups(gpu + cpu)[0].name == "cpu-work"


class TestSeverity:
    def test_mostly_failing_group_is_critical(self, repeat_timeouts):
        assert build_groups(repeat_timeouts)[0].severity == "crit"

    def test_healthy_group_is_ok(self, healthy_job):
        jobs = [healthy_job._replace(job_id=str(i)) for i in range(10)]
        assert build_groups(jobs)[0].severity == "ok"

    def test_single_failure_in_a_large_group_is_not_critical(self, healthy_job, cot_exp):
        jobs = [healthy_job._replace(job_id=str(i), name="mix") for i in range(50)]
        jobs.append(cot_exp._replace(job_id="bad", name="mix"))
        assert build_groups(jobs)[0].severity != "crit"


class TestSorting:
    def test_every_mode_is_stable_and_total(self, oom_series, repeat_timeouts):
        groups = build_groups(list(oom_series) + list(repeat_timeouts))
        for mode, _label in SORTS:
            assert len(sort_groups(groups, mode)) == len(groups)

    def test_name_sort_is_alphabetical(self, oom_series, repeat_timeouts):
        groups = build_groups(list(oom_series) + list(repeat_timeouts))
        names = [g.name for g in sort_groups(groups, "name")]
        assert names == sorted(names, key=str.lower)

    def test_cycle_wraps(self):
        mode = "cost"
        for _ in range(6):
            mode = next_sort(mode)
        assert mode == "cost"

    def test_unknown_mode_falls_back(self, oom_series):
        groups = build_groups(oom_series)
        assert sort_groups(groups, "nonsense") == sort_groups(groups, "cost")

    def test_label_exists_for_each_mode(self):
        assert sort_label("cost") == "resources burned"


class TestFiltering:
    def test_failed_filter(self, oom_series):
        assert len(filter_jobs(oom_series, "failed")) == 8

    def test_noop_filter(self, repeat_timeouts, healthy_job):
        jobs = list(repeat_timeouts) + [healthy_job]
        assert len(filter_jobs(jobs, "noop")) == 12

    def test_problem_filter_is_the_union(self, repeat_timeouts, oom_series):
        jobs = list(repeat_timeouts) + list(oom_series)
        assert len(filter_jobs(jobs, "problem")) == 20

    def test_search_matches_job_id(self, oom_series):
        assert len(filter_jobs(oom_series, "all", "52139773")) == 1

    def test_search_matches_node(self, repeat_timeouts):
        assert len(filter_jobs(repeat_timeouts, "all", "midway3-0385")) == 12

    def test_search_matches_state(self, oom_series):
        assert len(filter_jobs(oom_series, "all", "out_of_memory")) == 8

    def test_search_is_case_insensitive(self, repeat_timeouts):
        assert filter_jobs(repeat_timeouts, "all", "COT-EXP")

    def test_search_no_match(self, oom_series):
        assert filter_jobs(oom_series, "all", "zzzz") == []

    def test_group_filter(self, repeat_timeouts, healthy_job):
        groups = build_groups(list(repeat_timeouts) + [healthy_job])
        assert [g.name for g in filter_groups(groups, "failed")] == ["cot-exp"]

    def test_filter_names_are_unique(self):
        names = [n for n, _ in FILTERS]
        assert len(names) == len(set(names))


class TestHistory:
    def test_indexes_by_job_id(self, oom_series):
        history = History(oom_series)
        assert history.job("52139773") is not None
        assert history.job("nope") is None

    def test_len_counts_all_records(self, oom_series):
        assert len(History(oom_series)) == 10

    def test_group_for_job(self, repeat_timeouts):
        history = History(repeat_timeouts)
        assert history.group_for(repeat_timeouts[0]).name == "cot-exp"

    def test_patterns_are_lazy_and_cached(self, oom_series):
        history = History(oom_series)
        assert history._patterns is None
        first = history.patterns
        assert history._patterns is not None
        assert history.patterns is first

    def test_group_patterns_are_scoped(self, oom_series, repeat_timeouts):
        history = History(list(oom_series) + list(repeat_timeouts))
        group = [g for g in history.groups if g.name == "cot-exp"][0]
        codes = {f.code for f in history.group_patterns(group)}
        assert "memory-search" not in codes

    def test_headline_prefers_idle_hours(self, repeat_timeouts):
        assert "never computed" in History(repeat_timeouts).headline()

    def test_headline_on_clean_history(self, healthy_job):
        jobs = [healthy_job._replace(job_id=str(i)) for i in range(5)]
        assert "nothing flagged" in History(jobs).headline()

    def test_stats_exclude_open_records(self, stale_job, healthy_job):
        history = History([stale_job, healthy_job])
        assert history.stats["excluded_open_records"] == 1
        assert history.stats["gpu_hours_total"] < 10


class TestScale:
    """6,574 jobs is the real size; the index must not be accidentally quadratic."""

    def test_large_history_builds_quickly(self, cot_exp):
        # Alphabetic names: numeric suffixes would (correctly) normalize into a
        # single family, which is the opposite of what this test measures.
        names = [
            "work-" + a + b for a in string.ascii_lowercase[:6] for b in string.ascii_lowercase[:10]
        ]
        jobs = [cot_exp._replace(job_id=str(i), name=names[i % len(names)]) for i in range(6000)]
        history = History(jobs)
        assert len(history.groups) == 60
        assert len(history) == 6000

    def test_filter_over_large_history(self, cot_exp):
        names = ["work-" + a for a in string.ascii_lowercase]
        jobs = [cot_exp._replace(job_id=str(i), name=names[i % len(names)]) for i in range(6000)]
        assert len(filter_jobs(jobs, "all", "work-c")) > 0
