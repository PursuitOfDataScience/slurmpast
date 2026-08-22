import random

import pytest

from slurmpast.nodes import (
    _bh_reject,
    compress_nodelist,
    dominant_workload,
    excluded_tail,
    expand_nodelist,
    node_p_value,
    node_table,
    note_for_allocation,
    note_for_node,
    suggest_exclude,
    wilson_interval,
)


class TestExpandNodelist:
    def test_single_node(self):
        assert expand_nodelist("midway3-0385") == ["midway3-0385"]

    def test_range(self):
        assert expand_nodelist("midway3-[0277-0279]") == [
            "midway3-0277",
            "midway3-0278",
            "midway3-0279",
        ]

    def test_mixed_range_and_singles(self):
        assert expand_nodelist("midway3-[0298,0377-0378]") == [
            "midway3-0298",
            "midway3-0377",
            "midway3-0378",
        ]

    def test_zero_padding_preserved(self):
        assert "midway3-0007" in expand_nodelist("midway3-[0007-0008]")

    def test_multiple_prefixes(self):
        got = expand_nodelist("beagle3-0011,midway3-[0602-0603]")
        assert got == ["beagle3-0011", "midway3-0602", "midway3-0603"]

    @pytest.mark.parametrize("value", ["", "None assigned", None])
    def test_unassigned_is_empty(self, value):
        assert expand_nodelist(value) == []

    def test_compressed_multinode_is_not_counted_as_one(self):
        """Counting the raw NodeList string undercounts multi-node placements."""
        assert len(expand_nodelist("midway3-[0600-0606]")) == 7


class TestCompressNodelist:
    def test_roundtrip_range(self):
        nodes = expand_nodelist("midway3-[0600-0606]")
        assert compress_nodelist(nodes) == "midway3-[0600-0606]"

    def test_single_stays_plain(self):
        assert compress_nodelist(["midway3-0385"]) == "midway3-0385"

    def test_disjoint_runs(self):
        got = compress_nodelist(["midway3-0385", "midway3-0432", "midway3-0433"])
        assert got == "midway3-[0385,0432-0433]"

    def test_empty(self):
        assert compress_nodelist([]) == ""


class TestWilson:
    def test_interval_brackets_the_estimate(self):
        low, high = wilson_interval(19, 36)
        assert low < 19 / 36.0 < high

    def test_small_sample_is_wide(self):
        narrow = wilson_interval(100, 400)
        wide = wilson_interval(1, 4)
        assert (wide[1] - wide[0]) > (narrow[1] - narrow[0])

    def test_zero_trials_is_maximally_uncertain(self):
        assert wilson_interval(0, 0) == (0.0, 1.0)

    def test_all_failures_does_not_claim_certainty(self):
        low, high = wilson_interval(10, 10)
        assert low < 1.0


def _placements(node, bad, total, name="node-evaluation", job_id_base=1000):
    """Synthesize `total` jobs on `node`, `bad` of them FAILED."""
    from slurmpast.sacct import parse
    from tests.conftest import row

    rows = [
        row(
            JobID=str(job_id_base + index),
            JobName=name,
            Partition="test",
            State="FAILED" if index < bad else "COMPLETED",
            ExitCode="0:0",
            End="2026-01-01T00:10:00",
            Elapsed="00:10:00",
            Timelimit="01:00:00",
            ReqMem="40Gn",
            ReqCPUS="8",
            AllocTRES="billing=8,cpu=8,mem=40G,node=1",
            NodeList=node,
        )
        for index in range(total)
    ]
    return parse("\n".join(rows))


class TestNodeTable:
    def test_worse_node_identified(self):
        jobs = _placements("midway3-0385", 19, 36) + _placements(
            "midway3-0600", 12, 218, job_id_base=5000
        )
        table = node_table(jobs, workload="node-evaluation")
        rows = {r["node"]: r for r in table["rows"]}
        assert rows["midway3-0385"]["verdict"] == "worse"
        assert rows["midway3-0385"]["rate"] > rows["midway3-0600"]["rate"]

    def test_better_node_identified(self):
        jobs = _placements("midway3-0385", 19, 36) + _placements(
            "midway3-0600", 12, 218, job_id_base=5000
        )
        rows = {r["node"]: r for r in node_table(jobs, workload="node-evaluation")["rows"]}
        assert rows["midway3-0600"]["verdict"] == "better"

    def test_thin_evidence_is_inconclusive_not_accusatory(self):
        """One bad run out of twelve must not brand a node."""
        jobs = _placements("midway3-0001", 6, 12) + _placements(
            "midway3-0002", 30, 60, job_id_base=9000
        )
        rows = {r["node"]: r for r in node_table(jobs, workload="node-evaluation")["rows"]}
        assert rows["midway3-0001"]["verdict"] == "inconclusive"

    def test_below_threshold_nodes_omitted_but_counted(self):
        jobs = _placements("midway3-0009", 1, 3)
        table = node_table(jobs, workload="node-evaluation")
        assert table["rows"] == []
        assert table["skipped_nodes"] == 1

    def test_workload_control_changes_the_answer(self):
        """The confound is real: a node hosting one bad campaign looks cursed."""
        mixed = _placements("midway3-0385", 30, 30, name="cot-exp") + _placements(
            "midway3-0385", 0, 30, name="node-evaluation", job_id_base=7000
        )
        uncontrolled = node_table(mixed)
        controlled = node_table(mixed, workload="node-evaluation")
        assert uncontrolled["rows"][0]["rate"] == pytest.approx(0.5)
        assert controlled["rows"][0]["rate"] == pytest.approx(0.0)

    def test_hang_metric_uses_cpu_not_state(self, repeat_timeouts):
        table = node_table(repeat_timeouts, workload="cot-exp", metric="hang", min_samples=5)
        assert table["rows"][0]["rate"] == pytest.approx(1.0)

    def test_cancelled_excluded_from_failure_rate(self):
        jobs = _placements("midway3-0100", 0, 20)
        cancelled = tuple(j._replace(state="CANCELLED by 1") for j in jobs)
        table = node_table(list(jobs) + list(cancelled), workload="node-evaluation")
        assert table["rows"][0]["bad"] == 0


class TestSuggestions:
    def test_only_statistically_worse_nodes_suggested(self):
        jobs = _placements("midway3-0385", 19, 36) + _placements(
            "midway3-0600", 12, 218, job_id_base=5000
        )
        table = node_table(jobs, workload="node-evaluation")
        assert suggest_exclude(table) == ["midway3-0385"]

    def test_no_suggestion_without_evidence(self):
        jobs = _placements("midway3-0001", 5, 20)
        assert suggest_exclude(node_table(jobs, workload="node-evaluation")) == []

    def test_note_mentions_confidence_interval(self):
        jobs = _placements("midway3-0385", 19, 36) + _placements(
            "midway3-0600", 12, 218, job_id_base=5000
        )
        note = note_for_node(jobs, "midway3-0385", workload="node-evaluation")
        assert "CI" in note
        # The rate it is compared against, stated as what it is: every OTHER node.
        # A pooled "baseline" would include this node's own 36 placements, which is
        # the comparison the verdict is not making.
        assert "on every other node" in note
        assert "5.5%" in note  # 12 of 218 elsewhere, not 31/254 pooled

    def test_the_comparison_excludes_the_node_being_judged(self):
        """A node holding most of the placements would otherwise be compared against
        a rate it dominates. Real case: midway3-0602 is 403 of 1,098 placements."""
        jobs = _placements("midway3-0385", 60, 100) + _placements(
            "midway3-0600", 2, 20, job_id_base=5000
        )
        table = node_table(jobs, workload="node-evaluation")
        row = next(r for r in table["rows"] if r["node"] == "midway3-0385")
        assert row["comparison"] == pytest.approx(2 / 20)
        assert table["baseline"] == pytest.approx(62 / 120)  # header keeps the pooled rate
        assert row["verdict"] == "worse"

    def test_note_empty_for_ordinary_node(self):
        jobs = _placements("midway3-0385", 19, 36) + _placements(
            "midway3-0600", 12, 218, job_id_base=5000
        )
        assert note_for_node(jobs, "midway3-0600", workload="node-evaluation") == ""


class TestTheNoteCoversTheWholeAllocation:
    """Both front ends passed ``expand_nodelist(job.node_list)[0]`` -- the first node
    and nothing else. On the single-node job that is 99.6% of a real history that is
    the whole allocation; on a multi-node job it examined one node of however many,
    so the warning went missing exactly where the job had the most places to have
    gone wrong.
    """

    @staticmethod
    def _fleet():
        """40 clean placements on midway3-0600, 30 of 40 failing on midway3-0607."""
        return _placements("midway3-0600", 0, 40) + _placements(
            "midway3-0607", 30, 40, job_id_base=5000
        )

    def test_a_multi_node_job_is_warned_about_its_bad_node(self):
        jobs = self._fleet()
        # The bad node is listed SECOND, which is what the old code walked past.
        note = note_for_allocation(jobs, "midway3-[0600-0607]", workload="node-evaluation")
        assert "midway3-0607" in note, note
        assert "on every other node" in note

    def test_a_single_node_allocation_is_unchanged(self):
        jobs = self._fleet()
        assert note_for_allocation(jobs, "midway3-0607", workload="node-evaluation") == (
            note_for_node(jobs, "midway3-0607", workload="node-evaluation")
        )

    def test_an_allocation_of_only_good_nodes_stays_silent(self):
        jobs = self._fleet()
        assert note_for_allocation(jobs, "midway3-0600", workload="node-evaluation") == ""

    def test_no_nodelist_is_not_an_accusation(self):
        jobs = self._fleet()
        for value in ("", None, "None assigned"):
            assert note_for_allocation(jobs, value, workload="node-evaluation") == ""

    def test_only_the_worst_node_is_named(self):
        """A job on several bad nodes needs to know its placement is the problem,
        not a list of intervals."""
        jobs = (
            _placements("midway3-0600", 0, 40)
            + _placements("midway3-0606", 25, 40, job_id_base=4000)
            + _placements("midway3-0607", 35, 40, job_id_base=5000)
        )
        note = note_for_allocation(jobs, "midway3-[0600-0607]", workload="node-evaluation")
        assert note.count("failed") == 1
        assert note.startswith("midway3-0607"), "the worse of the two, by rate"

    def test_the_job_screen_reaches_the_bad_node(self):
        """End to end through the CLI helper, which is what a reader actually sees."""
        from slurmpast.cli import _node_note
        from slurmpast.index import History

        jobs = self._fleet()
        job = jobs[0]._replace(job_id="9999", node_list="midway3-[0600-0607]", state="FAILED")
        assert "midway3-0607" in _node_note(job, History(list(jobs) + [job]))


class TestDominantWorkload:
    def test_picks_most_common(self, repeat_timeouts, healthy_job):
        assert dominant_workload(list(repeat_timeouts) + [healthy_job]) == "cot-exp"

    def test_empty_history(self):
        assert dominant_workload([]) is None

    def test_prefers_a_workload_that_exhibits_the_metric(self, repeat_timeouts, healthy_job):
        """Measured on a real 30-day history: the most-common workload was 200
        runs of `sw-arr100` with ZERO hangs, so every row of the table read
        "0/10, 0.0%, inconclusive" against a 0.0% baseline -- eight rows of
        nothing. The comparison has to be held over work that actually hangs.
        """
        # More runs of the healthy workload than of the hanging one.
        bulk = [healthy_job._replace(job_id=str(9000 + i), name="bulk-healthy") for i in range(40)]
        jobs = bulk + list(repeat_timeouts)
        assert dominant_workload(jobs) == "bulk-healthy"  # by count alone
        assert dominant_workload(jobs, metric="hang") == "cot-exp"

    def test_falls_back_to_the_count_when_nothing_exhibits_it(self, healthy_job):
        jobs = [healthy_job._replace(job_id=str(9000 + i)) for i in range(5)]
        assert dominant_workload(jobs, metric="hang") == healthy_job.name


class TestOneTestPerNodeIsStillManyTests:
    """The table runs a test per node and shows them together, so the error rate
    that matters is the whole table's. Uncorrected it was a function of how many
    nodes were tested rather than of the evidence: on a null where every node
    shares one true rate, a 20-node table offered an innocent node to --exclude
    54.8% of the time and a 40-node table 77.8%.
    """

    @staticmethod
    def _null_tables(n_nodes, tables, seed, jobs_per=30, rate=0.20):
        """Fraction of tables flagging at least one node, with every node identical.

        Jobs are built directly rather than through `parse` -- this generates tens
        of thousands of records and the sacct reader is far too slow for that.
        """
        from slurmpast.model import Job

        rng = random.Random(seed)
        flagged = 0
        for _ in range(tables):
            jobs = []
            for node in range(n_nodes):
                for _ in range(jobs_per):
                    jobs.append(
                        Job(
                            job_id="%d" % len(jobs),
                            name="w",
                            node_list="node%03d" % node,
                            elapsed=600.0,
                            timelimit=3600.0,
                            state="FAILED" if rng.random() < rate else "COMPLETED",
                        )
                    )
            if suggest_exclude(node_table(jobs, workload="w")):
                flagged += 1
        return flagged / float(tables)

    def test_an_innocent_node_is_rarely_offered_to_exclude(self):
        rate = self._null_tables(20, tables=120, seed=4242)
        # Corrected this sits near 3%; uncorrected it was 54.8%. The bound is loose
        # enough not to flake on 120 samples and far below what a regression costs.
        assert rate < 0.15, "%.1f%% of null tables flagged a node" % (100 * rate)

    def test_the_error_rate_does_not_grow_with_the_table(self):
        """The signature of the defect, and the reason a bigger Z is not the fix:
        raising Z to 2.576 still went 13.5% -> 21.3% -> 33.8% across these sizes."""
        small = self._null_tables(10, tables=120, seed=7)
        large = self._null_tables(40, tables=120, seed=8)
        assert large < 0.15
        # Uncorrected this gap was +41 points (36.5% -> 77.8%).
        assert large < small + 0.10, "%.1f%% at 10 nodes, %.1f%% at 40" % (100 * small, 100 * large)

    def test_a_genuinely_bad_node_still_survives_a_large_table(self):
        """The correction must cost power where evidence is thin, not everywhere.
        This is the module's own headline case, buried in 39 innocent nodes."""
        from slurmpast.model import Job

        rng = random.Random(11)
        jobs = []
        for node in range(40):
            bad_rate = 0.55 if node == 0 else 0.20
            for _ in range(50):
                jobs.append(
                    Job(
                        job_id="%d" % len(jobs),
                        name="w",
                        node_list="node%03d" % node,
                        elapsed=600.0,
                        timelimit=3600.0,
                        state="FAILED" if rng.random() < bad_rate else "COMPLETED",
                    )
                )
        assert suggest_exclude(node_table(jobs, workload="w")) == ["node000"]

    def test_the_real_recorded_signal_is_untouched(self):
        """19/36 against 12/218 is a 9.6x spread on identical work. No correction
        may be allowed to talk the tool out of that one."""
        jobs = _placements("midway3-0385", 19, 36) + _placements(
            "midway3-0600", 12, 218, job_id_base=5000
        )
        table = node_table(jobs, workload="node-evaluation")
        rows = {r["node"]: r for r in table["rows"]}
        assert rows["midway3-0385"]["verdict"] == "worse"
        assert rows["midway3-0385"]["p_value"] < 1e-9

    def test_a_withheld_verdict_is_counted_so_the_screen_can_explain_it(self):
        """The table displays the interval that the verdict no longer rests on
        alone, so a row reading `inconclusive` beside a CI clear of the baseline
        has to be explainable rather than looking like a contradiction."""
        from slurmpast.model import Job

        rng = random.Random(2026)
        found = False
        for seed in range(60):
            rng.seed(seed)
            jobs = []
            for node in range(20):
                for _ in range(30):
                    jobs.append(
                        Job(
                            job_id="%d" % len(jobs),
                            name="w",
                            node_list="node%03d" % node,
                            elapsed=600.0,
                            timelimit=3600.0,
                            state="FAILED" if rng.random() < 0.20 else "COMPLETED",
                        )
                    )
            table = node_table(jobs, workload="w")
            if table["held_back"]:
                found = True
                clears = [
                    r
                    for r in table["rows"]
                    if r["verdict"] == "inconclusive"
                    and (r["ci_low"] > r["comparison"] or r["ci_high"] < r["comparison"])
                ]
                assert len(clears) == table["held_back"]
                break
        assert found, "no null table in 60 draws produced an interval the correction withheld"

    def test_tested_nodes_is_the_family_the_correction_used(self):
        jobs = _placements("midway3-0385", 19, 36) + _placements(
            "midway3-0600", 12, 218, job_id_base=5000
        )
        table = node_table(jobs, workload="node-evaluation")
        assert table["tested_nodes"] == len(table["rows"]) == 2


class TestNodePValue:
    def test_matches_the_hand_computed_fisher_tail(self):
        """1 failure in 10 placements against 0 in 500: P = 10/510."""
        assert node_p_value(1, 10, 0, 500, "worse") == pytest.approx(10 / 510.0)

    def test_a_zero_baseline_does_not_become_a_certainty(self):
        """The reason this is Fisher and not a binomial tail against the
        leave-one-out rate: that rate is estimated, and a binomial test against an
        estimated 0% scores one bad run at exactly p = 0 -- which no correction can
        withhold, in a table of any size. Fisher leaves it borderline instead, so
        the size of the table still gets a say."""
        borderline = node_p_value(1, 10, 0, 500, "worse")
        assert borderline > 0.0
        assert 0.05 / 3 < borderline < 0.05 / 2

        # Two nodes: p = 0.0196 clears 0.05*1/2, and stands.
        two = _placements("midway3-0009", 1, 10) + _placements(
            "midway3-0010", 0, 500, job_id_base=5000
        )
        assert suggest_exclude(node_table(two, workload="node-evaluation")) == ["midway3-0009"]

        # The same one bad run, with a third node that was also tested. Nothing
        # about midway3-0009 changed; the number of chances to produce it did.
        three = (
            _placements("midway3-0009", 1, 10)
            + _placements("midway3-0010", 0, 250, job_id_base=5000)
            + _placements("midway3-0011", 0, 250, job_id_base=7000)
        )
        assert suggest_exclude(node_table(three, workload="node-evaluation")) == []

    def test_a_strong_signal_against_a_clean_fleet_still_lands(self):
        assert node_p_value(3, 10, 0, 500, "worse") < 0.001

    def test_the_two_directions_agree_on_one_2x2_table(self):
        """In a two-node table "A is worse" and "B is better" are the same event."""
        worse = node_p_value(19, 36, 12, 218, "worse")
        better = node_p_value(12, 218, 19, 36, "better")
        assert worse == pytest.approx(better)

    def test_identical_rates_are_not_surprising(self):
        assert node_p_value(6, 12, 30, 60, "worse") > 0.5

    def test_no_failures_anywhere_is_not_a_finding(self):
        assert node_p_value(0, 20, 0, 20, "worse") == 1.0

    def test_a_single_node_cannot_be_compared(self):
        assert node_p_value(5, 10, 0, 0, "worse") == 1.0


class TestBenjaminiHochberg:
    def test_rejects_the_clearly_small_one_only(self):
        assert _bh_reject([0.001, 0.4, 0.6]) == {0}

    def test_step_up_rescues_the_larger_of_two_small_ones(self):
        """Bonferroni would keep only the first at alpha/m = 0.025. BH steps up:
        0.03 <= 0.05*2/2, so both are rejected. This is the power BH buys."""
        assert _bh_reject([0.02, 0.03]) == {0, 1}

    def test_nothing_survives_when_nothing_is_small(self):
        assert _bh_reject([0.2, 0.3, 0.9]) == set()

    def test_empty_family(self):
        assert _bh_reject([]) == set()

    def test_the_bar_tightens_as_the_family_grows(self):
        """The whole point: the same p-value is a finding in a small table and not
        in a large one, because the large table ran more chances to produce it."""
        assert 0 in _bh_reject([0.02, 0.5])
        assert _bh_reject([0.02] + [0.5] * 39) == set()


class TestTheScreenExplainsAWithheldVerdict:
    """The table shows one interval per node and corrects the verdict across all of
    them, so an interval clear of the baseline can sit beside "inconclusive". Left
    unexplained that reads as the tool contradicting its own evidence column.
    """

    @staticmethod
    def _null_history(seed, n_nodes=20, jobs_per=30, rate=0.20):
        from slurmpast.model import Job

        rng = random.Random(seed)
        jobs = []
        for node in range(n_nodes):
            for _ in range(jobs_per):
                jobs.append(
                    Job(
                        job_id="%d" % len(jobs),
                        name="w",
                        node_list="node%03d" % node,
                        elapsed=600.0,
                        timelimit=3600.0,
                        state="FAILED" if rng.random() < rate else "COMPLETED",
                    )
                )
        return jobs

    def test_the_note_is_shown_when_an_interval_was_withheld(self):
        from slurmpast.index import History
        from slurmpast.report import Style, render_nodes

        for seed in range(60):
            jobs = self._null_history(seed)
            table = node_table(jobs, workload="w")
            if not table["held_back"]:
                continue
            text = render_nodes(History(jobs), metric="failure", style=Style(enabled=False))
            # Wrapped to the terminal, so the sentence spans lines. Matched against
            # the flattened text rather than asserting where the breaks landed.
            flat = " ".join(text.split())
            assert "baseline on their own" in flat or "baseline on its own" in flat
            assert "20 nodes were tested" in flat
            return
        pytest.fail("no null history in 60 draws withheld an interval")

    def test_the_note_does_not_claim_those_intervals_are_chance(self):
        """One of them may be the genuinely bad node the correction cost us, so the
        sentence has to be about what an interval alone can support."""
        from slurmpast.render import held_back_note

        note = held_back_note(2, 20)
        assert "not yet evidence" in note
        assert "about one in twenty" in note

    def test_the_note_is_grammatical_either_way(self):
        from slurmpast.render import held_back_note

        assert held_back_note(1, 20).startswith("1 interval clears the baseline on its own")
        assert held_back_note(3, 20).startswith("3 intervals clear the baseline on their own")

    def test_the_note_pluralises_the_table_size_too(self):
        """The half of the sentence the count-of-intervals check above never read.

        One node clearing MIN_SAMPLES while the rest fall short is the ordinary
        shape of a short window, and it produced "1 nodes were tested" -- inside a
        sentence that takes care to write "1 interval" rather than "1 intervals".
        """
        from slurmpast.render import held_back_note

        assert "1 node was tested" in held_back_note(1, 1)
        assert "1 nodes" not in held_back_note(1, 1)
        # The control: above one, nothing changes.
        assert "20 nodes were tested" in held_back_note(1, 20)

    def test_the_exclude_header_names_the_family_it_corrected_over(self):
        from slurmpast.index import History
        from slurmpast.report import Style, render_nodes

        jobs = _placements("midway3-0385", 19, 36) + _placements(
            "midway3-0600", 12, 218, job_id_base=5000
        )
        text = render_nodes(History(jobs), metric="failure", style=Style(enabled=False))
        assert "after correcting for 2 nodes tested" in text
        assert "#SBATCH --exclude=midway3-0385" in text

    def test_the_exclude_header_names_the_noun_at_one_node_too(self):
        """ "after correcting for 1 tested" is what `--demo` printed: an unfinished
        clause, and the noun is supplied two lines further down the same screen by
        `held_back_note`."""
        from slurmpast.render import nodes_correction_note

        assert nodes_correction_note(1) == (
            "worse than every other node, after correcting for 1 node tested:"
        )
        assert nodes_correction_note(7) == (
            "worse than every other node, after correcting for 7 nodes tested:"
        )


class TestEmptyTablesSayWhyNotNothing:
    """An empty grid, or a grid of zeros, is not an answer. Reported as "some of
    these options ... are useless"."""

    def test_no_events_reports_in_words(self, healthy_job):
        from slurmpast.index import History
        from slurmpast.report import Style, render_nodes

        jobs = [
            healthy_job._replace(job_id=str(9000 + i), node_list="midway3-0600") for i in range(20)
        ]
        text = render_nodes(History(jobs), metric="hang", style=Style(enabled=False))
        assert "nothing to attribute to a node" in text
        assert "VERDICT" not in text  # no column header over an empty table

    def test_too_few_placements_reports_in_words(self, repeat_timeouts):
        """Every node fell below the sample threshold, so the table had a
        baseline line and then a bare column header with no rows."""
        from slurmpast.index import History
        from slurmpast.nodes import MIN_SAMPLES
        from slurmpast.report import Style, render_nodes

        few = list(repeat_timeouts)[:4]
        assert len(few) < MIN_SAMPLES
        text = render_nodes(History(few), metric="hang", style=Style(enabled=False))
        assert "placements a comparison needs" in text
        assert "VERDICT" not in text

    def test_a_real_signal_still_produces_a_table(self):
        from slurmpast.index import History
        from slurmpast.report import Style, render_nodes

        # _placements produces FAILED runs, so `failure` is the metric it carries.
        jobs = _placements("midway3-0385", 19, 36) + _placements(
            "midway3-0600", 12, 218, job_id_base=5000
        )
        text = render_nodes(History(jobs), metric="failure", style=Style(enabled=False))
        assert "VERDICT" in text
        assert "midway3-0385" in text


class TestAWorkloadIsTheFoldedName:
    """A parameter sweep is one piece of work and many literal names.

    Both `dominant_workload` and `node_table`'s filter compared raw `job.name`, so
    a sweep fragmented into one stratum per arm. A fragment is too small to test:
    every node fell under MIN_SAMPLES and a genuinely bad node produced an empty
    table, while an unrelated single-name workload won the "dominant" vote on
    fewer total runs.
    """

    def _sweep(self, healthy_job, bad_node="midway3-bad", arms=6, per_arm=6):
        """One sweep, distinct literal names, one node failing most of its runs."""
        jobs = []
        for arm in range(arms):
            for index in range(per_arm):
                on_bad = index < 3
                jobs.append(
                    healthy_job._replace(
                        job_id="s%d%d" % (arm, index),
                        name="sweep-e%d" % (arm * 7),
                        node_list=bad_node if on_bad else "midway3-good%d" % index,
                        state="FAILED" if (on_bad and index < 2) else "COMPLETED",
                    )
                )
        return jobs

    def test_the_sweep_is_one_stratum(self, healthy_job):
        jobs = self._sweep(healthy_job)
        assert len({j.name for j in jobs}) > 1, "fixture must have distinct raw names"
        assert dominant_workload(jobs, metric="failure") == "sweep-e#"

    def test_filtering_by_the_folded_name_keeps_every_arm(self, healthy_job):
        """18 placements pooled across 6 arms, versus 3 per arm on its own.

        MIN_SAMPLES is 10, so the fragmented version cannot produce a row at all --
        which is how a node failing most of its runs became invisible.
        """
        jobs = self._sweep(healthy_job)
        table = node_table(jobs, workload=dominant_workload(jobs, metric="failure"))
        bad = [r for r in table["rows"] if r["node"] == "midway3-bad"]
        assert bad, "the pooled sweep should give the bad node enough placements"
        assert bad[0]["trials"] == 18

    def test_raw_name_equality_would_have_found_nothing(self, healthy_job):
        """The old behaviour, asserted directly so the fix cannot silently revert."""
        jobs = self._sweep(healthy_job)
        one_arm = [j for j in jobs if j.name == "sweep-e7"]
        assert len(one_arm) == 6
        assert node_table(one_arm)["rows"] == []

    def test_a_single_name_workload_still_matches_itself(self, healthy_job):
        jobs = [healthy_job._replace(job_id=str(i), name="node-evaluation") for i in range(12)]
        table = node_table(jobs, workload="node-evaluation")
        assert sum(r["trials"] for r in table["rows"]) == 12


class TestTheExcludeLineSaysWhatItLeftOut:
    """`suggest_exclude` caps at 8, which is right, but it was silent.

    The paste-ready line read as the complete answer while the table above it
    showed more rows with the same verdict. Every other truncation here names its
    tail.
    """

    def _table(self, worse):
        return {"rows": [{"node": "n%d" % i, "verdict": "worse"} for i in range(worse)]}

    def test_nothing_left_out_when_under_the_cap(self):
        assert excluded_tail(self._table(5)) == 0

    def test_the_remainder_is_counted(self):
        assert excluded_tail(self._table(12)) == 4
        assert len(suggest_exclude(self._table(12))) == 8

    def test_it_agrees_with_the_list_it_describes(self):
        table = self._table(11)
        assert len(suggest_exclude(table)) + excluded_tail(table) == 11
