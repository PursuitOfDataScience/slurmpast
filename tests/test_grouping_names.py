"""Job-name normalization.

Measured motivation: a real seven-month history has 1,624 distinct job names
across 6,576 jobs. Grouping on raw names yields 1,687 groups -- no better than
the flat list the rollup exists to replace. Collapsing digit runs folds that to
591, and the top 12 then cover 81.5% of all weighted resource.
"""

from slurmpast.index import build_groups
from slurmpast.patterns import normalize_name


class TestNormalizeName:
    def test_sweep_coordinates_collapse(self):
        """s1e20 / s2e47 / s3e83 are one sweep, 300 distinct names in reality."""
        assert normalize_name("s1e20") == normalize_name("s2e47") == "s#e#"

    def test_parameter_suffix_collapses(self):
        assert normalize_name("att-speed-23") == normalize_name("att-speed-40") == "att-speed-#"

    def test_underscore_variant(self):
        assert normalize_name("mid85_059") == normalize_name("mid85_067") == "mid#_#"

    def test_plain_name_untouched(self):
        assert normalize_name("node-evaluation") == "node-evaluation"

    def test_dates_collapse(self):
        """Each date field becomes its own placeholder.

        Adjacent placeholders are deliberately not merged into one -- folding
        ``#-#-#`` to ``#`` would also put ``mid85_059`` and an unrelated
        ``mid42`` in the same group. Dated runs still group together, which is
        the point.
        """
        assert normalize_name("tool-bench-2026-03-15") == "tool-bench-#-#-#"
        assert normalize_name("tool-bench-2026-03-15") == normalize_name("tool-bench-2026-04-01")

    def test_long_compound_name(self):
        got = normalize_name("cot-8092-h200-openended-strict-620")
        assert got == "cot-#-h#-openended-strict-#"

    def test_empty_name(self):
        assert normalize_name("") == "?"
        assert normalize_name(None) == "?"

    def test_distinct_words_stay_distinct(self):
        """Conservative on purpose: over-collapsing blames one workload for
        another's failures, which is worse than a slightly longer list."""
        names = {"node-test", "node-testing", "node-evaluation", "test-node"}
        assert len({normalize_name(n) for n in names}) == 4

    def test_single_letter_variants_are_not_merged(self):
        assert normalize_name("nemotron-h200-x") != normalize_name("nemotron-h200-y")


class TestGroupingUsesPatterns:
    def test_variants_counted(self, cot_exp):
        jobs = [cot_exp._replace(job_id=str(i), name="att-speed-%d" % (i * 7)) for i in range(1, 6)]
        group = build_groups(jobs)[0]
        assert group.name == "att-speed-#"
        assert group.distinct_names == 5
        assert group.total == 5

    def test_single_name_group_reports_one_variant(self, repeat_timeouts):
        assert build_groups(repeat_timeouts)[0].distinct_names == 1

    def test_partition_still_separates(self, cot_exp):
        a = cot_exp._replace(job_id="1", name="run-1", partition="test")
        b = cot_exp._replace(job_id="2", name="run-2", partition="caslake")
        assert len(build_groups([a, b])) == 2


class TestTailSummary:
    def test_tail_reports_what_is_hidden(self, cot_exp):
        from slurmpast.index import History

        jobs = [
            cot_exp._replace(job_id=str(i), name="work-" + "abcdefghij"[i % 10]) for i in range(100)
        ]
        history = History(jobs)
        tail = history.tail_summary(3)
        assert "7 more workloads" in tail
        # "of the compute", matching the ordering note above the table. "Of the
        # resource" named a quantity the reader had never been given.
        assert "% of the compute" in tail

    def test_no_tail_when_everything_shown(self, repeat_timeouts):
        from slurmpast.index import History

        assert History(repeat_timeouts).tail_summary(50) == ""
