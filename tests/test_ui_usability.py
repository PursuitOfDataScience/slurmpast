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


class TestResizeRelayout:
    """Columns are fitted to the terminal, so the table has to be rebuilt when
    the terminal changes -- without losing the reader's place."""

    @pytest.mark.asyncio
    async def test_columns_follow_the_terminal_width(self):
        from textual.widgets import DataTable

        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(84, 24)) as pilot:
            await pilot.pause()
            table = app.screen.query_one(DataTable)
            narrow = sum(c.width for c in table.columns.values())
            await pilot.resize_terminal(150, 24)
            await pilot.pause()
            table = app.screen.query_one(DataTable)
            wide = sum(c.width for c in table.columns.values())
            assert wide > narrow

    @pytest.mark.asyncio
    async def test_the_table_fits_its_content_without_a_canyon(self):
        """Two reported defects, and the fix for the first caused the second:
        a hard stop at 94 columns leaving a wide terminal blank, then a JOB NAME
        column stretched to 44 cells around 18-character names.

        The contract has since changed once more: leaving the leftover unused read
        as thin, so the dashboard now spends it -- but round-robin across every
        column, so no single one can hog it the way JOB NAME did. The plain
        renderer still leaves it unused, because a pasted table wants to be narrow.
        See TestSpendingTheLeftoverWhenAskedTo for the spread itself.
        """
        from textual.widgets import DataTable

        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(140, 24)) as pilot:
            await pilot.pause()
            table = app.screen.query_one(DataTable)
            used = sum(c.width for c in table.columns.values()) + 2 * len(table.columns)
            assert used <= table.size.width, (used, table.size.width)
            # And now uses it, rather than stopping short and centring the gap.
            # Two cells short of the full width on purpose: a vertical scrollbar
            # claims them once the rows overflow, and filling them would push the
            # table into a HORIZONTAL scrollbar instead.
            from slurmpast.tui import _SCROLLBAR

            assert used >= table.size.width - _SCROLLBAR, (used, table.size.width)

            longest = max(len(g.label) for g in app.history.groups)
            columns = {str(c.label): c.width for c in table.columns.values()}
            assert columns["JOB NAME"] >= longest, "names would be truncated"
            # No hogging: an even share of the leftover, not all of it. The reported
            # defect was 44 cells around 18-character names.
            share = (table.size.width - used) // max(1, len(columns)) + 1
            assert columns["JOB NAME"] <= max(longest, 22) + share + (used // len(columns)), (
                columns["JOB NAME"]
            )
            assert columns["JOB NAME"] < used // 3, "one column must not dominate"

    @pytest.mark.asyncio
    async def test_a_long_name_still_gets_the_room_it_needs(self):
        """Content-aware sizing must not become a new truncation bug."""
        from textual.widgets import DataTable

        jobs = [j._replace(name="a-really-quite-long-workload-name-here") for j in history()]
        app = make_app(jobs, no_logs=True)
        async with app.run_test(size=(140, 24)) as pilot:
            await pilot.pause()
            table = app.screen.query_one(DataTable)
            columns = {str(c.label): c.width for c in table.columns.values()}
            assert columns["JOB NAME"] >= len("a-really-quite-long-workload-name-here")

    @pytest.mark.asyncio
    async def test_the_selected_row_survives_a_resize(self):
        from textual.widgets import DataTable

        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(100, 24)) as pilot:
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            before = app.screen.query_one(DataTable).cursor_row
            assert before > 0
            await pilot.resize_terminal(150, 24)
            await pilot.pause()
            assert app.screen.query_one(DataTable).cursor_row == before


class TestTimestampsInJobList:
    @pytest.mark.asyncio
    async def test_job_table_has_started_and_ended_columns(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(160, 24)) as pilot:
            await pilot.pause()
            await pilot.press("a")  # flat job list
            await pilot.pause()
            from textual.widgets import DataTable

            labels = [str(c.label) for c in app.screen.query_one(DataTable).columns.values()]
            assert "STARTED" in labels
            assert "ENDED" in labels

    @pytest.mark.asyncio
    async def test_started_outlives_ended_on_a_narrow_terminal(self):
        """Columns are fitted to the width, so something has to yield at 80
        columns. ENDED goes first because STARTED plus WALL TIME imply it;
        STARTED itself is what tells two same-named attempts apart."""
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            from textual.widgets import DataTable

            labels = [str(c.label) for c in app.screen.query_one(DataTable).columns.values()]
            assert "STARTED" in labels
            assert "ENDED" not in labels
            # The measurements survive the squeeze; the derivable column does not.
            assert "PEAK MEM" in labels
            assert "CPUS BUSY" in labels

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

    def test_plain_renderer_shows_them_too(self, monkeypatch):
        """The dashboard and the text output must not disagree.

        The table uses the compact ``MM-DD HH:MM`` form, not full ISO -- the
        clipboard payload carries the full timestamps instead.

        Given room for every column, both front ends show both stamps: they now
        share one column spec, so they cannot label or order them differently.
        """
        import re

        from slurmpast.report import Style, render_list

        monkeypatch.setenv("COLUMNS", "150")
        text = render_list(history()[:5], style=Style(enabled=False))
        assert "STARTED" in text and "ENDED" in text
        assert re.search(r"\d\d-\d\d \d\d:\d\d", text)

    def test_started_outlives_ended_when_the_terminal_is_narrow(self, monkeypatch):
        """ENDED is the first column dropped, deliberately: STARTED plus WALL TIME
        recover it, whereas nothing else on the row recovers a node name or a peak
        memory figure. Pinned because the alternative -- keeping all 13 columns at
        135 cells wide -- wrapped every row on a 100-column terminal, and a
        wrapped table is worse than a narrow one."""
        from slurmpast.report import Style, render_list

        monkeypatch.setenv("COLUMNS", "100")
        text = render_list(history()[:5], style=Style(enabled=False))
        assert "STARTED" in text
        assert "ENDED" not in text
        assert "PEAK MEM" in text and "NODE" in text
        assert max(len(line) for line in text.splitlines()) <= 100


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
            # "outcome" is not listed: it holds only a non-zero exit code and the
            # like, so a clean run has no such section rather than a heading over
            # one line repeating the state from the title.
            for section in ("job", "timing", "memory"):
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
    async def test_the_fallback_file_is_utf8_whatever_the_locale_says(self, tmp_path, monkeypatch):
        """What gets copied always holds ``●``, ``·`` and box drawing. Writing it
        with the locale's encoding meant that on a Python whose preferred encoding
        resolves to ASCII, `y` raised UnicodeEncodeError -- a ValueError, so the
        OSError handler beside it would not have caught it, and the exception left
        a UI action handler."""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("Y")
            await pilot.pause()
        clip = tmp_path / "slurmpast" / "clip.txt"
        # Decodes as UTF-8 regardless of the ambient locale, and round-trips.
        raw = clip.read_bytes()
        assert raw.decode("utf-8").strip()

    def test_the_help_text_names_the_path_it_actually_writes(self, tmp_path, monkeypatch):
        """It advertised ~/.cache/slurmpast/clip.txt, which is wrong wherever
        XDG_CACHE_HOME is set -- and the code has always honoured that."""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        assert tui._clip_path().startswith(str(tmp_path))

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
            await pilot.press("f")  # -> "problem"
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
            # The count is on the summary line, not repeated up here: the job list
            # printed "58 jobs" in both places.
            assert "jobs" not in app.screen.sub_title
            assert "jobs" in app.screen.summary_text.plain


class TestSingularPlural:
    """Counts live on the summary line, not the title bar -- the title bar carries
    the window and any active filter or sort, and nothing else."""

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
            summary = app.screen.summary_text.plain
            assert "1 job" in summary
            assert "1 jobs" not in summary

    @pytest.mark.asyncio
    async def test_one_workload_is_not_one_workloads(self):
        from slurmpast.demo import history as demo

        single = [j for j in demo() if j.name == "soup-merge"]
        app = make_app(single, no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            summary = app.screen.summary_text.plain
            assert "1 workload" in summary
            assert "1 workloads" not in summary

    @pytest.mark.asyncio
    async def test_both_counts_share_one_line(self):
        """Reported as "why not putting workloads at the same line as jobs?" --
        "233 jobs rolled up into 41 workloads" is one fact and it was split
        between the title bar and the summary."""
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            first = app.screen.summary_text.plain.splitlines()[0]
            assert "jobs in" in first and "workloads" in first
            # And not repeated in the title bar.
            assert "workload" not in app.screen.sub_title

    @pytest.mark.asyncio
    async def test_a_narrowed_table_still_reports_the_true_total(self):
        """The header count has to stay honest when a filter hides rows."""
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            total = app.screen.summary_text.plain.splitlines()[0]
            await pilot.press("f")  # -> problems only
            await pilot.pause()
            narrowed = app.screen.summary_text.plain.splitlines()[0]
            assert narrowed.startswith(total.split("  ·  ")[0])
            assert "showing" in narrowed


class TestExcludedRecordsAreNamed:
    """A record dropped as unterminated must not just vanish from its workload."""

    def _with_a_running_job(self):
        from slurmpast.demo import history as demo

        jobs = [j for j in demo() if j.name == "soup-merge"]
        live = jobs[0]._replace(job_id="9999999", end=None, state="RUNNING", open_ended=True)
        return jobs + [live]

    def test_group_counts_what_it_lost(self):
        from slurmpast.index import build_groups

        group = [g for g in build_groups(self._with_a_running_job()) if g.name == "soup-merge"][0]
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
            assert "unterminated, excluded" in app.screen.summary_text.plain

    def test_plain_overview_shows_the_window(self):
        from slurmpast.demo import history as demo
        from slurmpast.index import History
        from slurmpast.report import Style, render_overview

        h = History(demo(), window="now-30days → now")
        text = render_overview(h, style=Style(enabled=False))
        assert "window now-30days → now" in text


class TestBarLooksLikeAGauge:
    """The empty track was ``─``, which renders as a string of dashes and reads as
    punctuation rather than the unfilled remainder of a bar. slurmwatch uses a
    shaded block; these two tools sit either side of the same job and should not
    look like different products."""

    def test_empty_track_is_a_shaded_block_not_a_line(self):
        text = render.bar(40, "cyan", width=10).plain
        assert "░" in text
        assert "─" not in text

    def test_partial_cells_are_drawn(self):
        """Eighth-block caps land the fill on its true position.

        30% of 8 cells is 2.4, so the cap must appear. (37% of 8 lands on exactly
        3 whole cells -- a value with no remainder correctly draws no cap.)
        """
        text = render.bar(30, "cyan", width=8).plain
        assert any(g in text for g in "▏▎▍▌▋▊▉")

    def test_no_cap_when_the_fill_lands_on_a_whole_cell(self):
        assert render.bar(37, "cyan", width=8).plain == "███░░░░░"

    def test_zero_is_an_empty_track_not_a_blank(self):
        assert render.bar(0, "cyan", width=6).plain == "░" * 6

    def test_none_is_an_empty_track(self):
        assert render.bar(None, "cyan", width=6).plain == "░" * 6

    def test_a_sliver_survives_for_any_visible_percentage(self):
        """A bar must never read empty beside a non-zero number."""
        assert render.bar(1, "cyan", width=20).plain[0] != "░"

    def test_full_only_when_it_rounds_to_100_at_our_precision(self):
        """Labels carry one decimal, so 99.6% must not draw a completely full bar."""
        assert "░" not in render.bar(100, "cyan", width=10).plain
        near = render.bar(99.6, "cyan", width=10).plain
        assert near != "█" * 10

    def test_ascii_mode_has_no_block_glyphs(self):
        text = render.bar(50, "cyan", width=10, ascii_mode=True).plain
        assert set(text) <= set("#-")

    @pytest.mark.parametrize("percent", [0.0, 0.4, 0.6, 0.94, 0.95, 1.0, 4.0, 50.0, 99.6, 100.0])
    def test_ascii_and_unicode_agree_on_whether_anything_is_lit(self, percent):
        """Both docstrings promise a lit cell for anything that *prints* as >=1%,
        but one tested `>= 0.5` and the other `round(x, 1) >= 1.0`, so over
        0.5-0.94% the ASCII bar lit a cell beside a label reading "0.7%" and the
        Unicode bar did not."""
        unicode_lit = render.bar(percent, "cyan", width=10).plain[0] != "░"
        ascii_lit = render.bar(percent, "cyan", width=10, ascii_mode=True).plain[0] != "-"
        assert unicode_lit == ascii_lit, percent

    @pytest.mark.parametrize("percent", [0.4, 0.94])
    def test_a_value_printing_below_one_percent_lights_nothing(self, percent):
        from slurmpast.duration import format_percent

        assert format_percent(percent / 100.0) in ("0.4%", "0.9%")
        assert render.bar_cells(percent, 10) == 0


class TestWorkloadBannerSurvivesRefresh:
    """The pattern banner was written into #summary from on_mount, but
    refresh_rows rewrites that widget on every filter and search keystroke -- so
    the banner vanished on the first `f` press. Found by mypy objecting to reading
    a Static widget's rendered content back off the widget, which was the smell.
    """

    def _hung_workload(self):
        from slurmpast.demo import history as demo

        return [j for j in demo() if j.name == "cot-exp"]

    @pytest.mark.asyncio
    async def test_banner_is_present_initially(self):
        app = make_app(self._hung_workload(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            extra = app.screen.extra_summary()
            assert extra is not None
            assert "failed repeatedly" in extra.plain

    @pytest.mark.asyncio
    async def test_banner_still_there_after_filtering(self):
        app = make_app(self._hung_workload(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("f")  # this used to wipe it
            await pilot.pause()
            assert "failed repeatedly" in app.screen.summary_text.plain

    @pytest.mark.asyncio
    async def test_a_clean_workload_gets_no_failure_banner(self):
        """No findings banner -- though sizing advice may still appear, which is
        the whole point of the screen."""
        from slurmpast.demo import history as demo

        clean = [j for j in demo() if j.name == "midtrain"]
        app = make_app(clean, no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            extra = app.screen.extra_summary()
            text = "" if extra is None else extra.plain
            assert "failed repeatedly" not in text

    @pytest.mark.asyncio
    async def test_flat_job_list_has_no_banner_hook_content(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            assert app.screen.extra_summary() is None
