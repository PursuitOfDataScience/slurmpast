"""Two usability defects reported from real use, and their fixes.

1. Dragging to select did nothing. Textual 0.89 hands the terminal's mouse to
   the app and has no in-app selection API (that arrived in 1.x), so there was
   no way to get text out of the dashboard at all.
2. A workload with hundreds of identically-named runs showed no timestamps, so
   there was no way to tell which attempt a row was.
"""

import pytest

pytest.importorskip("textual")

from slurmpast import render, tui  # noqa: E402
from slurmpast.demo import history  # noqa: E402


def make_app(jobs, **kw):
    return tui.SlurmpastApp(lambda: list(jobs), window="test", **kw)


class TestStampShort:
    def test_compact_form(self):
        assert render.stamp_short("2026-06-27T08:12:50") == "06-27 08:12"

    def test_time_only(self):
        assert render.stamp_short("2026-06-27T08:12:50", with_date=False) == "08:12"

    def test_missing_is_empty_not_a_fake_date(self):
        """An absent timestamp must never render as something that looks real."""
        assert render.stamp_short(None) == ""
        assert render.stamp_short("") == ""

    def test_non_iso_is_passed_through_truncated(self):
        assert render.stamp_short("Unknown") == "Unknown"


class TestTimestampsInJobList:
    @pytest.mark.asyncio
    async def test_job_table_has_started_and_ended_columns(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")          # flat job list
            await pilot.pause()
            from textual.widgets import DataTable

            labels = [str(c.label) for c in app.screen.query_one(DataTable).columns.values()]
            assert "STARTED" in labels
            assert "ENDED" in labels

    @pytest.mark.asyncio
    async def test_rows_actually_carry_a_timestamp(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            text = app.screen.clipboard_view()
            header, first = text.splitlines()[0], text.splitlines()[1]
            assert "STARTED" in header and "ENDED" in header
            assert "2026-07" in first

    def test_plain_renderer_shows_them_too(self):
        """The dashboard and the text output must not disagree.

        The table uses the compact ``MM-DD HH:MM`` form, not full ISO -- the
        clipboard payload carries the full timestamps instead.
        """
        import re

        from slurmpast.report import Style, render_list

        text = render_list(history()[:5], style=Style(enabled=False))
        assert "STARTED" in text and "ENDED" in text
        assert re.search(r"\d\d-\d\d \d\d:\d\d", text)


class TestClipboard:
    @pytest.mark.asyncio
    async def test_copy_row_on_overview(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            text = app.screen.clipboard_row()
            assert "\t" in text
            assert text.split("\t")[0]

    @pytest.mark.asyncio
    async def test_copy_view_on_overview_is_the_plain_report(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            text = app.screen.clipboard_view()
            assert "workloads" in text
            assert "\033[" not in text  # never ship escape codes to a clipboard

    @pytest.mark.asyncio
    async def test_job_screen_copies_the_whole_postmortem(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, tui.JobScreen)
            text = app.screen.clipboard_row()
            for section in ("timing", "cpu", "memory", "outcome"):
                assert section in text
            assert "\033[" not in text

    @pytest.mark.asyncio
    async def test_patterns_and_nodes_are_copyable(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            assert app.screen.clipboard_row()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            assert "baseline" in app.screen.clipboard_row()

    @pytest.mark.asyncio
    async def test_y_writes_the_fallback_file(self, tmp_path, monkeypatch):
        """OSC 52 fails silently on some terminals and inside a misconfigured
        tmux, so the copy must always land somewhere checkable."""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
        clip = tmp_path / "slurmpast" / "clip.txt"
        assert clip.is_file()
        assert clip.read_text().strip()

    @pytest.mark.asyncio
    async def test_copy_is_offered_in_the_footer(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            keys = {b.key for b in app.screen.BINDINGS}
            assert "y" in keys and "Y" in keys

    def test_clip_path_is_under_the_cache_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        assert tui._clip_path() == str(tmp_path / "slurmpast" / "clip.txt")


class TestMouseCapture:
    """Why text was unselectable, and the fix.

    A TUI that enables mouse tracking takes drag events for itself, so the
    terminal stops doing its own selection. Textual 0.89 has no in-app selection
    API to replace it, so the only way to make text selectable is to not capture
    the mouse. These are the four sequences that matter.
    """

    TRACKING = ("1000h", "1003h", "1015h", "1006h")

    def _written(self, mouse):
        from textual.drivers.linux_driver import LinuxDriver

        driver = LinuxDriver.__new__(LinuxDriver)
        written = []
        driver.write = written.append
        driver.flush = lambda: None
        driver._mouse = mouse
        driver._enable_mouse_support()
        return "".join(written)

    def test_capture_off_writes_no_tracking_sequences(self):
        out = self._written(False)
        assert not [t for t in self.TRACKING if t in out]

    def test_capture_on_writes_them_all(self):
        """Guards the test above: if this stops holding, the check above is vacuous."""
        out = self._written(True)
        assert all(t in out for t in self.TRACKING)

    def test_default_is_capture_off_so_selection_works(self):
        from slurmpast.cli import build_parser

        assert build_parser().parse_args([]).mouse is False

    def test_mouse_flag_opts_back_in(self):
        from slurmpast.cli import build_parser

        assert build_parser().parse_args(["--mouse"]).mouse is True

    @pytest.mark.asyncio
    async def test_app_records_the_setting(self):
        app = make_app(history(), no_logs=True, mouse=False)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.mouse_enabled is False

    @pytest.mark.asyncio
    async def test_toggle_is_bound_and_does_not_crash(self):
        """The toggle reaches into driver internals, so it must degrade, not raise."""
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert "M" in {b.key for b in app.BINDINGS}
            await pilot.press("M")
            await pilot.pause()
            assert isinstance(app.mouse_enabled, bool)

    def test_run_threads_the_setting_through(self, monkeypatch):
        seen = {}

        class FakeApp:
            def __init__(self, *a, **kw):
                seen["ctor"] = kw.get("mouse")
                self.load_error = None

            def run(self, **kw):
                seen["run"] = kw.get("mouse")

        monkeypatch.setattr(tui, "SlurmpastApp", FakeApp)
        tui.run(lambda: [], window="w", mouse=False)
        assert seen == {"ctor": False, "run": False}
