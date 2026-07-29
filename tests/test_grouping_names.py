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


class TestTheFoldIsOnlyShownWhenItStandsForSomething:
    """Reported: `exp-a#-newckpt · test · 1 job` above a row whose job is plainly
    called `exp-a35-newckpt`. The `#` summarises a family of names; with one name
    there is no family, and the notation hides the only name it stands for.

    Measured on a real 7-day history: 29 of 34 folded groups covered a single name.
    """

    def _groups(self, job, names):
        from slurmpast.index import build_groups

        return build_groups(
            [job._replace(job_id=str(1000 + i), name=n) for i, n in enumerate(names)]
        )

    def test_one_name_shows_that_name(self, healthy_job):
        group = self._groups(healthy_job, ["exp-a35-newckpt"])[0]
        assert group.name == "exp-a#-newckpt", "the key still folds, so a sibling joins it"
        assert group.label == "exp-a35-newckpt"
        assert "#" not in group.label

    def test_repeats_of_one_name_still_show_it(self, healthy_job):
        """Five runs of the same name are not a family either."""
        group = self._groups(healthy_job, ["argonne35-pretrain"] * 5)[0]
        assert group.total == 5 and group.distinct_names == 1
        assert group.label == "argonne35-pretrain"

    def test_two_names_keep_the_fold(self, healthy_job):
        group = self._groups(healthy_job, ["exp-a35-gate", "exp-a4-gate"])[0]
        assert group.distinct_names == 2
        assert group.label == "exp-a#-gate" == group.name

    def test_the_plain_overview_prints_the_label(self, healthy_job):
        from slurmpast.index import History
        from slurmpast.report import Style, render_overview

        text = render_overview(
            History([healthy_job._replace(name="exp-a35-newckpt")]), style=Style(enabled=False)
        )
        assert "exp-a35-newckpt" in text
        assert "exp-a#-newckpt" not in text

    def test_the_hash_footnote_goes_with_it(self, healthy_job):
        """The "#" stands for a name's digits note explained notation that is no
        longer on screen."""
        from slurmpast.index import History
        from slurmpast.report import Style, render_overview

        text = render_overview(
            History([healthy_job._replace(name="exp-a35-newckpt")]), style=Style(enabled=False)
        )
        assert '"#" stands for' not in text


class TestTheColumnsReconcile:
    """Reported: "15 in total but 10 success and 2 flagged, where are the rest 3?
    is the math wrong here?" It was not -- 5 of the 15 were cancelled, 2 of those
    held GPUs without computing and so are the 2 FLAGGED -- but nothing on screen
    let a reader close the arithmetic.
    """

    def _mixed(self, healthy_job):
        jobs = [
            healthy_job._replace(job_id=str(2000 + i), name="argonne35-pretrain") for i in range(6)
        ]
        for i in (4, 5):
            jobs[i] = jobs[i]._replace(state="CANCELLED by 1000")
        return jobs

    def test_cancelled_runs_are_in_runs_but_neither_completed_nor_flagged(self, healthy_job):
        from slurmpast.index import build_groups

        group = build_groups(self._mixed(healthy_job))[0]
        assert group.total == 6
        assert group.completed == 4
        assert group.cancelled == 2
        assert group.failed == 0
        # The gap the reader was doing arithmetic on.
        assert group.total - group.completed - group.problems == group.cancelled

    def test_the_overview_stays_within_its_four_lines(self, healthy_job):
        """The reconciliation belongs on the workload screen, not above the table:
        test_the_summary_is_brief caps that at four lines on purpose."""
        from slurmpast.index import History
        from slurmpast.report import Style, render_overview

        text = render_overview(History(self._mixed(healthy_job)), style=Style(enabled=False))
        head = text.split("#    JOB NAME")[0].strip().splitlines()
        body = [ln for ln in head if ln.strip() and not set(ln.strip()) <= {"-"}]
        assert len(body) <= 4, body
