"""Column layout: fit the content, inside the terminal, without canyons.

Two complaints shaped this, in order:

* "the horizontal space is unoccupied on the right side" -- widths were hard
  coded, so the overview stopped dead at 94 columns while still truncating job
  names to 24 characters.
* "why is the job name column taking much space and it has a ton of empty
  space" -- the first fix stretched flexible columns to a fixed cap regardless of
  what they held, which put 26 cells of nothing inside one column.

So a column grows to fit its content and no further, and width that no column
needs is left unused. A compact table with space to its right is what every
well-behaved table does; a canyon inside a column is not.
"""

import pytest

from slurmpast.render import Column, fit_columns

SPEC = (
    Column("#", 4),
    Column("JOB NAME", 12, flex=True, grow_to=44),
    Column("PARTITION", 9, drop=2),
    Column("RUNS", 5),
    Column("COMPLETED", 9, drop=1),
    Column("CPU-HOURS", 11),
)


def filled(layout, padding=2):
    return sum(width for _, width in layout) + padding * len(layout)


class TestFitsInsideTheTerminal:
    @pytest.mark.parametrize("available", [60, 70, 84, 96, 110, 135, 160, 200])
    def test_never_wider_than_what_it_was_given(self, available):
        assert filled(fit_columns(SPEC, available)) <= available

    def test_a_wider_terminal_never_produces_a_narrower_table(self):
        widths = [filled(fit_columns(SPEC, a)) for a in range(60, 200)]
        assert widths == sorted(widths)


class TestGrowsToFitContentAndNoFurther:
    def test_a_flex_column_reaches_its_longest_value(self):
        content = {"JOB NAME": 30}
        assert dict(fit_columns(SPEC, 200, content=content))["JOB NAME"] == 30

    def test_a_flex_column_does_not_exceed_its_longest_value(self):
        """The canyon: 44 cells of column holding 18 characters of name."""
        content = {"JOB NAME": 18}
        assert dict(fit_columns(SPEC, 200, content=content))["JOB NAME"] == 18

    def test_short_content_still_gets_the_declared_minimum(self):
        """A table of three-letter names should not look cramped either."""
        layout = dict(fit_columns(SPEC, 200, content={"JOB NAME": 3}))
        assert layout["JOB NAME"] == 12

    def test_the_cap_still_binds_on_very_long_content(self):
        assert dict(fit_columns(SPEC, 300, content={"JOB NAME": 500}))["JOB NAME"] == 44

    def test_width_nothing_needs_is_left_unused(self):
        layout = fit_columns(SPEC, 200, content={"JOB NAME": 14})
        assert filled(layout) < 200

    def test_without_content_it_still_grows_to_the_cap(self):
        """Callers that cannot measure their cells keep the old behaviour."""
        assert dict(fit_columns(SPEC, 200))["JOB NAME"] == 44

    def test_a_fixed_column_never_grows(self):
        for available in (96, 135, 200):
            layout = dict(fit_columns(SPEC, available, content={"JOB NAME": 40}))
            assert layout["RUNS"] == 5
            assert layout["#"] == 4


class TestNarrowTerminals:
    def test_droppable_columns_go_in_the_declared_order(self):
        assert "COMPLETED" not in dict(fit_columns(SPEC, 58))
        assert "PARTITION" not in dict(fit_columns(SPEC, 48))

    def test_columns_without_a_drop_order_always_survive(self):
        layout = dict(fit_columns(SPEC, 20))
        for label in ("#", "JOB NAME", "RUNS", "CPU-HOURS"):
            assert label in layout

    def test_at_least_one_column_always_remains(self):
        assert fit_columns(SPEC, 1)


class TestInvariants:
    def test_a_column_is_never_narrower_than_its_own_header(self):
        """A truncated "WALL TIM" is the same defect as a cryptic abbreviation,
        just self-inflicted."""
        for available in (40, 84, 135, 200):
            for label, width in fit_columns(SPEC, available):
                assert width >= len(label), (label, width, available)

    def test_content_wider_than_the_header_still_wins(self):
        layout = dict(fit_columns(SPEC, 200, content={"JOB NAME": 25}))
        assert layout["JOB NAME"] == 25


class TestTwoColumnDetailRows:
    """Reported as "there is ample amount of empty space on the right side.
    should we put at least two things at the same row" -- the detail sections used
    one row per line and about 40 of 120 columns."""

    def _rows(self, *values):
        return [("label%d" % i, v, None) for i, v in enumerate(values)]

    def test_short_values_pair_up(self):
        from slurmpast.render import pair_rows

        groups = pair_rows(self._rows("a", "b", "c", "d"))
        assert [len(g) for g in groups] == [2, 2]

    def test_an_odd_row_ends_alone(self):
        from slurmpast.render import pair_rows

        assert [len(g) for g in pair_rows(self._rows("a", "b", "c"))] == [2, 1]

    def test_a_long_value_keeps_its_own_line(self):
        """Truncating a workdir to fit a column trades one defect for a worse one."""
        from slurmpast.render import PAIR_VALUE_WIDTH, pair_rows

        long_value = "/" + "x" * (PAIR_VALUE_WIDTH + 5)
        groups = pair_rows(self._rows("a", long_value, "b"))
        assert [len(g) for g in groups] == [1, 1, 1]
        assert groups[1][0][1] == long_value

    def test_a_gauged_row_keeps_its_own_line(self):
        from slurmpast.render import pair_rows

        rows = [("a", "1", None), ("bar", "2", 50.0), ("c", "3", None)]
        assert [len(g) for g in pair_rows(rows)] == [1, 1, 1]

    def test_no_rows_no_groups(self):
        from slurmpast.render import pair_rows

        assert pair_rows([]) == []


class TestOneSpecTwoRenderers:
    """The drift this guards against actually happened.

    Both front ends draw the same two tables, but the specs lived next to the
    dashboard only and ``--plain`` re-declared its own with hardcoded ``%``
    widths. They diverged in both directions: the dashboard had already dropped
    its NEVER RAN column and its "(2 names)" suffix while ``--plain`` was still
    printing both, and the plain job list was laid out 135 cells wide, so on a
    100-column terminal every row wrapped.
    """

    def test_the_dashboard_uses_the_shared_specs(self):
        from slurmpast import render, tui

        assert tui._OVERVIEW_COLUMNS is render.OVERVIEW_COLUMNS
        assert tui._JOB_COLUMNS is render.JOB_COLUMNS

    def test_the_plain_renderer_uses_the_shared_specs(self):
        """Checked through the output, not the import: a module can import a spec
        and then not use it."""
        from slurmpast.demo import history
        from slurmpast.render import JOB_COLUMNS
        from slurmpast.report import Style, render_list

        text = render_list(history()[:3], style=Style(enabled=False))
        header = text.splitlines()[0]
        shown = [c.label for c in JOB_COLUMNS if c.label in header]
        assert shown, header
        # Same order as the spec, and nothing invented.
        positions = [header.index(label) for label in shown]
        assert positions == sorted(positions)

    def test_a_cpu_only_history_collapses_the_paired_cell_in_both(self):
        from slurmpast.render import HOURS_PAIR_LABEL, OVERVIEW_COLUMNS, cpu_only_columns

        labels = [c.label for c in cpu_only_columns(OVERVIEW_COLUMNS)]
        assert HOURS_PAIR_LABEL not in labels
        assert "CPU-HOURS" in labels
        assert len(labels) == len(OVERVIEW_COLUMNS)


class TestTextTable:
    # RUNS is declared align="right" in OVERVIEW_COLUMNS, which registers its
    # alignment at import -- text_table looks alignment up by label, so a layout
    # reusing that label gets it for free.
    LAYOUT = [("NAME", 8), ("RUNS", 5), ("LAST", 10)]

    def _rows(self):
        return [{"NAME": "midtrain", "RUNS": "14", "LAST": "2026-07-18"}]

    def test_the_rule_spans_the_widest_row_not_the_nominal_total(self):
        """A right-aligned last column leaves the nominal width unreached, and a
        rule hanging past the widest row reads as a rendering fault."""
        from slurmpast.render import text_table

        lines = text_table(self.LAYOUT, self._rows())
        rule = lines[1].strip()
        assert set(rule) == {"-"}
        assert len(lines[1]) == max(len(line) for line in lines)

    def test_the_header_carries_no_trailing_run_of_spaces(self):
        from slurmpast.render import text_table

        header = text_table(self.LAYOUT, self._rows())[0]
        assert header == header.rstrip()

    def test_right_aligned_columns_line_their_digits_up(self):
        from slurmpast.render import text_table

        rows = [{"NAME": "a", "RUNS": "7"}, {"NAME": "b", "RUNS": "1101"}]
        lines = text_table(self.LAYOUT, rows)
        assert lines[-2].rstrip().endswith("   7")
        assert lines[-1].rstrip().endswith("1101")

    def test_colour_is_not_counted_toward_the_column_width(self):
        """An ANSI wrapper is nine characters ``%-*s`` counts and the terminal does
        not, so colouring before padding shifts every following cell."""
        from slurmpast.render import text_table

        def style(text, *names):
            return "\033[31m" + text + "\033[0m" if names else text

        plain = text_table(self.LAYOUT, [{"NAME": "midtrain", "RUNS": "14"}])
        painted = text_table(
            self.LAYOUT, [{"NAME": ("midtrain", "red"), "RUNS": "14"}], style=style
        )
        assert "\033[31m" in painted[-1]
        assert painted[-1].replace("\033[31m", "").replace("\033[0m", "") == plain[-1]

    def test_a_missing_cell_is_blank_not_a_crash(self):
        from slurmpast.render import text_table

        assert text_table(self.LAYOUT, [{"NAME": "x"}])[-1].strip() == "x"


class TestPlainOutputFitsATerminal:
    """Measured, not assumed. Every one of these overran 100 columns before the
    shared layout landed: the overview by 14 cells, the job list by 35 (all 42 of
    its rows), the sizing block by 8.
    """

    @staticmethod
    def _views(style):
        from slurmpast.demo import history
        from slurmpast.index import History
        from slurmpast.report import (
            render_list,
            render_nodes,
            render_overview,
            render_patterns,
            render_sizing,
        )

        h = History(history(), window="last 7 days (2026-07-21 to now)")
        # A node name no fixed width survives. The demo's are 12 characters, which
        # is what let `render_nodes` keep a hand-rolled "%-16s" through two audits;
        # real clusters run to `queue1-dy-c5xlarge-1` and longer. The workload name
        # goes with it, for the same reason and one audit later: the demo's is
        # `cot-exp`, and that is what let render_nodes' "controlled for workload"
        # line stay unwrapped through two more.
        wide = History(
            [
                j._replace(
                    node_list=j.node_list.replace("midway3-", "gpu-compute-node-a100-"),
                    name=j.name.replace(
                        "cot-exp", "nemotron-batch-h7-tokenize-shards-stage3-retry-2"
                    ),
                )
                for j in history()
            ],
            window="last 7 days (2026-07-21 to now)",
        )
        return {
            "overview": render_overview(h, style=style),
            "list": render_list(list(h.jobs), style=style),
            "patterns": render_patterns(h, style=style),
            "nodes": render_nodes(h, style=style),
            "nodes-long-names": render_nodes(wide, style=style),
            "sizing": render_sizing(h, style=style),
        }

    # Each view's own floor: below this the table it draws has no droppable column
    # left and cannot get narrower. Asserted against rather than assumed, so a new
    # never-dropped column moves the bar instead of silently breaking the promise.
    @staticmethod
    def _floor(name):
        from slurmpast.render import JOB_COLUMNS, NODE_COLUMNS, table_floor

        if name == "list":
            return table_floor(JOB_COLUMNS)
        if name.startswith("nodes"):
            return table_floor(NODE_COLUMNS)
        return 0

    @staticmethod
    def _table_lines(text):
        """The header, rule and rows of the last table in a block.

        Scoped to the table on purpose. A wrapped sentence is what sentences do; a
        wrapped table row destroys the column alignment that is the whole point of
        a table. Only the second is a defect.
        """
        lines = text.splitlines()
        rules = [i for i, line in enumerate(lines) if line.strip() and set(line.strip()) == {"-"}]
        if not rules:
            return []
        return [line for line in lines[max(0, rules[-1] - 1) :] if line.strip()]

    @pytest.mark.parametrize("columns", ["60", "66", "74", "80", "100", "120"])
    def test_no_table_row_overruns_the_terminal(self, monkeypatch, columns):
        """Every view that draws a table, not a chosen two.

        This asserted over `("overview", "list")` while `_views` built five, so the
        node table -- the one still hand-formatted at fixed widths -- was exempt from
        the invariant it was breaking, and the sibling rule test iterating all five
        never caught it because a rule is drawn from the widest *row*.

        The narrow widths are the round-five addition. It was parametrized over
        80/100/120 while `report.PLAIN_MIN_WIDTH` declares a floor of 60, so the
        whole 60-79 band -- the band where anything actually breaks -- was
        unmeasured. Each view is held to its own `table_floor` rather than to a
        flat 60, because a table with no droppable column left genuinely cannot
        get narrower and pretending otherwise is how the 60 came to be claimed.
        """
        from slurmpast.report import Style

        monkeypatch.setenv("COLUMNS", columns)
        for name, text in self._views(Style(enabled=False)).items():
            allowed = max(int(columns), self._floor(name))
            for line in self._table_lines(text):
                assert len(line) <= allowed, "%s: %d > %d -- %r" % (
                    name,
                    len(line),
                    allowed,
                    line,
                )

    @pytest.mark.parametrize("columns", ["60", "66", "74", "80", "100", "120"])
    def test_no_job_detail_line_overruns_the_terminal(self, monkeypatch, columns):
        """The post-mortem, which `_views` never built and so nothing measured.

        It has no table to scope to -- every line is prose, a pair row or a gauge
        row, and all three are supposed to fit. Three did not, at *any* width: the
        gauge rows carried their detail inline for a fixed 86 cells, a sentence in
        a single-pair value went out at its full length, and a finding title was
        the one line of its three that was never wrapped.
        """
        from slurmpast.demo import history
        from slurmpast.report import Style, render_job

        monkeypatch.setenv("COLUMNS", columns)
        for job in history():
            text, _ = render_job(job, style=Style(enabled=False))
            for line in text.splitlines():
                assert len(line) <= int(columns), "%s: %d > %s -- %r" % (
                    job.job_id,
                    len(line),
                    columns,
                    line,
                )

    @pytest.mark.parametrize("columns", ["60", "66", "74", "80", "100", "120"])
    def test_no_step_table_row_overruns_the_terminal(self, monkeypatch, columns):
        """`--steps`, which neither width test built.

        The sibling above renders every demo job and never passes `show_steps`, so
        the fourth table this codebase draws was measured at no width at all --
        while the three in `_views` are measured at six. It happens to behave: it
        goes through `STEP_COLUMNS` like the others and bottoms out at its own
        floor. Pinned so that stays a fact rather than a coincidence, and so a
        never-dropped column added to the spec moves the bar instead of quietly
        breaking the promise.

        Indented by four inside the post-mortem, not the two `table_floor`
        assumes, which is what makes this floor 67 and not 65.
        """
        from slurmpast.demo import history
        from slurmpast.render import STEP_COLUMNS, table_floor
        from slurmpast.report import Style, render_job

        monkeypatch.setenv("COLUMNS", columns)
        floor = table_floor(STEP_COLUMNS, indent=4)
        allowed = max(int(columns), floor)
        drawn = 0
        for job in history():
            text, _ = render_job(job, style=Style(enabled=False), show_steps=True)
            for line in self._table_lines(text):
                drawn += 1
                assert len(line) <= allowed, "%s: %d > %d -- %r" % (
                    job.job_id,
                    len(line),
                    allowed,
                    line,
                )
        assert drawn, "no step table was drawn -- the demo lost its steps"

    def test_a_gauge_row_keeps_its_detail_inline_where_there_is_room(self, monkeypatch):
        """The narrow-terminal form is a fallback, not the new shape.

        `resource_rows` is deliberately the same row idiom as slurmwatch's live
        view, so at the width it was designed for the detail stays on the row and
        the output is unchanged.
        """
        from slurmpast.demo import history
        from slurmpast.render import resource_rows

        monkeypatch.setenv("COLUMNS", "100")
        over = [
            j
            for j in history()
            if j.mem_limit_bytes and j.max_rss and j.max_rss > j.mem_limit_bytes
        ]
        assert over, "the demo needs a MaxRSS-above-limit job for this"
        rows = [r.plain for r in resource_rows(over[0], max_width=100)]
        assert any("· an upper bound, over the" in r and " MEM " in r for r in rows), rows
        assert len(rows) == 3, rows

        narrow = [r.plain for r in resource_rows(over[0], max_width=80)]
        assert len(narrow) == 4, narrow
        assert max(len(r) for r in narrow) <= 80, narrow
        # Moved, not dropped: the figure that says the gauge is a ceiling survives.
        assert any("an upper bound, over the" in r for r in narrow), narrow

    @pytest.mark.parametrize("columns", ["80", "100", "120", "200"])
    def test_no_rule_overruns_the_terminal(self, monkeypatch, columns):
        """A rule wider than the terminal wraps to a stray second line of dashes --
        the one thing on screen that cannot be read as anything but a fault."""
        from slurmpast.report import Style

        monkeypatch.setenv("COLUMNS", columns)
        for name, text in self._views(Style(enabled=False)).items():
            for line in text.splitlines():
                if line.strip() and set(line.strip()) == {"-"}:
                    assert len(line) <= int(columns), "%s: %d > %s" % (name, len(line), columns)

    @pytest.mark.parametrize("columns", ["80", "200"])
    def test_prose_wraps_to_the_terminal_it_is_printed_on(self, monkeypatch, columns):
        """The wrap widths were hardcoded at 72, 82 and 84, so a finding hard-broke
        mid-sentence two thirds of the way across a wide terminal."""
        from slurmpast.report import Style

        monkeypatch.setenv("COLUMNS", columns)
        text = self._views(Style(enabled=False))["sizing"]
        widest = max(len(line) for line in text.splitlines())
        assert widest <= int(columns)
        if columns == "200":
            # And it actually used the room, rather than stopping at the old 84.
            assert widest > 84

    def test_piped_output_assumes_a_pasteable_width(self, monkeypatch):
        """No terminal to ask, so the fallback has to be a width a pasted table
        survives in -- a ticket comment, a code review, a chat message."""
        from slurmpast.report import PLAIN_FALLBACK_WIDTH, Style

        monkeypatch.delenv("COLUMNS", raising=False)
        monkeypatch.setattr(
            "slurmpast.report.shutil.get_terminal_size",
            lambda fallback=(80, 24): __import__("os").terminal_size(fallback),
        )
        for name, text in self._views(Style(enabled=False)).items():
            widest = max(len(line) for line in text.splitlines())
            assert widest <= PLAIN_FALLBACK_WIDTH, "%s: %d" % (name, widest)

    def test_the_widest_real_history_still_fits_the_fallback(self, monkeypatch):
        """The demo history has short names; a real one has 42-character workload
        names and five-figure hour counts."""
        from slurmpast.demo import history
        from slurmpast.index import History
        from slurmpast.report import PLAIN_FALLBACK_WIDTH, Style, render_overview

        monkeypatch.setenv("COLUMNS", str(PLAIN_FALLBACK_WIDTH))
        stretched = [
            j._replace(name="a-very-long-workload-name-like-real-ones-%d" % i)
            for i, j in enumerate(history())
        ]
        text = render_overview(History(stretched), style=Style(enabled=False))
        for line in self._table_lines(text):
            assert len(line) <= PLAIN_FALLBACK_WIDTH, repr(line)

    def test_a_narrow_terminal_drops_columns_rather_than_wrapping(self, monkeypatch):
        from slurmpast.report import Style

        monkeypatch.setenv("COLUMNS", "80")
        wide_header = self._views(Style(enabled=False))["list"].splitlines()[0]
        monkeypatch.setenv("COLUMNS", "160")
        narrow_header = self._views(Style(enabled=False))["list"].splitlines()[0]
        assert len(wide_header) < len(narrow_header)


class TestSpendingTheLeftoverWhenAskedTo:
    """``fill_to`` exists because the two callers want opposite things: a pasted
    table should be as narrow as its content so it survives a ticket comment, while
    a 100-cell table centred in a 150-column terminal reads as thin.
    """

    CONTENT = {"JOB NAME": 14}

    def test_zero_leaves_it_unused_as_before(self):
        assert filled(fit_columns(SPEC, 200, content=self.CONTENT)) < 200

    def test_it_fills_exactly_what_it_was_told_to(self):
        assert filled(fit_columns(SPEC, 200, content=self.CONTENT, fill_to=160)) == 160

    def test_it_never_exceeds_what_is_available(self):
        layout = fit_columns(SPEC, 120, content=self.CONTENT, fill_to=500)
        assert filled(layout) <= 120

    def test_a_target_below_the_natural_width_changes_nothing(self):
        natural = fit_columns(SPEC, 200, content=self.CONTENT)
        assert fit_columns(SPEC, 200, content=self.CONTENT, fill_to=40) == natural

    def test_the_leftover_goes_in_proportion_not_to_one_column(self):
        """The anti-canyon property. Handing one flex column the whole leftover is
        the reported 44-cells-around-18-characters defect; equal shares are wrong
        the other way, turning a 3-cell "#" holding one digit into 13 cells."""
        natural = dict(fit_columns(SPEC, 200, content=self.CONTENT))
        wide = dict(fit_columns(SPEC, 200, content=self.CONTENT, fill_to=180))
        grew = {label: wide[label] - natural[label] for label in natural}
        assert grew["JOB NAME"] > grew["#"], grew
        # Proportional, so the ratio of widths is roughly preserved rather than
        # every column converging on the same size.
        assert wide["#"] < wide["RUNS"] < wide["JOB NAME"], wide
        # Shares track width: JOB NAME is ~3.5x "#" here, so it takes ~3.5x more.
        assert grew["JOB NAME"] >= 3 * grew["#"], grew

    def test_a_realistic_fill_barely_touches_the_narrow_columns(self):
        """The screen case: 64 cells of content in a 100-cell terminal. The dramatic
        growth in the test above comes from filling to nearly 3x the natural width,
        which no terminal asks for."""
        natural = dict(fit_columns(SPEC, 100, content=self.CONTENT))
        wide = dict(fit_columns(SPEC, 100, content=self.CONTENT, fill_to=98))
        assert wide["#"] - natural["#"] <= 2, (natural["#"], wide["#"])

    def test_it_lands_on_the_target_exactly(self):
        """Proportional shares round down, so the remainder has to go somewhere."""
        for target in range(120, 181, 7):
            assert filled(fit_columns(SPEC, 200, content=self.CONTENT, fill_to=target)) == target

    def test_the_numbers_are_not_left_huddled_at_one_end(self):
        """Spreading only across the flex columns would widen JOB NAME and leave
        RUNS, COMPLETED and CPU-HOURS bunched together."""
        natural = dict(fit_columns(SPEC, 200, content=self.CONTENT))
        wide = dict(fit_columns(SPEC, 200, content=self.CONTENT, fill_to=180))
        for label in ("RUNS", "COMPLETED", "CPU-HOURS"):
            assert wide[label] > natural[label], label

    def test_a_dropped_column_stays_dropped(self):
        """Filling is not an excuse to re-add a column that did not fit."""
        narrow = fit_columns(SPEC, 60, content=self.CONTENT)
        filled_narrow = fit_columns(SPEC, 60, content=self.CONTENT, fill_to=60)
        assert [label for label, _ in narrow] == [label for label, _ in filled_narrow]


class TestATruncatedListSaysSo:
    """Everything else here names its tail; the job list did not.

    `cli.py` pre-sliced the list to `--limit` before `render_list` could compare
    against it, so the "… N more" line was unreachable in production and `-n 5`
    showed 5 of 28 problem jobs in silence.
    """

    def test_the_tail_is_named(self):
        from slurmpast.demo import history
        from slurmpast.report import Style, render_list

        jobs = history()
        assert len(jobs) > 5
        text = render_list(jobs, style=Style(enabled=False), limit=5)
        assert "%d more" % (len(jobs) - 5) in text, text

    def test_nothing_is_claimed_when_nothing_is_hidden(self):
        from slurmpast.demo import history
        from slurmpast.report import Style, render_list

        jobs = history()[:4]
        assert "more" not in render_list(jobs, style=Style(enabled=False), limit=10)


class TestTheOverviewCaptionDescribesTheTableBelowIt:
    """ "ordered by compute used" was printed under every `--sort`.

    The dashboard has always got this right -- it appends "by <mode>" only when the
    mode is not the default -- while the plain caption asserted a cost ordering over
    an alphabetical table.
    """

    def _caption(self, sort):
        from slurmpast.demo import history
        from slurmpast.index import History
        from slurmpast.report import Style, render_overview

        text = render_overview(History(history()), style=Style(enabled=False), sort=sort)
        return next(line for line in text.splitlines() if "ordered by" in line)

    def test_the_default_still_says_compute_used(self):
        assert "ordered by compute used" in self._caption("cost")

    def test_another_sort_names_itself_instead(self):
        from slurmpast.index import sort_label

        caption = self._caption("name")
        assert "ordered by compute used" not in caption
        assert "ordered by %s" % sort_label("name") in caption

    def test_the_exchange_rate_survives_either_way(self):
        """It is load-bearing: without it a row outranking another looks arbitrary."""
        for sort in ("cost", "name", "recent"):
            assert "GPU-hour" in self._caption(sort)


class TestTruncationSaysSoInATable:
    """`value[:width]` with no marker. A job name stays recognisable truncated; a
    hostlist does not -- `midway3-[0600-0607,0611]` came out as `midway3-[0600`,
    and at a 12-cell column `midway3-0600,midway3-0611` came out as a complete,
    valid, real `midway3-0600` for a job that ran on two nodes. Every other
    truncation in this codebase announces itself.
    """

    LAYOUT = [("NODE", 12)]

    def test_a_cut_value_is_marked(self):
        from slurmpast.render import text_table

        row = text_table(self.LAYOUT, [{"NODE": "midway3-0600,midway3-0611"}])[-1]
        assert row.strip().endswith("…")
        assert row.strip() != "midway3-0600", "a wrong answer that looks right"

    def test_a_value_that_fits_is_untouched(self):
        from slurmpast.render import text_table

        assert text_table(self.LAYOUT, [{"NODE": "midway3-0600"}])[-1].strip() == "midway3-0600"

    def test_the_marker_never_widens_the_cell(self):
        from slurmpast.render import clip

        for width in range(1, 30):
            assert len(clip("midway3-[0600-0607,0611]", width)) <= width


class TestTheNodeTableGoesThroughTheSharedSpec:
    """It was the one plain table still hand-formatted at `"  %-16s %9s %10s %20s"`.
    `render.NODE_COLUMNS` was declared for it -- "so this table drops columns,
    tracks the terminal and spends the leftover exactly as the other two do" -- and
    only the dashboard ever used it. So any node name past 16 characters pushed
    every following column right, on the row the reader came for, and the table read
    byte-identically at 60 columns and at 200.
    """

    LONG = "gpu-compute-node-a100-0001"
    SHORT = "cn2"

    @classmethod
    def _table(cls, style):
        from slurmpast.index import History
        from slurmpast.model import Job, Step
        from slurmpast.report import render_nodes

        jobs = []
        for index, node in enumerate((cls.LONG, cls.SHORT)):
            for run in range(14):
                jid = 100 * index + run
                jobs.append(
                    Job(
                        job_id=str(9000 + jid),
                        name="sweep",
                        state="FAILED" if (node is cls.LONG and run < 10) else "COMPLETED",
                        start="2026-07-%02dT01:00:00" % (run + 1),
                        end="2026-07-%02dT02:00:00" % (run + 1),
                        elapsed=3600.0,
                        timelimit=7200.0,
                        alloc_cpus=8,
                        nnodes=1,
                        alloc_tres="cpu=8,mem=64G,node=1",
                        node_list=node,
                        steps=(Step(step_id="%d.batch" % (9000 + jid), total_cpu=3000.0),),
                    )
                )
        return render_nodes(History(jobs, window="t"), metric="failure", style=style)

    def _rows(self, text):
        """The two node rows, and not the `--exclude=` line that names one of them.

        Matched on a prefix short enough to survive the column being narrowed: on a
        cramped terminal the long name is legitimately clipped to `gpu-compute-…`.
        """
        return [
            line
            for line in text.splitlines()
            if line.startswith("  gpu-compute") or line.startswith("  " + self.SHORT)
        ]

    @pytest.mark.parametrize("columns", ["80", "100", "140"])
    def test_the_verdict_column_starts_in_one_place(self, monkeypatch, columns):
        from slurmpast.report import Style

        monkeypatch.setenv("COLUMNS", columns)
        rows = self._rows(self._table(Style(enabled=False)))
        assert len(rows) == 2, rows
        starts = set()
        for line in rows:
            stripped = line.rstrip()
            for word in ("inconclusive", "better", "worse"):
                if stripped.endswith(word):
                    starts.add(len(stripped) - len(word))
                    break
            else:
                raise AssertionError("no verdict on %r" % line)
        assert len(starts) == 1, "a long name shifted the verdict column: %s" % sorted(starts)

    def test_it_tracks_the_terminal(self, monkeypatch):
        from slurmpast.report import Style

        widths = []
        for columns in ("70", "100", "160"):
            monkeypatch.setenv("COLUMNS", columns)
            widths.append(max(len(line) for line in self._rows(self._table(Style(enabled=False)))))
        assert len(set(widths)) > 1, "identical at every width -- not fitted at all"
        assert widths == sorted(widths)

    @pytest.mark.parametrize("columns", ["60", "70", "80"])
    def test_a_narrow_terminal_drops_a_column_rather_than_overrunning(self, monkeypatch, columns):
        from slurmpast.report import Style

        monkeypatch.setenv("COLUMNS", columns)
        text = self._table(Style(enabled=False))
        for line in self._rows(text):
            assert len(line) <= int(columns), "%d > %s -- %r" % (len(line), columns, line)


class TestTheReadmeAndItsAssetsAgree:
    """The README's lead image was a 404 for the first several releases: it pointed
    at `assets/demo.gif`, and no `.gif` was ever committed. Nothing noticed, because
    nothing checked — a broken image renders as a small grey box that reads like a
    slow network.
    """

    @staticmethod
    def _root():
        import pathlib

        return pathlib.Path(__file__).resolve().parent.parent

    @staticmethod
    def _referenced(root):
        import re

        readme = (root / "README.md").read_text()
        return set(re.findall(r'src="(assets/[^"]+)"', readme))

    def test_every_image_the_readme_points_at_exists(self):
        root = self._root()
        missing = [ref for ref in self._referenced(root) if not (root / ref).is_file()]
        assert not missing, missing

    def test_every_asset_is_pointed_at(self):
        """The other direction. An asset nobody references is one a generator keeps
        rewriting and no reader ever sees -- and it is how three of these came to be
        stale for four rounds without anyone noticing."""
        root = self._root()
        referenced = self._referenced(root)
        images = {
            "assets/%s" % path.name
            for path in (root / "assets").iterdir()
            if path.suffix in (".svg", ".gif", ".png")
        }
        assert images - referenced == set(), sorted(images - referenced)

    def test_the_test_badge_matches_the_suite(self):
        """`tests-1029` sat in the README for two rounds after the count moved."""
        import re

        root = self._root()
        claimed = re.search(r"tests-(\d+)-brightgreen", (root / "README.md").read_text())
        assert claimed, "the badge should still be there"
        collected_n, basis = _committed_collect_count(root)
        if collected_n is None:  # pytest phrasing varies by version; skip rather than lie
            import pytest

            pytest.skip("could not read a collected count from this pytest")
        claimed_n = int(claimed.group(1))
        assert claimed_n == collected_n, (
            f"README says {claimed_n} tests, {basis} collects {collected_n} -- "
            + _badge_mismatch_reason(claimed_n, collected_n, _untracked_test_files(root))
        )


def _untracked_test_files(root):
    """Test files present but not committed, or ``[]`` when git cannot say.

    Read rather than assumed, because it decides which of two opposite messages
    :meth:`test_the_test_badge_matches_the_suite` prints. Returns ``[]`` on any
    git failure (a tarball install, no git binary) so the caller falls back to
    the plain "bump it" wording rather than claiming a cause it cannot support.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "--", "tests/"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    return sorted(ln.strip() for ln in out.stdout.splitlines() if ln.strip().endswith(".py"))


def _collect_count(cwd, src_first=None):
    """``N`` from a ``--collect-only`` run in ``cwd``, or ``None`` if unreadable."""
    import os
    import re
    import subprocess
    import sys

    env = dict(os.environ)
    if src_first is not None:
        # An exported tree is not the installed package: put its own `src` first
        # so the collect imports the code that ships WITH it, not this checkout's.
        prior = env.get("PYTHONPATH")
        env["PYTHONPATH"] = os.pathsep.join([str(src_first), prior] if prior else [str(src_first)])
    try:
        out = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--collect-only", "-p", "no:cacheprovider"],
            cwd=cwd,
            capture_output=True,
            text=True,
            env=env,
            timeout=600,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    found = re.search(r"(\d+) tests collected", out) or re.search(r"(\d+)/(\d+)", out)
    return int(found.group(1)) if found else None


def _committed_collect_count(root):
    """``(count, basis)`` for the suite that SHIPS -- what HEAD collects.

    A live collect is the wrong surface to compare the badge against. The badge
    documents the PUBLISHED package, and a working tree mid-round holds test
    files that are not committed *and* edits adding tests to files that are, so
    the live count describes a suite nobody can install. Comparing against it
    made this test fail on every round that left the tree dirty -- carried in
    ``issues.md`` as open since round fifty-three, with a whole module
    (``test_badge_mismatch_diagnosis.py``) written to explain the failure rather
    than remove it. Measured on this checkout: HEAD collects 1969 with a badge
    reading 1969, the same tree live collects 2526, and dropping only the 27
    untracked files still gives 1985 -- which is why "ignore what is untracked"
    is not the fix either.

    Falls back to the working tree when git cannot answer (a tarball install, no
    git binary). That fallback is why :func:`_badge_mismatch_reason` keeps its
    untracked branch: it is the one remaining path where untracked files explain
    a mismatch.
    """
    import os
    import subprocess
    import tempfile

    def _live():
        return _collect_count(root), "the working tree"

    try:
        archive = subprocess.run(
            ["git", "archive", "HEAD"], cwd=root, capture_output=True, timeout=120
        )
    except (OSError, subprocess.SubprocessError):
        return _live()
    if archive.returncode != 0 or not archive.stdout:
        return _live()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            unpack = subprocess.run(
                ["tar", "-x", "-C", tmp], input=archive.stdout, capture_output=True, timeout=120
            )
        except (OSError, subprocess.SubprocessError):
            return _live()
        if unpack.returncode != 0:
            return _live()
        return _collect_count(tmp, os.path.join(tmp, "src")), "HEAD"


def _badge_mismatch_reason(claimed, collected, untracked):
    """Why the badge and the live collect disagree, as a sentence.

    The count alone cannot tell the two causes apart, and they want opposite
    actions:

    * the badge is stale -- somebody added tests and did not bump it. This is the
      case the docstring below records (``tests-1029`` sat for two rounds), and
      the fix is to bump the badge.
    * the working tree holds test files that are not committed. Then the badge is
      RIGHT for the suite that ships, this failure is expected locally, and CI is
      green -- bumping the badge would RED CI, which is the opposite of the fix.

    Empty string when the counts agree, so the caller can use it unconditionally.
    """
    if claimed == collected:
        return ""
    if untracked and collected > claimed:
        shown = ", ".join(untracked[:3]) + (", ..." if len(untracked) > 3 else "")
        return (
            f"{len(untracked)} test file(s) here are untracked ({shown}), which is "
            f"exactly the difference: the badge states the count of the suite that "
            f"SHIPS, so it is correct for HEAD and this failure is expected locally "
            f"while CI is green. Commit or delete those files to close it -- bumping "
            f"the badge to {collected} would red CI."
        )
    return f"the badge is stale; bump it to {collected}"


class TestEverySentenceWrapsIncludingTheEmptyOnes:
    """Round six. Round five wrapped the prose lines its reproductions reached and
    left the siblings beside them, which is the "fixed only on one side" shape
    `issues.md` has now named three times.

    Three of the five survivors are the lines a view falls back to when it has
    nothing else to show, so the sentence written to rescue an empty screen was the
    longest thing on it -- 132 cells at *every* terminal width, because the first
    interpolates a folded workload name and the second is a fixed 121-character
    literal.

    Standalone rather than a subclass of TestPlainOutputFitsATerminal: that class
    scopes its assertions to table rows on purpose ("a wrapped sentence is what
    sentences do"), which is exactly the exemption these five hid behind. Every
    line counts here.
    """

    LONG_WORKLOAD = "nemotron-batch-h200-tokenize-shards-stage7-retry"

    @classmethod
    def _history(cls, count, nodes, state, cpu):
        """A history with long names, chosen to land on one of the empty branches."""
        from slurmpast.index import History
        from slurmpast.sacct import _FIELDS, parse

        def row(**kw):
            return "|".join(str(kw.get(name, "")) for name in _FIELDS)

        rows = []
        for index in range(count):
            jid = 7000000 + index
            day = index % 28 + 1
            rows.append(
                row(
                    JobID=str(jid),
                    JobName="%s-%d" % (cls.LONG_WORKLOAD, index),
                    State=state,
                    ExitCode="0:0",
                    Start="2026-07-%02dT01:00:00" % day,
                    End="2026-07-%02dT02:00:00" % day,
                    Elapsed="01:00:00",
                    Timelimit="02:00:00",
                    ReqMem="0n",
                    ReqCPUS="8",
                    AllocTRES="cpu=8,mem=64G,node=1",
                    NodeList="gpu-compute-node-a100-%04d" % (index % nodes),
                    Partition="gpu",
                )
            )
            rows.append(
                row(
                    JobID="%d.batch" % jid,
                    State=state.split()[0],
                    Elapsed="01:00:00",
                    TotalCPU=cpu,
                    CPUTime="08:00:00",
                    MaxRSS="2000000K",
                )
            )
        return History(parse("\n".join(rows)))

    @pytest.mark.parametrize("columns", ["66", "80", "100", "120"])
    def test_the_nodes_screen_with_nothing_to_report_still_fits(self, monkeypatch, columns):
        """Both "nothing to say" branches, at four widths.

        Branch A -- no hangs anywhere -- carries the workload name, so it reached
        132 cells at 80, 100 and 120 alike. Branch B is a fixed literal at 122.
        """
        from slurmpast.report import Style, render_nodes

        monkeypatch.setenv("COLUMNS", columns)
        histories = {
            "no hangs at all": self._history(30, 2, "COMPLETED", "00:50:00"),
            "nothing reaches MIN_SAMPLES": self._history(12, 12, "TIMEOUT", "00:00.5"),
        }
        for label, history in histories.items():
            text = render_nodes(history, metric="hang", style=Style(enabled=False))
            for line in text.splitlines():
                assert len(line) <= int(columns), "%s: %d > %s -- %r" % (
                    label,
                    len(line),
                    columns,
                    line,
                )

    @pytest.mark.parametrize("columns", ["66", "80", "100", "120"])
    def test_the_baseline_line_wraps(self, monkeypatch, columns):
        """The third sibling. 67 cells, so it overran below 68 only -- and that 67
        is the number `table_floor`'s docstring recorded as `NODE_COLUMNS`' floor
        for a round, which is 41. Measuring a prose bug and filing it as a property
        of the column spec is how it survived."""
        from slurmpast.demo import history
        from slurmpast.index import History
        from slurmpast.report import Style, render_nodes

        monkeypatch.setenv("COLUMNS", columns)
        text = render_nodes(History(history()), metric="hang", style=Style(enabled=False))
        baseline = [ln for ln in text.splitlines() if "baseline" in ln]
        assert baseline, "the baseline line should still be on the screen"
        for line in text.splitlines():
            assert len(line) <= int(columns), "%d > %s -- %r" % (len(line), columns, line)

    def test_the_documented_node_table_floor_is_the_one_the_spec_gives(self):
        """The control for the docstring correction, and the reason it is a test.

        67 was measured off the rendered view and written down as a property of
        `NODE_COLUMNS`. Asserting the real relationship means the next person to
        add a never-dropped column moves this number and finds out.
        """
        from slurmpast.render import NODE_COLUMNS, table_floor

        assert table_floor(NODE_COLUMNS) == 41
        keep = [c for c in NODE_COLUMNS if not c.drop]
        assert table_floor(NODE_COLUMNS) == 2 + sum(max(c.width, len(c.label)) for c in keep) + (
            len(keep) - 1
        )

    @pytest.mark.parametrize("columns", ["66", "80", "100"])
    def test_the_sizing_screen_wraps_its_headers_and_its_empty_line(self, monkeypatch, columns):
        """A folded workload name plus a partition is unbounded (86 cells at 80),
        and the "nothing to advise" line is 66 -- the only line on that view."""
        from slurmpast.index import History
        from slurmpast.report import Style, render_sizing
        from slurmpast.sacct import _FIELDS, parse

        monkeypatch.setenv("COLUMNS", columns)

        def row(**kw):
            return "|".join(str(kw.get(name, "")) for name in _FIELDS)

        nothing = History(
            parse(
                row(
                    JobID="500001",
                    JobName="a",
                    State="COMPLETED",
                    ExitCode="0:0",
                    Start="2026-07-01T00:00:00",
                    End="2026-07-01T01:00:00",
                    Elapsed="01:00:00",
                    Timelimit="01:00:00",
                    ReqMem="0n",
                    ReqCPUS="1",
                    AllocTRES="cpu=1,mem=1G,node=1",
                    NodeList="n1",
                    Partition="p",
                )
            )
        )
        from slurmpast.demo import history

        wide = History(
            [
                j._replace(
                    name=j.name.replace("cot-exp", self.LONG_WORKLOAD),
                    partition="very-long-partition-name",
                )
                for j in history()
            ]
        )
        for label, hist in (("nothing to advise", nothing), ("long headers", wide)):
            text = render_sizing(hist, style=Style(enabled=False))
            for line in text.splitlines():
                assert len(line) <= int(columns), "%s: %d > %s -- %r" % (
                    label,
                    len(line),
                    columns,
                    line,
                )

    @pytest.mark.parametrize("columns", ["80", "100", "120"])
    def test_only_the_recorded_log_path_may_overrun(self, monkeypatch, columns):
        """The prose around a path wraps; the path itself does not, on purpose.

        `--plain` exists to be pasted, so a path is never shortened -- but the
        58-cell "matched by timing" note rode on the same line (133 cells at every
        width) and the "moved or deleted" variant is a whole sentence built around
        one (122). Both are prose. The demo could not catch either: its jobs record
        no StdOut, no SubmitLine and a 23-character workdir, and this test's own
        class already had a long-valued fixture the job-detail test did not use.
        """
        from slurmpast.report import Style, render_job
        from slurmpast.sacct import _FIELDS, parse

        monkeypatch.setenv("COLUMNS", columns)

        def row(**kw):
            return "|".join(str(kw.get(name, "")) for name in _FIELDS)

        job = parse(
            row(
                JobID="884411",
                JobName="nemotron-batch-h200-tokenize-shards",
                State="COMPLETED",
                ExitCode="0:0",
                Start="2026-07-01T00:00:00",
                End="2026-07-01T02:00:00",
                Elapsed="02:00:00",
                Timelimit="04:00:00",
                ReqMem="0n",
                ReqCPUS="8",
                AllocTRES="cpu=8,mem=64G,node=1",
                NodeList="n1",
                Partition="p",
                WorkDir="/scratch/dana",
                StdOut="/scratch/dana/logs/%x-%j.out",
            )
        )[0]
        long_path = "/scratch/dana/logs/nemotron-batch-h200-tokenize-shards-884411.out"
        cases = {
            "found, matched by timing": {"log_path": long_path, "log_inferred": True},
            "not found, path recorded": {"log_path": None},
        }
        for label, kwargs in cases.items():
            text, _ = render_job(job, style=Style(enabled=False), **kwargs)
            for line in text.splitlines():
                if long_path in line:
                    continue  # the accepted overrun: a path has to stay copyable
                assert len(line) <= int(columns), "%s: %d > %s -- %r" % (
                    label,
                    len(line),
                    columns,
                    line,
                )

    def test_the_path_itself_is_still_printed_whole(self):
        """The control for the exemption above: wrapping must not have shortened
        the one value the plain renderer promises to keep intact."""
        from slurmpast.demo import history
        from slurmpast.report import Style, render_job

        long_path = "/scratch/dana/logs/a-very-long-name-indeed-for-one-job-884411.out"
        text, _ = render_job(history()[0], log_path=long_path, style=Style(enabled=False))
        assert long_path in text
        assert "…" not in text.split("log")[-1].splitlines()[0]


class TestASharedSentenceKeepsWhatIsSurfaceSpecific:
    """`render` exists so the two front ends cannot drift — but pooling a sentence
    can also average away the one part of it that is *supposed* to differ.

    `nodes_empty_reason` did: the plain report told the reader "A wider --since
    window is what fixes this" and the dashboard told them "(w)", and sharing the
    sentence collapsed both into a bare "A wider window is what fixes this." That
    is the only actionable clause in it, and this codebase's whole line on advice
    is to name the thing the reader actually types — `format_duration`'s
    `HH:MM:SS`, `format_mem_flag`'s `52G`, the paste-ready `#SBATCH --exclude=`.

    So the wording is shared and the keystroke is passed in. Nothing caught the
    loss when it happened: the suite stayed green at 1,190.
    """

    @staticmethod
    def _no_rows_table():
        """A table that reaches the "nothing reached MIN_SAMPLES" branch."""
        return {"hits": 3, "rows": [], "skipped_nodes": 12, "baseline": 0.25, "trials": 12}

    def test_the_plain_report_names_the_flag(self):
        from slurmpast.render import nodes_empty_reason

        assert "--since" in nodes_empty_reason(self._no_rows_table(), "hang", None)

    def test_the_dashboard_names_the_key(self):
        from slurmpast.render import nodes_empty_reason

        text = nodes_empty_reason(self._no_rows_table(), "hang", None, widen="w")
        assert "(w)" in text
        assert "--since" not in text

    def test_neither_surface_is_left_with_a_bare_sentence(self):
        """The regression itself: an empty-window message with no way out of it."""
        from slurmpast.render import nodes_empty_reason

        for widen in ("--since", "w"):
            text = nodes_empty_reason(self._no_rows_table(), "hang", None, widen=widen)
            assert "A wider window ()" not in text
            assert "A wider window is what fixes this" not in text, text

    def test_the_wording_around_it_is_still_shared(self):
        """The control: the point of pooling the sentence was that `report` said
        "below threshold" while `tui` said "below sample threshold". Everything but
        the keystroke has to stay identical."""
        from slurmpast.render import nodes_empty_reason

        plain = nodes_empty_reason(self._no_rows_table(), "hang", None, widen="--since")
        dash = nodes_empty_reason(self._no_rows_table(), "hang", None, widen="w")
        assert plain.replace("(--since)", "<>") == dash.replace("(w)", "<>")

    def test_both_front_ends_actually_pass_their_own(self):
        """Reading the rendered views, not just the helper: a parameter with a
        default is only as good as the caller that overrides it."""
        import inspect

        from slurmpast import report, tui

        assert 'widen="w"' in inspect.getsource(tui.NodesScreen)
        # report relies on the default, so pin that the default is the flag.
        assert "--since" in report.nodes_empty_reason(self._no_rows_table(), "hang", None)


class TestFitColumnsHoldsItsContractOnAnySpec:
    """`fit_columns` is the one engine every table on every surface goes through,
    and its behaviour was pinned only by the four specs this codebase happens to
    declare. Its docstring makes six promises; this asserts all six over 40,000
    generated specs at generated widths, paddings and content caps.

    Nothing was found. That is the point of writing it down: the layout arithmetic
    is now covered by a property rather than by examples, so a change to the drop
    order or the fill spread has to break a rule rather than an instance.

    The generator is checked for vacuity in `test_the_generator_exercises_every_branch`
    below -- a green fuzz whose assertions never ran is worth nothing, and 4,377 of
    the trials here are the floor case where the table legitimately cannot fit.
    """

    LABELS = (
        "#",
        "JOBID",
        "NAME",
        "STATE",
        "STARTED",
        "ENDED",
        "WALL TIME",
        "CPU TIME",
        "CPUS BUSY",
        "PEAK MEM",
        "MEM%",
        "GPU",
        "NODE",
        "95% CI",
        "VERDICT",
        "RATE",
        "N",
    )

    @classmethod
    def _cases(cls, count, seed=31):
        """(spec, available, padding, content, fill_to) tuples."""
        import random

        from slurmpast.render import Column

        rng = random.Random(seed)
        for _ in range(count):
            size = rng.randint(1, 8)
            labels = rng.sample(cls.LABELS, size)
            drops = list(range(1, size + 1))
            rng.shuffle(drops)
            spec = [
                Column(
                    label,
                    rng.randint(1, 20),
                    flex=rng.random() < 0.35,
                    drop=drops[index] if rng.random() < 0.6 else 0,
                    grow_to=rng.choice([0, 0, rng.randint(1, 40)]),
                    align=rng.choice(["left", "right"]),
                )
                for index, label in enumerate(labels)
            ]
            available = rng.randint(1, 220)
            fill_to = rng.choice([0, 0, available, rng.randint(1, 220)])
            content = (
                {c.label: rng.randint(0, 40) for c in spec if rng.random() < 0.7}
                if rng.random() < 0.5
                else None
            )
            yield spec, available, rng.choice([0, 1, 2, 3]), content, fill_to

    def test_the_contract(self):
        from slurmpast.render import fit_columns

        for spec, available, padding, content, fill_to in self._cases(40000):
            got = fit_columns(spec, available, padding=padding, content=content, fill_to=fill_to)
            labels = [label for label, _ in got]
            kept = set(labels)
            by_label = {c.label: c for c in spec}
            width = dict(got)

            # "A column is never narrower than its own header."
            for label, cells in got:
                assert cells >= len(label), (label, cells)

            # "Returns (label, width) in display order" -- a subsequence of the spec.
            assert labels == [c.label for c in spec if c.label in kept]

            # "drop=0 means never dropped", and the lowest number goes first.
            dropped = [c for c in spec if c.label not in kept]
            if len(spec) > 1:
                assert all(c.drop for c in dropped), [c.label for c in dropped if not c.drop]
            for gone in dropped:
                for held in (c for c in spec if c.label in kept and c.drop):
                    assert gone.drop <= held.drop, (gone.label, held.label)

            # It fits, unless every remaining column is undroppable -- the
            # `table_floor` case, which is a property of the spec.
            total = sum(width.values()) + padding * len(got)
            undroppable = [c for c in spec if not c.drop]
            floor = sum(max(c.width, len(c.label)) for c in undroppable) + padding * max(
                1, len(undroppable)
            )
            if len(got) > 1:
                assert total <= available or total <= floor, (total, available, floor)

            # "fill_to is the total width to spread whatever is still spare across"
            # -- landed on exactly, unless the table was already wider than it.
            if fill_to and available >= fill_to:
                assert total == fill_to or total > fill_to, (total, fill_to)

            # "zero leaves it unused": with no fill_to, a fixed column never grows.
            if not fill_to:
                for label, cells in got:
                    column = by_label[label]
                    if not column.flex:
                        assert cells == max(column.width, len(label)), (label, cells)

    def test_the_generator_exercises_every_branch(self):
        """Vacuity check. Each of these was zero in an earlier draft of the
        generator, which made the corresponding assertion above decorative."""
        from slurmpast.render import fit_columns

        seen = dict.fromkeys(
            ["dropped", "flex grew", "fill reachable", "landed exactly", "floor overrun"], 0
        )
        for spec, available, padding, content, fill_to in self._cases(40000):
            got = fit_columns(spec, available, padding=padding, content=content, fill_to=fill_to)
            width = dict(got)
            total = sum(width.values()) + padding * len(got)
            if len(got) < len(spec):
                seen["dropped"] += 1
            if any(c.flex and width.get(c.label, 0) > max(c.width, len(c.label)) for c in spec):
                seen["flex grew"] += 1
            if fill_to and available >= fill_to:
                seen["fill reachable"] += 1
                if total == fill_to:
                    seen["landed exactly"] += 1
            if total > available:
                seen["floor overrun"] += 1
        for branch, count in seen.items():
            assert count > 100, (branch, count, seen)


def _widths(columns):
    return {c.label: c.width for c in columns}


class TestTheRowNumberColumnFitsTheRowsItNumbers:
    """A "#" fixed at 3 numbered row 1000 as "100", and 1001 as "100" as well.

    Reported from the flat job list: rows 991 to 999 counted up correctly and
    then the column started over, so ten consecutive rows carried the same
    number before it ticked to "101". It is not decoration -- `tui._RowJump`
    lets a reader type a row number to jump to it -- so a row that reads 100 and
    answers to 1004 is a trap, and a clipped identifier that still looks like an
    identifier is worse than a wider table or no column at all.
    """

    def test_a_short_list_is_left_as_it_was(self):
        """CONTROL — `--plain` shows 25 rows by default and 3 is right for it."""
        from slurmpast.render import JOB_COLUMNS, ROW_NUMBER_FLOOR, numbered_for

        assert _widths(numbered_for(JOB_COLUMNS, 25))["#"] == ROW_NUMBER_FLOOR

    @pytest.mark.parametrize("rows,want", [(999, 3), (1000, 4), (9999, 4), (29617, 5)])
    def test_it_widens_to_the_longest_number_it_will_draw(self, rows, want):
        from slurmpast.render import JOB_COLUMNS, numbered_for

        assert _widths(numbered_for(JOB_COLUMNS, rows))["#"] == want

    def test_nothing_else_moves(self):
        from slurmpast.render import JOB_COLUMNS, numbered_for

        widened = numbered_for(JOB_COLUMNS, 29617)
        assert [c.label for c in widened] == [c.label for c in JOB_COLUMNS]
        for before, after in zip(JOB_COLUMNS, widened, strict=True):
            if before.label != "#":
                assert before == after

    def test_an_empty_list_still_has_a_column(self):
        from slurmpast.render import JOB_COLUMNS, ROW_NUMBER_FLOOR, numbered_for

        assert _widths(numbered_for(JOB_COLUMNS, 0))["#"] == ROW_NUMBER_FLOOR

    def test_the_overview_gets_it_too(self):
        """`--all-users` on a busy cluster reaches four figures of workloads."""
        from slurmpast.render import OVERVIEW_COLUMNS, numbered_for

        assert _widths(numbered_for(OVERVIEW_COLUMNS, 12000))["#"] == 5

    def test_a_wide_terminal_shows_the_wider_column(self):
        from slurmpast.render import JOB_COLUMNS, fit_columns, numbered_for

        layout = dict(fit_columns(numbered_for(JOB_COLUMNS, 29617), 140))
        assert layout["#"] == 5

    def test_a_narrow_terminal_drops_the_column_rather_than_a_digit(self):
        """The note this replaced chose the other way: it held "#" at 3 so the
        never-dropped columns would fit 80 cells, and paid for it with a number
        that was wrong. `#` goes LAST in the drop order now -- so on a terminal
        that cannot hold a truthful row number there is no row number, and the
        table still fits."""
        from slurmpast.render import JOB_COLUMNS, fit_columns, numbered_for

        layout = dict(fit_columns(numbered_for(JOB_COLUMNS, 29617), 80))
        assert "#" not in layout
        assert sum(layout.values()) + 2 * len(layout) <= 80

    def test_and_keeps_it_at_eighty_cells_when_it_costs_nothing_extra(self):
        """CONTROL, and the reason the drop is on the WIDENING and not the column.

        At the floor "#" costs no more than it always did, so making it droppable
        there would take the row number away from every 80-column terminal to
        solve a problem those readers do not have."""
        from slurmpast.render import JOB_COLUMNS, fit_columns, numbered_for

        assert dict(fit_columns(numbered_for(JOB_COLUMNS, 25), 80))["#"] == 3
        assert dict(fit_columns(numbered_for(JOB_COLUMNS, 999), 78))["#"] == 3

    def test_every_number_the_plain_job_table_prints_is_its_own(self):
        """End to end, on the surface the report was made from."""
        from slurmpast import report

        jobs = [_numbered_job(i) for i in range(1, 1006)]
        text = report.render_list(jobs, limit=len(jobs), style=report.Style(enabled=False))
        seen = [
            line.split()[0]
            for line in text.splitlines()
            if line[:6].strip().isdigit() and len(line.split()) > 2
        ]
        assert len(seen) == len(jobs), (len(seen), len(jobs))
        assert seen == [str(n) for n in range(1, len(jobs) + 1)]


def _numbered_job(index):
    from slurmpast.model import Job

    return Job(
        job_id="%d" % (900000 + index),
        name="w",
        user="u",
        partition="test",
        state="COMPLETED",
        submit="2026-01-01T00:00:00",
        start="2026-01-01T00:00:00",
        end="2026-01-01T00:10:00",
        elapsed=600.0,
        node_list="midway3-0001",
    )
