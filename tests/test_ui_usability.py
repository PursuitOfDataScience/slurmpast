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


class TestWindowIsVisible:
    """Reported as "why is this job not tracked? many jobs share this name".

    It was not a extraction bug: 19 amd_reserve jobs exist, 2 fall in the default
    now-7days window, and one of those is RUNNING with End=Unknown so it is
    correctly excluded from aggregates. The defect was that the UI never showed
    the window, so a correct 1-job workload looked like data loss.
    """

    @pytest.mark.asyncio
    async def test_overview_subtitle_names_the_window(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert "test" in app.screen.sub_title  # the window string we passed

    @pytest.mark.asyncio
    async def test_subtitle_is_never_just_a_filter_label(self):
        """The header used to read "slurmpast — everything", which says nothing."""
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.screen.sub_title != "everything"
            await pilot.press("a")
            await pilot.pause()
            assert app.screen.sub_title != "everything"

    @pytest.mark.asyncio
    async def test_filter_named_only_when_filtering(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert "everything" not in app.screen.sub_title
            await pilot.press("f")          # -> "problem"
            await pilot.pause()
            assert "failed, timed out, or idle" in app.screen.sub_title

    @pytest.mark.asyncio
    async def test_job_list_subtitle_carries_the_window(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            assert "test" in app.screen.sub_title
            assert "jobs" in app.screen.sub_title


class TestSingularPlural:
    @pytest.mark.asyncio
    async def test_one_job_is_not_reported_as_one_jobs(self):
        from slurmpast.demo import history as demo

        single = [j for j in demo() if j.name == "soup-merge"]
        assert len(single) == 1
        app = make_app(single, no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            assert "1 job" in app.screen.sub_title
            assert "1 jobs" not in app.screen.sub_title

    @pytest.mark.asyncio
    async def test_one_workload_is_not_one_workloads(self):
        from slurmpast.demo import history as demo

        single = [j for j in demo() if j.name == "soup-merge"]
        app = make_app(single, no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert "1 workload" in app.screen.sub_title
            assert "1 workloads" not in app.screen.sub_title


class TestExcludedRecordsAreNamed:
    """A record dropped as unterminated must not just vanish from its workload."""

    def _with_a_running_job(self):
        from slurmpast.demo import history as demo

        jobs = [j for j in demo() if j.name == "soup-merge"]
        live = jobs[0]._replace(job_id="9999999", end=None, state="RUNNING", open_ended=True)
        return jobs + [live]

    def test_group_counts_what_it_lost(self):
        from slurmpast.index import build_groups

        group = [g for g in build_groups(self._with_a_running_job())
                 if g.name == "soup-merge"][0]
        assert group.total == 1
        assert group.excluded == 1

    def test_group_with_nothing_excluded_reports_zero(self):
        from slurmpast.demo import history as demo
        from slurmpast.index import build_groups

        group = [g for g in build_groups(demo()) if g.name == "midtrain"][0]
        assert group.excluded == 0

    @pytest.mark.asyncio
    async def test_workload_screen_says_so(self):
        app = make_app(self._with_a_running_job(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            body = app.screen.query_one("#summary").renderable
            text = body.plain if hasattr(body, "plain") else str(body)
            assert "excluded as unterminated" in text

    def test_plain_overview_shows_the_window(self):
        from slurmpast.demo import history as demo
        from slurmpast.index import History
        from slurmpast.report import Style, render_overview

        h = History(demo(), window="now-30days → now")
        text = render_overview(h, style=Style(enabled=False))
        assert "window now-30days → now" in text
