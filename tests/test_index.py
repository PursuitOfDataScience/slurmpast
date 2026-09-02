import string

import pytest

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
        assert sort_label("cost") == "resource use"


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


class TestSearchMatchesWhatIsOnScreen:
    """Reported: searching "07-28" returned nothing against a table full of
    visible "07-28 15:00". Typing what you can plainly see and getting an empty
    list reads as missing data, not as a narrow search box."""

    def _jobs(self):
        from slurmpast.demo import history

        return history()

    # 07-20 07:22 is demo job 5100035, the first of the rc-tok-github_code series.
    # Deliberately not a midnight stamp: the demo's clock now counts up from 00:00
    # on each day (see demo._time_of_day), and an "HH:MM" case of "00:00" would
    # pass against a haystack that had lost its time component entirely.
    @pytest.mark.parametrize("query", ["07-20", "2026-07-20", "07-20 07:22", "07:22", "2026-07"])
    def test_a_date_from_the_started_column_matches(self, query):
        assert filter_jobs(self._jobs(), "all", query), query

    def test_only_the_started_column_is_matched(self):
        """A run that began 07-24 23:02 and finished 07-25 06:58 matched "07-25"
        while its row displayed 07-24 -- a hit the reader cannot see. STARTED is
        the always-visible column and the sort key, so it alone is indexed."""
        from slurmpast.model import Job

        overnight = Job(
            job_id="1",
            name="w",
            state="COMPLETED",
            start="2026-07-24T23:02:00",
            end="2026-07-25T06:58:00",
            elapsed=28680.0,
        )
        assert filter_jobs([overnight], "all", "07-24") == [overnight]
        assert filter_jobs([overnight], "all", "07-25") == []

    def test_every_hit_is_visibly_explained(self):
        """After the fix, each returned row displays the date that was typed."""
        jobs = self._jobs()
        for stamp in ("07-01", "07-05", "07-20"):
            for job in filter_jobs(jobs, "all", stamp):
                assert stamp in (job.start or ""), (stamp, job.start)

    def test_the_display_spelling_and_the_raw_spelling_both_match(self):
        """The table shows "07-20 07:22"; sacct stores "2026-07-20T07:22:00". One
        normalised haystack covers both, so a query copied off the screen works."""
        jobs = self._jobs()
        assert filter_jobs(jobs, "all", "2026-07-20T07:22:00".replace("T", " "))
        assert filter_jobs(jobs, "all", "07-20 07:22")

    def test_the_existing_fields_still_match(self):
        jobs = self._jobs()
        assert filter_jobs(jobs, "all", "cot-exp")
        assert filter_jobs(jobs, "all", "TIMEOUT")
        assert filter_jobs(jobs, "all", "midway3-0602")
        assert filter_jobs(jobs, "all", "5100001")

    def test_a_miss_is_still_a_miss(self):
        assert filter_jobs(self._jobs(), "all", "no-such-thing") == []

    def test_the_overview_last_run_date_is_searchable(self):
        """LAST RUN is a column there for the same reason."""
        from slurmpast.index import filter_groups

        groups = History(self._jobs()).groups
        stamp = groups[0].last_seen[:10]
        assert filter_groups(groups, "all", stamp)
        assert filter_groups(groups, "all", stamp[5:])  # the "07-26" form
        assert filter_groups(groups, "all", "no-such-thing") == []

    @pytest.mark.asyncio
    async def test_the_placeholder_advertises_dates(self):
        """A box that silently cannot match a whole visible column is a trap."""
        pytest.importorskip("textual")
        from slurmpast import tui

        assert "date" in tui.SearchBar().placeholder


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


class TestFailuresSortCountsEachRunOnce:
    """`failed + noop` double-counts, which is why `problems` exists.

    A hung TIMEOUT is both failed and a noop, so summing them ranked a workload
    with 5 hung timeouts above one with 8 genuine OOM kills under a sort the UI
    calls "failed runs". `GroupStats.problems` is already the de-duplicated union
    and is already the number the FLAGGED column shows.
    """

    def test_real_failures_outrank_double_counted_hangs(self, repeat_timeouts, oom_series):
        hangs = build_groups(repeat_timeouts)[0]
        assert hangs.failed and hangs.noop, "fixture must be both to be worth testing"
        ordered = sort_groups(build_groups(list(repeat_timeouts) + list(oom_series)), "failures")
        by_name = {g.name: g for g in ordered}
        assert set(by_name) == {"cot-exp", "rc-tok-github_code"}
        assert ordered[0].problems >= ordered[1].problems
        assert ordered[0].problems == max(g.problems for g in ordered)

    def test_the_key_is_the_union_not_the_sum(self, repeat_timeouts):
        group = build_groups(repeat_timeouts)[0]
        assert group.problems < group.failed + group.noop, "no overlap, nothing to check"


class TestBuildGroupsWalksItsInputTwice:
    def test_a_one_shot_iterator_still_counts_the_excluded(self, stale_job, healthy_job):
        """`Iterable` is what the signature accepts, and it was silently wrong.

        The first pass exhausted the iterator, so the second -- the one that counts
        open-ended records per workload -- saw nothing and reported `excluded=0`,
        quietly undoing the guarantee it exists to provide.
        """
        jobs = [healthy_job, stale_job._replace(name=healthy_job.name)]
        from_list = build_groups(jobs)
        from_iterator = build_groups(iter(jobs))
        assert [g.excluded for g in from_iterator] == [g.excluded for g in from_list]
        assert sum(g.excluded for g in from_iterator) == 1


class TestTheTruncationNoteDescribesWhatWasTruncated:
    """`tail_summary` sliced `self.groups` -- always cost order -- while its caller
    sliced a sorted copy. So under any non-default `--sort` the note described a
    different set of workloads than the ones actually hidden, and described the
    hidden bulk of the history as a negligible remainder: 30 runs holding 86.4% of
    the compute, reported as 23 runs holding 10.9%. The line exists so truncation is
    never silent; wrong is worse than silent, because it reassures.
    """

    @staticmethod
    def _history():
        from slurmpast.demo import history

        return History(history(), window="demo")

    def test_the_default_order_is_unchanged(self):
        history = self._history()
        assert history.tail_summary(3, ordered=sort_groups(history.groups, "cost")) == (
            history.tail_summary(3)
        )

    @pytest.mark.parametrize("mode", ["name", "rate", "runs", "recent", "failures"])
    def test_every_order_gets_its_own_tail(self, mode):
        history = self._history()
        ordered = sort_groups(history.groups, mode)
        note = history.tail_summary(3, ordered=ordered)
        hidden = ordered[3:]
        assert "%d more workloads" % len(hidden) in note
        assert "(%d runs)" % sum(g.total for g in hidden) in note
        share = 100.0 * sum(g.cost for g in hidden) / sum(g.cost for g in history.groups)
        assert "%.1f%%" % share in note

    def test_a_non_default_order_really_does_differ(self):
        """Guards the test above from passing vacuously on a history where every
        order happens to hide the same workloads."""
        history = self._history()
        by_cost = history.tail_summary(3, ordered=sort_groups(history.groups, "cost"))
        by_name = history.tail_summary(3, ordered=sort_groups(history.groups, "name"))
        assert by_cost != by_name


class TestSortTieBreaksRunTheSameWayInEveryMode:
    """`reverse=True` reverses the whole key tuple, tie-break included. Every other
    mode negates its primary inside the key and so leaves names A-Z; `recent` cannot
    negate a timestamp string, inherited the flip, and ordered same-day workloads
    Z-A. Sharing a date is the ordinary case for the one sort keyed on a date."""

    @staticmethod
    def _tied(names, stamp="2026-07-20T00:00:00"):
        from slurmpast.index import GroupStats

        return [
            GroupStats(
                key=(name, "p", "cpu", "u"),
                name=name,
                partition="p",
                kind="cpu",
                distinct_names=1,
                excluded=0,
                jobs=(),
                total=1,
                completed=1,
                failed=0,
                cancelled=0,
                noop=0,
                problems=0,
                gpu_hours=0.0,
                core_hours=1.0,
                wasted_gpu_hours=0.0,
                first_seen=stamp,
                last_seen=stamp,
            )
            for name in names
        ]

    # The three keys that carry a name to break ties with. `cost`, `failures` and
    # `rate` break theirs on another number and leave equal rows in input order,
    # which is a different question from this one.
    @pytest.mark.parametrize("mode", ["recent", "runs", "name"])
    def test_ties_are_alphabetical(self, mode):
        groups = self._tied(["charlie", "alpha", "bravo"])
        assert [g.name for g in sort_groups(groups, mode)] == ["alpha", "bravo", "charlie"]

    def test_recent_still_puts_the_newest_first(self):
        groups = self._tied(["alpha", "bravo"]) + self._tied(["zulu"], "2026-07-25T00:00:00")
        assert [g.name for g in sort_groups(groups, "recent")] == ["zulu", "alpha", "bravo"]


class TestAFoldedNodeListIsSearchableByHostname:
    """`midway3-[0003-0004]` contains neither hostname, so neither found the job.

    `filter_jobs` states the standard it failed: "typing what you can plainly see
    and getting an empty list is the worst kind of empty result -- it reads as
    missing data." Its own docstring offers `what died on midway3-0385` as one of
    the four queries the box is for.

    Slurm folds a multi-node allocation, and the raw string was what got searched.
    The reader can plainly see the individual hostnames -- the job screen for one
    of these real jobs prints both of these rows:

        nodes            midway3-[0003-0004] (2 nodes)
        slowest task     0.3% below average (task 1 on midway3-0003)
        peak on          midway3-0003 task 0

    and then the job list could not find `midway3-0003`. On this machine 26 of
    20,905 jobs carry a folded NodeList and 72 hostname searches came back empty
    for a job that had run on that node.
    """

    def _on(self, healthy_job, nodelist, job_id="1"):
        return healthy_job._replace(job_id=job_id, node_list=nodelist)

    def test_each_hostname_in_a_range_finds_the_job(self, healthy_job):
        job = self._on(healthy_job, "midway3-[0003-0004]")
        assert filter_jobs([job], query="midway3-0003") == [job]
        assert filter_jobs([job], query="midway3-0004") == [job]

    def test_the_folded_string_itself_still_matches(self, healthy_job):
        """The control: a reader who copies the `nodes` row verbatim off the job
        screen types the bracketed form, and that has to keep working."""
        job = self._on(healthy_job, "midway3-[0003-0004]")
        assert filter_jobs([job], query="midway3-[0003-0004]") == [job]
        assert filter_jobs([job], query="midway3-") == [job]

    def test_a_plain_single_node_is_unaffected(self, healthy_job):
        """The other control. 20,879 of the 20,905 real jobs have no bracket at
        all, and the fast path they take must not change."""
        job = self._on(healthy_job, "midway3-0294")
        assert filter_jobs([job], query="midway3-0294") == [job]
        assert filter_jobs([job], query="midway3-0295") == []

    def test_expanding_does_not_invent_a_match(self, healthy_job):
        """The control that matters most: searching a hostname outside the range
        must still return nothing. A fix that makes every search match everything
        would pass the first test in this class."""
        job = self._on(healthy_job, "midway3-[0003-0004]")
        assert filter_jobs([job], query="midway3-0005") == []
        assert filter_jobs([job], query="beagle3-0003") == []

    def test_the_suffixed_and_multi_range_forms_too(self, healthy_job):
        """`expand_nodelist` handles the whole hostlist grammar; the search has to
        get the same answers it does, not a simpler subset."""
        job = self._on(healthy_job, "beagle3-bigmem[1-4]")
        assert filter_jobs([job], query="beagle3-bigmem1") == [job]
        assert filter_jobs([job], query="beagle3-bigmem4") == [job]
        assert filter_jobs([job], query="beagle3-bigmem5") == []

    def test_no_node_list_does_not_raise(self, healthy_job):
        for value in ("", None, "None assigned"):
            job = self._on(healthy_job, value)
            assert filter_jobs([job], query="midway3-0003") == []

    def test_the_hostname_the_job_screen_prints_is_findable(self, healthy_job):
        """End to end, and the exact path a reader walks: read a hostname off the
        job screen, type it into the list."""
        import re

        from slurmpast.report import render_job

        # Shaped like real job 51553906: the allocation is folded, and the
        # per-step readers name one host inside it, which is what gets printed.
        job = self._on(healthy_job, "midway3-[0003-0004]")._replace(
            alloc_nodes=2,
            nnodes=2,
            steps=tuple(
                st._replace(max_rss_node="midway3-0003", nnodes=2) for st in healthy_job.steps
            ),
        )
        text = re.sub(r"\x1b\[[0-9;]*m", "", render_job(job)[0])
        # "peak on  midway3-0003" -- a bare hostname the folded NodeList in the
        # row above it does not contain.
        shown = set(re.findall(r"midway3-\d{4}", text))
        assert "midway3-0003" in shown, text
        for hostname in shown:
            assert filter_jobs([job], query=hostname) == [job], hostname


class TestTheNameOnTheOverviewIsSearchable:
    """JOB NAME on the overview is `GroupStats.label`, and the search box matched
    `GroupStats.name` -- the fold.

    `label` shows a real job name wherever the fold would otherwise stand in for
    exactly one, which is the ordinary case rather than the exception: 639 of 879
    workloads on a real 30-day history. So the table printed `exp-a45` and typing
    it returned nothing, because the only name in the haystack was `exp-a#`. That
    is the failure `filter_jobs` names in its own comment -- "typing what you can
    plainly see and getting an empty list is the worst kind of empty result" -- on
    the landing screen, for three rows in four.

    Round thirteen fixed the *promise* this box makes (`GROUP_SEARCH_FIELDS` says
    "name") and left the promise unmet for the value it displays. Its test could
    not catch this: it samples a job name out of the demo history, and every demo
    workload has a name the fold leaves alone, so `label == name` for all eight and
    the assertion held vacuously.
    """

    @staticmethod
    def _rows(name, count, partition="test"):
        from tests.conftest import row

        rows = []
        for offset in range(count):
            day = "2026-06-%02d" % (offset + 1)
            rows.append(
                row(
                    JobID=str(200 + offset),
                    JobName=name,
                    User="youzhi",
                    Partition=partition,
                    State="COMPLETED",
                    ExitCode="0:0",
                    Submit="%sT01:00:00" % day,
                    Start="%sT01:00:01" % day,
                    End="%sT01:30:01" % day,
                    Elapsed="00:30:00",
                    ElapsedRaw="1800",
                    Timelimit="01:00:00",
                    ReqCPUS="1",
                    AllocTRES="cpu=1,mem=8G,node=1",
                    NodeList="midway3-0602",
                    NTasks="1",
                    TotalCPU="20:00",
                )
            )
        return rows

    @staticmethod
    def _parse(rows):
        from slurmpast.sacct import parse
        from tests.conftest import make_text

        return parse(make_text(*rows))

    def _groups(self):
        return build_groups(self._parse(self._rows("s1e20", 3)))

    def test_the_fold_hides_a_real_name_on_this_fixture(self):
        """The premise, asserted rather than assumed: without a group whose label
        differs from its fold there is nothing here to test, and that is exactly
        how the round-thirteen test passed while the defect stood."""
        group = self._groups()[0]
        assert group.name == "s#e#"
        assert group.label == "s1e20"

    def test_the_displayed_label_finds_the_group(self):
        groups = self._groups()
        assert filter_groups(groups, "all", "s1e20") == groups

    def test_every_label_in_a_history_is_findable(self):
        """The general rule, over the demo history and the fixture together."""
        from slurmpast.demo import history

        jobs = [j for j in history() if not j.open_ended]
        jobs += self._parse(self._rows("mid85_059", 4))
        groups = build_groups(jobs)
        assert len(groups) == 9
        for group in groups:
            assert filter_groups(groups, "all", group.label), group.label

    def test_the_fold_still_matches(self):
        """First control: widening the haystack must not cost the pattern itself,
        which is what a reader who has learned the `#` notation types."""
        groups = self._groups()
        assert filter_groups(groups, "all", "s#e#") == groups

    def test_the_overview_still_cannot_be_searched_by_job_id_or_state(self):
        """Second control, and the one this change could plausibly have broken:
        round thirteen's whole finding was that the box must not invite job id,
        state or node here, and its test asserts those three still return nothing.
        A haystack widened by whole `Job` records rather than by their names would
        satisfy this class and silently reopen that one."""
        from slurmpast.index import GROUP_SEARCH_FIELDS

        groups = self._groups()
        for field, query in (("job id", "200"), ("state", "COMPLETED"), ("node", "midway3-0602")):
            assert field not in GROUP_SEARCH_FIELDS, field
            assert filter_groups(groups, "all", query) == [], (field, query)

    def test_a_miss_is_still_a_miss(self):
        assert filter_groups(self._groups(), "all", "s2e20") == []
