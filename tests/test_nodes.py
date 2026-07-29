import pytest

from slurmpast.nodes import (
    compress_nodelist,
    dominant_workload,
    expand_nodelist,
    node_table,
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
