"""Wording the UI got wrong, reported from real use.

Three separate complaints, all the same failure: printing a number or a glyph
that the reader has no way to interpret.

* "⭘" appeared top-left on every screen. It is Textual's command-palette button,
  which cannot even be clicked here because mouse capture is off.
* "BURNED" was a column name I invented for resource-time consumed.
* "778 GPU-h (96.7% goodput)" used two pieces of insider shorthand and gave no
  reference frame -- a GPU-hour total means nothing without the period it covers.
"""

import pytest

pytest.importorskip("textual")

from slurmpast import tui  # noqa: E402
from slurmpast.demo import history  # noqa: E402
from slurmpast.index import History, sort_label  # noqa: E402


def make_app(jobs, **kw):
    return tui.SlurmpastApp(lambda: list(jobs), window="test", **kw)


class TestNoMysteryGlyph:
    def test_header_icon_is_blank(self):
        header = tui._header()
        assert getattr(header, "icon", "") == ""

    @pytest.mark.asyncio
    async def test_the_circle_is_gone_from_the_header(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import Header

            for header in app.screen.query(Header):
                assert getattr(header, "icon", "") == ""


class TestColumnNames:
    @pytest.mark.asyncio
    async def test_no_invented_jargon_in_the_overview_columns(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import DataTable

            labels = [str(c.label) for c in app.screen.query_one(DataTable).columns.values()]
            assert "BURNED" not in labels
            assert "USED" in labels

    def test_sort_label_is_plain(self):
        assert sort_label("cost") == "resource use"

    def test_plain_report_names_the_unit_in_the_title(self):
        from slurmpast.report import Style, render_overview

        text = render_overview(History(history()), style=Style(enabled=False))
        assert "GPU-hours, else core-hours" in text
        assert "BURNED" not in text


class TestGpuHoursAreInterpretable:
    """A GPU-hour total is meaningless alone; concurrency is what makes it land."""

    def test_span_derived_from_the_records(self):
        h = History(history())
        assert h.span_hours is not None
        assert h.span_hours > 0

    def test_concurrency_is_hours_over_span(self):
        h = History(history())
        assert h.gpu_concurrency == pytest.approx(
            h.stats["gpu_hours_total"] / h.span_hours, rel=1e-6
        )

    def test_no_span_no_concurrency(self):
        """Rather than divide by a guess, report nothing."""
        jobs = [j._replace(start=None, end=None) for j in history()]
        h = History(jobs)
        assert h.span_hours is None
        assert h.gpu_concurrency is None

    def test_unparseable_timestamps_do_not_crash(self):
        jobs = [j._replace(start="not-a-date", end="also-not") for j in history()]
        assert History(jobs).span_hours is None

    def test_no_gpus_means_no_concurrency(self):
        cpu_only = [
            j._replace(alloc_tres="billing=8,cpu=8,mem=64G,node=1", req_tres="") for j in history()
        ]
        assert History(cpu_only).gpu_concurrency is None

    def test_total_appears_only_as_the_denominator_for_the_idle_figure(self):
        """The total is not a standalone fact worth a line; it makes "17 of 778"
        legible, and that ratio is the number worth acting on."""
        from slurmpast.report import Style, render_overview

        text = render_overview(History(history()), style=Style(enabled=False))
        assert "GPU-hours never computed" in text
        assert "GPU-h (" not in text  # the old abbreviated form

    def test_no_jargon_survives(self):
        from slurmpast.report import Style, render_overview

        text = render_overview(History(history()), style=Style(enabled=False))
        for word in ("goodput", "BURNED", "GPU-h ("):
            assert word not in text

    def test_the_summary_is_brief(self):
        """It was four lines of derivable detail. Everything above the table
        should fit in a couple of lines."""
        from slurmpast.report import Style, render_overview

        text = render_overview(History(history()), style=Style(enabled=False))
        head = text.split("#    WORKLOAD")[0].strip().splitlines()
        body = [ln for ln in head if ln.strip() and not set(ln.strip()) <= {"-"}]
        assert len(body) <= 4, body

    def test_concurrency_still_available_to_callers(self):
        """Trimmed from the display, not deleted -- it is in the JSON payload."""
        h = History(history())
        assert h.gpu_concurrency is not None

    @pytest.mark.asyncio
    async def test_dashboard_summary_says_it_in_words(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            text = app.screen.summary_text.plain
            assert "goodput" not in text
            assert "GPU-hours" in text
            assert "never computed" in text


class TestNoWidgetInternalsInTests:
    """Guard against a mistake made twice already.

    A Static widget's rendered-content attribute exists in textual 0.89 and not
    in 8.x, so a test that reads it passes locally and fails in CI. That was
    fixed once, then reintroduced in a new file two commits later -- exactly the
    kind of regression a rule catches and vigilance does not. Assert on data the
    code composed (``summary_text``, ``extra_summary()``, ``clipboard_view()``)
    instead.
    """

    def test_no_test_reads_a_widget_renderable(self):
        import pathlib

        # Assembled so this file does not trip its own check.
        needle = "." + "render" + "able"
        offenders = []
        for path in sorted(pathlib.Path(__file__).parent.glob("test_*.py")):
            for number, line in enumerate(path.read_text().splitlines(), start=1):
                stripped = line.strip()
                if needle in stripped and not stripped.startswith("#"):
                    offenders.append("%s:%d" % (path.name, number))
        assert not offenders, (
            "these tests read widget internals, which differ across Textual "
            "versions: %s" % ", ".join(offenders)
        )


class TestWindowInEnglish:
    """The title bar read "now-7days → now" -- the tool's own arguments showing
    through. A reader should not have to parse a sacct time spec back out of it."""

    @pytest.mark.parametrize(
        "since,expected",
        [
            ("now-7days", "last 7 days"),
            ("now-30days", "last 30 days"),
            ("now-1day", "last 24 hours"),
            ("now-1week", "last week"),
            ("now-6months", "last 6 months"),
            ("2026-01-01", "since 2026-01-01"),
        ],
    )
    def test_relative_and_absolute(self, since, expected):
        from slurmpast.duration import humanize_window

        assert humanize_window(since) == expected

    def test_closed_range(self):
        from slurmpast.duration import humanize_window

        assert humanize_window("2026-01-01", "2026-07-15") == "2026-01-01 to 2026-07-15"

    def test_no_arrow_glyph_leaks_through(self):
        from slurmpast.duration import humanize_window

        for spec in ("now-7days", "2026-01-01", "now-1day"):
            assert "→" not in humanize_window(spec)
            assert "now-" not in humanize_window(spec)

    def test_timestamps_are_trimmed_to_the_date(self):
        from slurmpast.duration import humanize_window

        assert humanize_window("2026-01-01T08:00:00") == "since 2026-01-01"


class TestColumnNamesAreUnambiguous:
    @pytest.mark.asyncio
    async def test_cpu_columns_say_which_is_which(self):
        """A bare "UTIL" beside a "CPU" column does not say whether it is CPU or
        GPU utilization -- and GPU utilization is not even recorded here."""
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            from textual.widgets import DataTable

            labels = [str(c.label) for c in app.screen.query_one(DataTable).columns.values()]
            assert "UTIL" not in labels
            assert "CPU TIME" in labels
            assert "CPU%" in labels

    @pytest.mark.asyncio
    async def test_overview_fits_a_narrow_terminal(self):
        """It required sideways scrolling; the ribbon and a redundant column went."""
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(84, 20)) as pilot:
            await pilot.pause()
            from textual.widgets import DataTable

            columns = list(app.screen.query_one(DataTable).columns.values())
            assert "OUTCOMES" not in [str(c.label) for c in columns]
            assert "NEVER RAN" not in [str(c.label) for c in columns]
            assert sum(c.width for c in columns) <= 80


class TestCursorDoesNotRepaintCells:
    @pytest.mark.asyncio
    async def test_renderable_keeps_priority_over_the_cursor(self):
        """With the CSS default the cursor's foreground wins and every coloured
        glyph in the highlighted row turns solid white."""
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import DataTable

            table = app.screen.query_one(DataTable)
            assert table.cursor_foreground_priority == "renderable"


class TestResourceRowsMatchSlurmwatch:
    def test_rows_use_the_marker_label_bar_idiom(self):
        from slurmpast.render import resource_rows

        job = [j for j in history() if j.name == "midtrain"][0]
        rows = [r.plain for r in resource_rows(job)]
        assert any(r.lstrip().startswith("●") for r in rows)
        labels = " ".join(rows)
        for expected in ("TIME", "CPU", "MEM"):
            assert expected in labels

    def test_unmeasurable_rows_show_na_and_an_empty_track(self):
        from slurmpast.render import resource_rows

        job = [j for j in history() if j.gpu_count][0]
        gpu_row = [r.plain for r in resource_rows(job) if "GPU" in r.plain][0]
        assert "n/a" in gpu_row
        assert "░" in gpu_row

    def test_ascii_mode_avoids_block_glyphs(self):
        from slurmpast.render import resource_rows

        job = [j for j in history() if j.name == "midtrain"][0]
        rows = " ".join(r.plain for r in resource_rows(job, ascii_mode=True))
        assert "●" not in rows
        assert "█" not in rows
