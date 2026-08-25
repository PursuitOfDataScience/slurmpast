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

    def test_a_fold_that_kept_no_name_falls_back_too(self, healthy_job):
        """Reported from a real cluster-wide window, row 23 of the top 25:

            #   JOB NAME     PARTITION  RUNS COMPLETED FLAGGED  CPU-HOURS
            23  #            broadwl      20        14       6  559 / -

        20 runs and 559 CPU-hours under the name `#`. An all-digit job name --
        a date stamp -- folds to a single placeholder, so unlike `exp-a#-gate`
        this signature stands for a family and still says nothing. Several
        distinct names, so the one-name branch above does not catch it.
        """
        group = self._groups(healthy_job, ["20260821", "20260822", "20260823"])[0]
        assert group.name == "#", "the key still folds, so the three runs stay one workload"
        assert group.distinct_names == 3
        # `+2`, not a bare `20260823`. This assertion used to read `== "20260823"`
        # and the report's author was right that it should not: `#` was
        # uninformative but visibly a fold, while one real date on a row holding
        # three runs of three different dates is specific and wrong, and the RUNS
        # column then reads as three runs of one workload. The substitution is
        # still the fix -- the marker is what stops it overclaiming.
        assert group.label == "20260823 +2", group.label
        assert "#" not in group.label

    def test_a_date_with_separators_falls_back_as_well(self, healthy_job):
        """`2026-01` folds to `#-#`: separators are not information either."""
        group = self._groups(healthy_job, ["2026-01", "2026-02"])[0]
        assert group.name == "#-#"
        assert group.label == "2026-02 +1", group.label

    def test_a_fold_covering_one_name_carries_no_marker(self, healthy_job):
        """The control on the marker's scope. `distinct_names == 1` means the
        substituted name is the *only* name in the group, so it claims nothing the
        row cannot support and must stay clean -- an earlier round kept the count
        off the table as clutter, and that judgement still holds everywhere except
        the row where the label would otherwise imply singularity it lacks."""
        group = self._groups(healthy_job, ["20260822"])[0]
        assert group.distinct_names == 1
        assert group.label == "20260822", group.label

    def test_one_surviving_letter_is_enough_to_keep_the_fold(self, healthy_job):
        """The control on where the line is drawn. `a#` still names something and
        must keep folding -- substituting one arm's name would invent a workload
        narrower than the row's own RUNS column."""
        group = self._groups(healthy_job, ["a2026", "a2027"])[0]
        assert group.label == "a#" == group.name

    def test_the_plain_overview_prints_the_fallback(self, healthy_job):
        from slurmpast.index import History
        from slurmpast.report import Style, render_overview

        jobs = [
            healthy_job._replace(job_id=str(3000 + i), name=n)
            for i, n in enumerate(["20260821", "20260822"])
        ]
        text = render_overview(History(jobs), style=Style(enabled=False))
        assert "20260822" in text
        table = text.split("JOB NAME", 1)[1]
        assert " # " not in table, table

    def test_the_hash_footnote_goes_with_it(self, healthy_job):
        """The "#" stands for a name's digits note explained notation that is no
        longer on screen."""
        from slurmpast.index import History
        from slurmpast.report import Style, render_overview

        text = render_overview(
            History([healthy_job._replace(name="exp-a35-newckpt")]), style=Style(enabled=False)
        )
        assert '"#" stands for' not in text


class TestTheHashLegendFollowsWhatIsOnScreen:
    r"""Reported as a defect and withdrawn here: that the legend is appended "based
    on the data" while only the top 25 of 560 workloads are displayed, so a folded
    workload below the cutoff explains a symbol the reader cannot see.

    It is not. `render_overview` computes `shown = groups[:limit]` and the legend
    tests `shown`, so it is already conditioned on rendered rows.

    What produced the observation is the detection, not the tool. The check was
    `grep -cE '^\s+[0-9]+\s+#'`, which matches only a label *beginning* with `#` —
    and a fold that keeps letters does not. `fy#_s#_#_e#.#`, a real workload from
    that same cluster's window, contains `#` in five places and starts with `f`, so
    the grep returned 0 while a `#` was plainly on screen.

    Both halves are pinned below because the property was doubted, and because the
    fold-with-letters case is the one a naive check misses.
    """

    def _history(self, healthy_job, names):
        from slurmpast.index import History

        return History(
            [
                healthy_job._replace(job_id=str(7000 + i), name=n, user="u")
                for i, n in enumerate(names)
            ]
        )

    def test_a_hash_anywhere_in_a_shown_label_earns_the_legend(self, healthy_job):
        """Not just at the start. `fy#_s#_#_e#.#` is the shape that was missed."""
        from slurmpast.report import Style, render_overview

        history = self._history(healthy_job, ["fy1_s2_3_e4.5", "fy9_s8_7_e6.5"])
        assert any("#" in g.label for g in history.groups)
        text = render_overview(history, style=Style(enabled=False))
        assert '"#" stands for' in text, text

    def test_a_folded_workload_below_the_cutoff_does_not_earn_it(self, healthy_job):
        """The alleged defect, asserted as the behaviour it actually has. The
        folded group is last by compute, so `--limit 1` renders only the unfolded
        one and the legend must go with it."""
        from slurmpast.report import Style, render_overview

        jobs = [
            healthy_job._replace(job_id=str(7100 + i), name="steady", user="u", elapsed=9000.0)
            for i in range(4)
        ]
        jobs += [
            healthy_job._replace(job_id="7200", name="fy1_s2", user="u", elapsed=1.0),
            healthy_job._replace(job_id="7201", name="fy9_s8", user="u", elapsed=1.0),
        ]
        from slurmpast.index import History

        history = History(jobs)
        assert any("#" in g.label for g in history.groups), "the folded group must exist"
        text = render_overview(history, style=Style(enabled=False), limit=1)
        assert "fy#" not in text, text
        assert '"#" stands for' not in text, text


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


class TestEverySurfaceCallsAWorkloadTheSameThing:
    """The label rule reached the overview table but not the cross-run findings.

    `GroupStats.label` shows a group's one real job name instead of the fold, on
    the stated grounds that ``#`` "hides the one name it is standing in for and
    invents a family that does not exist". The findings in `patterns` named their
    groups `key[0]` -- the raw fold -- so one report said both things about one
    workload. Measured on pythia (Slurm 24.11.5), a two-day cluster-wide window:

        overview   m110_robustness_current_source_20260823_c9ea44e_v1   20 runs
        patterns   20 of 20 runs of m#_robustness_current_source_#_c#ea#e_v# failed

    Both surfaces now read the rule from :func:`patterns.workload_label`.

    Every name here carries digits on purpose. The suite already had tests for the
    table's half of this rule, and they passed throughout, because their fixtures
    are named `cot-exp` and `rc-tok-github_code` -- no digits, so the fold is the
    identity and a surface printing the fold is indistinguishable from one
    printing the name.
    """

    def _series(self, job, names, state="TIMEOUT"):
        return [
            job._replace(job_id=str(48000000 + i), name=name, state=state)
            for i, name in enumerate(names)
        ]

    def test_workload_label_prefers_the_one_real_name(self, healthy_job):
        from slurmpast.patterns import workload_label

        jobs = self._series(healthy_job, ["m110_robust_20260823_v1"] * 6)
        assert workload_label("m#_robust_#_v#", jobs) == "m110_robust_20260823_v1"

    def test_workload_label_keeps_the_fold_for_a_real_family(self, healthy_job):
        """The control. Two names *are* a family, and the fold is what names it."""
        from slurmpast.patterns import workload_label

        jobs = self._series(healthy_job, ["m110_robust_20260823_v1", "m110_robust_20260824_v1"])
        assert workload_label("m#_robust_#_v#", jobs) == "m#_robust_#_v#"

    def test_workload_label_does_not_depend_on_member_order(self, healthy_job):
        """`GroupStats.jobs` is sorted newest-first; the lists in `patterns` are
        not sorted at all, so the shared rule may not read position 0."""
        from slurmpast.patterns import workload_label

        jobs = self._series(healthy_job, ["run_2026_a7"] * 4)
        assert workload_label("run_#_a#", list(reversed(jobs))) == "run_2026_a7"

    def test_the_repeat_failure_finding_uses_the_name_not_the_fold(self, healthy_job):
        from slurmpast.patterns import find_repeat_failures

        jobs = self._series(healthy_job, ["m110_robust_20260823_v1"] * 8)
        findings = find_repeat_failures(jobs)
        assert findings, "8 identical timeouts should be a repeat-failure group"
        evidence = " ".join(f.evidence for f in findings)
        assert "m110_robust_20260823_v1" in evidence, evidence
        assert "m#_robust_#_v#" not in evidence, evidence

    def test_the_repeat_failure_finding_still_folds_a_real_family(self, healthy_job):
        """The control on the fix, not on the bug: with two names the fold is
        right, and a fix that always substituted a real name would be wrong here."""
        from slurmpast.patterns import find_repeat_failures

        names = ["m110_robust_20260823_v1"] * 4 + ["m110_robust_20260824_v1"] * 4
        findings = find_repeat_failures(self._series(healthy_job, names))
        assert findings
        evidence = " ".join(f.evidence for f in findings)
        assert "m#_robust_#_v#" in evidence, evidence

    def test_the_overview_and_the_patterns_section_agree(self, healthy_job):
        """The property that matters, stated over the rendered surfaces rather than
        the helper: one workload, one name, whatever is reading it.

        Both renderers are called, because `render_overview` draws only the table
        -- the cross-run section is `render_patterns`, and the CLI composes the
        two. Asserting over the overview alone made this test pass with the defect
        still in place, which is the failure mode this suite keeps producing.
        """
        from slurmpast.index import History
        from slurmpast.report import Style, render_overview, render_patterns

        history = History(self._series(healthy_job, ["m110_robust_20260823_v1"] * 8))
        plain = Style(enabled=False)
        table = render_overview(history, style=plain)
        patterns = render_patterns(history, style=plain)
        assert "cross-run patterns" in patterns, "the finding has to be on screen to be named"
        for surface, text in (("overview", table), ("patterns", patterns)):
            assert "m110_robust_20260823_v1" in text, (surface, text)
            assert "m#_robust_#_v#" not in text, (surface, text)

    def test_the_memory_search_finding_uses_the_name_too(self, oom_series):
        """The third and fourth `key[0]` sites, on the OOM path. Renamed onto a
        digit-bearing single name, because `rc-tok-github_code` cannot show this."""
        from slurmpast.patterns import find_memory_search

        renamed = [j._replace(name="tok110_shard7") for j in oom_series]
        findings = find_memory_search(renamed)
        assert findings, "the bisection series should still be found"
        evidence = " ".join(f.evidence for f in findings)
        assert "tok110_shard7" in evidence, evidence
        assert "tok#_shard#" not in evidence, evidence
