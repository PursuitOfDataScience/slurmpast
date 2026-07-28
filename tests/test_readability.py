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

    def test_plain_report_explains_the_number(self):
        from slurmpast.report import Style, render_overview

        text = render_overview(History(history()), style=Style(enabled=False))
        assert "GPU-hours" in text
        assert "held continuously" in text
        assert "GPU-h (" not in text  # the old abbreviated form

    def test_goodput_jargon_is_gone(self):
        from slurmpast.report import Style, render_overview

        text = render_overview(History(history()), style=Style(enabled=False))
        assert "goodput" not in text
        assert "in jobs that completed" in text

    @pytest.mark.asyncio
    async def test_dashboard_summary_says_it_in_words(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            body = app.screen.query_one("#summary")
            text = body.renderable.plain if hasattr(body.renderable, "plain") else ""
            assert "goodput" not in text
            assert "GPU-hours" in text
            assert "never computed" in text
