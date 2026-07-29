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
        return {
            "overview": render_overview(h, style=style),
            "list": render_list(list(h.jobs), style=style),
            "patterns": render_patterns(h, style=style),
            "nodes": render_nodes(h, style=style),
            "sizing": render_sizing(h, style=style),
        }

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

    @pytest.mark.parametrize("columns", ["80", "100", "120"])
    def test_no_table_row_overruns_the_terminal(self, monkeypatch, columns):
        from slurmpast.report import Style

        monkeypatch.setenv("COLUMNS", columns)
        views = self._views(Style(enabled=False))
        for name in ("overview", "list"):
            for line in self._table_lines(views[name]):
                assert len(line) <= int(columns), "%s: %d > %s -- %r" % (
                    name,
                    len(line),
                    columns,
                    line,
                )

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
