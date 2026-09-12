"""Two usability defects reported from real use, and their fixes.

1. Dragging to select did nothing. Textual 0.89 hands the terminal's mouse to
   the app and has no in-app selection API (that arrived in 1.x), so there was
   no way to get text out of the dashboard at all.
2. A workload with hundreds of identically-named runs showed no timestamps, so
   there was no way to tell which attempt a row was.
"""

import pathlib

import pytest

pytest.importorskip("textual")

from slurmpast import render, theme, tui
from slurmpast.demo import history
from slurmpast.index import History


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

    def test_an_unwritable_cache_home_costs_nothing(self, tmp_path, monkeypatch):
        """The failing side of the same question, which the three tests above do
        not reach -- they all point at a writable directory.

        This is the only path in the package that writes state anywhere, and a
        clipboard fallback file is not worth failing a report over. Exercised on a
        second cluster with the directory unwritable and reported as degrading
        silently at rc=0; confirmed here, since "we never write anything" and "we
        write and handle the failure" look identical from outside and only one of
        them keeps working when the feature is used.
        """
        import os

        blocked = tmp_path / "blocked"
        blocked.mkdir()
        blocked.chmod(0o500)
        monkeypatch.setenv("XDG_CACHE_HOME", str(blocked / "slurmpast-cache"))
        try:
            assert tui._clip_path() == ""
        finally:
            blocked.chmod(0o700)
            os.rmdir(blocked)

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
                # As on the real Textual `App`; `tui.run` reads it to propagate a
                # signalled exit (143/129/130).
                self.return_code = 0

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
        """On the LANDING screen, which is where the count actually lives.

        This pressed `a` first and then read the job-list screen's sentence -- a
        different one, always correct -- so it stayed green for rounds while the
        overview said "1 jobs in 1 workload". The sibling test below asserts the
        `workload` half of that same line, so only the half that was broken went
        unchecked. Both screens are read now.
        """
        from slurmpast.demo import history as demo

        single = [j for j in demo() if j.name == "soup-merge"]
        assert len(single) == 1
        app = make_app(single, no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            overview = app.screen.summary_text.plain
            await pilot.press("a")
            await pilot.pause()
            joblist = app.screen.summary_text.plain
        for where, summary in (("overview", overview), ("job list", joblist)):
            assert "1 job" in summary, (where, summary)
            assert "1 jobs" not in summary, (where, summary)

    def test_the_plain_overview_says_it_the_same_way(self):
        """`render.py` exists so the two surfaces cannot differ, and this sentence
        is built separately in each -- so it is checked in each."""
        from slurmpast.demo import history as demo
        from slurmpast.report import Style, render_overview

        single = [j for j in demo() if j.name == "soup-merge"]
        text = render_overview(History(single, window="w"), style=Style(enabled=False))
        assert "1 job in 1 workload" in text, text
        assert "1 jobs" not in text

    @pytest.mark.asyncio
    async def test_the_plural_is_untouched_above_one(self):
        """The control, on both surfaces."""
        from slurmpast.report import Style, render_overview

        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            summary = app.screen.summary_text.plain
        assert "58 jobs in 8 workloads" in summary, summary
        text = render_overview(History(history(), window="w"), style=Style(enabled=False))
        assert "58 jobs in 8 workloads" in text

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
        # The label alone; "window" in front of it was the tool's own vocabulary.
        assert "now-30days → now" in text


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

    def test_the_tip_has_track_behind_it(self):
        """An eighth-block paints only its own fraction of a cell, so without a
        background the rest of that cell is bare terminal and the tip reads as a
        notch rather than as a position."""
        text = render.bar(74.8, "cyan", width=18)
        assert "▌" in text.plain, text.plain
        tip = [sp for sp in text.spans if text.plain[sp.start] in "▏▎▍▌▋▊▉"]
        assert tip, "the tip must carry a style of its own"
        assert theme.TRACK_BG in str(tip[0].style), str(tip[0].style)

    def test_anything_short_of_full_keeps_a_whole_cell_of_track(self):
        """Reported twice: "there is nothing at the end of the final tip", then
        "the tip is still not obvious at all" after the background was added.

        At 96.6% of 18 cells the fill took 3/8 of the last cell and left 5/8 of dark
        behind it, which is not a gap a reader can see. Withholding one eighth was
        never enough; the whole final cell has to stay track."""
        for pct in (94.4, 96.6, 99.6, 99.9):
            drawn = render.bar(pct, "cyan", width=18).plain
            assert drawn.endswith("░"), (pct, drawn)
            assert drawn.count("░") >= 1

    def test_a_full_bar_is_the_only_one_that_reaches_the_end(self):
        """Which is what makes the reserved cell worth its cost: "at the limit" and
        "nearly at the limit" are now different pictures."""
        assert render.bar(100.0, "cyan", width=18).plain == "█" * 18
        assert render.bar(99.9, "cyan", width=18).plain != "█" * 18

    def test_the_reserved_cell_costs_the_top_of_the_range_and_that_is_accepted(self):
        """94.5% and 99.9% draw alike now. The figure is printed beside the bar, and
        a gauge whose last 5% was invisible distinguished nothing anyway."""
        assert render.bar(94.5, "cyan", width=18).plain == render.bar(99.9, "cyan", width=18).plain

    @pytest.mark.parametrize("pct", [0.0, 1.0, 30.0, 50.0, 94.4, 95.9, 99.6, 100.0])
    def test_every_cell_of_every_bar_is_painted(self, pct):
        """No unstyled cell anywhere in the width: an unstyled cell is a hole, and a
        hole in the middle of a gauge is indistinguishable from the end of it."""
        text = render.bar(pct, "cyan", width=18)
        painted = set()
        for span in text.spans:
            painted.update(range(span.start, span.end))
        assert painted == set(range(18)), (pct, sorted(set(range(18)) - painted))

    def test_a_surface_that_discards_styles_gets_whole_cells(self):
        """render_job appends line.plain, so no background survives there. Without
        one the tip is a notch, so that surface rounds to whole cells instead --
        the percentage is printed beside it either way."""
        text = render.bar(95.9, "cyan", width=18, flat=True).plain
        assert text == "█" * 17 + "░", text
        assert not any(g in text for g in "▏▎▍▌▋▊▉")

    def test_the_flat_bar_still_spans_the_full_width(self):
        for pct in (0.0, 1.0, 55.5, 95.9, 100.0):
            assert len(render.bar(pct, "cyan", width=18, flat=True).plain) == 18

    def test_the_plain_report_uses_the_flat_bar(self):
        """The path that actually showed the notch."""
        from slurmpast.demo import history
        from slurmpast.report import Style, render_job

        job = max(history(), key=lambda j: j.walltime_used or 0)
        text, _ = render_job(job, style=Style(enabled=False))
        bars = [ln for ln in text.splitlines() if "█" in ln or "░" in ln]
        assert bars, "expected gauge rows"
        for line in bars:
            assert not any(g in line for g in "▏▎▍▌▋▊▉"), line

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
            assert "Failing the same way" in extra.plain

    @pytest.mark.asyncio
    async def test_banner_still_there_after_filtering(self):
        app = make_app(self._hung_workload(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("f")  # this used to wipe it
            await pilot.pause()
            assert "Failing the same way" in app.screen.summary_text.plain

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
            assert "Failing the same way" not in text

    @pytest.mark.asyncio
    async def test_flat_job_list_has_no_banner_hook_content(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            assert app.screen.extra_summary() is None


class TestTheSearchBoxPromisesWhatItMatches:
    """Three descriptions of one feature, none of them right.

    The placeholder said "name, job id, state, node or date", the help screen said
    "name, job id, state or node", and `filter_jobs` matches partition as well. The
    expensive one was the overview: the same placeholder appeared there, and a
    workload rollup has no single job id, state or node to match on, so

        job id    '5100001'        job list: 1 job      overview: NO MATCH
        state     'TIMEOUT'        job list: 14 jobs    overview: NO MATCH
        node      'midway3-0602'   job list: 8 jobs     overview: NO MATCH

    -- three of the five things the box invited, on the landing screen, returning
    nothing. That is the failure `filter_jobs` already names in its own comment:
    "typing what you can plainly see and getting an empty list is the worst kind of
    empty result -- it reads as missing data."

    The promise is derived from the field list now rather than written out, so both
    are checked against the behaviour here rather than against each other.
    """

    @staticmethod
    def _probe():
        from slurmpast.index import build_groups

        jobs = [j for j in history() if not j.open_ended]
        sample = next(j for j in jobs if j.node_list and j.start and j.base_state)
        return jobs, build_groups(jobs), sample

    def _query_for(self, field, job):
        return {
            "name": job.name,
            "job id": job.job_id,
            "state": job.base_state,
            "partition": job.partition,
            "node": job.node_list,
            "date": (job.start or "")[5:10],
        }[field]

    def test_every_field_the_job_list_promises_actually_matches(self):
        from slurmpast.index import JOB_SEARCH_FIELDS, filter_jobs

        jobs, _groups, sample = self._probe()
        for field in JOB_SEARCH_FIELDS:
            query = self._query_for(field, sample)
            assert query, "the fixture should carry a %s" % field
            assert filter_jobs(jobs, "all", query), (
                "job list promises %r, matched nothing for %r"
                % (
                    field,
                    query,
                )
            )

    def test_every_field_the_overview_promises_actually_matches(self):
        from slurmpast.index import GROUP_SEARCH_FIELDS, filter_groups

        _jobs, groups, sample = self._probe()
        for field in GROUP_SEARCH_FIELDS:
            query = self._query_for(field, sample)
            assert filter_groups(groups, "all", query), (
                "overview promises %r, matched nothing" % field
            )

    def test_the_overview_does_not_promise_what_it_cannot_match(self):
        """The control, and the actual defect: these three are exactly what the old
        placeholder invited on this screen and what it could never find."""
        from slurmpast.index import GROUP_SEARCH_FIELDS, filter_groups

        _jobs, groups, sample = self._probe()
        for field in ("job id", "state", "node"):
            assert field not in GROUP_SEARCH_FIELDS, field
            assert not filter_groups(groups, "all", self._query_for(field, sample)), field

    @pytest.mark.asyncio
    async def test_each_screen_shows_its_own_placeholder(self):
        from slurmpast.index import GROUP_SEARCH_FIELDS, JOB_SEARCH_FIELDS

        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            overview = app.screen.query_one("#search").placeholder
            await pilot.press("a")
            await pilot.pause()
            joblist = app.screen.query_one("#search").placeholder

        assert render.search_hint(GROUP_SEARCH_FIELDS) in overview, overview
        assert render.search_hint(JOB_SEARCH_FIELDS) in joblist, joblist
        # The three the overview cannot match must not be advertised there.
        for word in ("job id", "state", "node"):
            assert word not in overview, overview
            assert word in joblist, joblist

    def test_the_help_row_names_both_sets(self):
        row = dict(tui._HELP_KEYS)["/"]
        assert "overview matches" in row and "job list also matches" in row, row
        for word in ("job id", "state", "node"):
            assert word in row, row

    def test_the_hint_reads_as_english(self):
        assert render.search_hint(("name",)) == "name"
        assert render.search_hint(("name", "date")) == "name or date"
        assert render.search_hint(("a", "b", "c")) == "a, b or c"
        assert render.search_hint(()) == ""


class TestTheHelpIsReachableFromEveryScreen:
    """`?` answered on four of the six screens and did nothing on the other two.

    `HelpScreen` carries two rows written for the nodes screen in particular --

        ("m", "on the nodes screen: measure hangs or failures"),
        ("c", "on the nodes screen: drop the workload control (confounded)"),

    -- and the nodes screen was one of the two that could not open it. So was the
    patterns screen. The binding was written out on each screen that had it, three
    times, which is how two came to be without it; it lives on `ScreenChrome` with
    the copy pair now, so a new screen inherits it rather than remembering it.

    `TestTheHelpScreenNamesEveryVisibleKey` below iterates `tui.NodesScreen`'s
    bindings and checks the help documents them, and passed throughout -- this
    suite's named failure mode, a test asserting less than it appears to.
    """

    # (label, keys from the overview, expected screen class)
    ROUTES = [
        ("overview", [], "OverviewScreen"),
        ("workload", ["enter"], "WorkloadScreen"),
        ("job list", ["a"], "JobListScreen"),
        ("job", ["a", "enter"], "JobScreen"),
        ("patterns", ["p"], "PatternsScreen"),
        ("nodes", ["n"], "NodesScreen"),
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("label,keys,expected", ROUTES)
    async def test_question_mark_opens_the_help(self, label, keys, expected):
        app = make_app(history())
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            for key in keys:
                await pilot.press(key)
                await pilot.pause()
            assert type(app.screen).__name__ == expected, label
            await pilot.press("question_mark")
            await pilot.pause()
            assert isinstance(app.screen, tui.HelpScreen), "? did nothing on %s" % label

    @pytest.mark.asyncio
    @pytest.mark.parametrize("label,keys,expected", ROUTES)
    async def test_and_escape_puts_it_back_where_it_was(self, label, keys, expected):
        """The control. A binding that opens a modal nobody can leave is not a fix,
        and the screen underneath has to be the one the reader was on."""
        app = make_app(history())
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            for key in keys:
                await pilot.press(key)
                await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert type(app.screen).__name__ == expected, label

    def test_the_binding_is_declared_once_not_per_screen(self):
        """Three copies is what left two screens out. One list, five screens."""
        source = pathlib.Path(tui.__file__).read_text()
        # The modal's own dismiss binding is the only other `?` in the file.
        declarations = [
            line
            for line in source.splitlines()
            if "question_mark" in line and "dismiss" not in line
        ]
        assert len(declarations) == 1, declarations
        for screen in (
            tui.OverviewScreen,
            tui.JobListScreen,
            tui.JobScreen,
            tui.PatternsScreen,
            tui.NodesScreen,
        ):
            keys = {b.key for b in screen.BINDINGS}
            assert "question_mark" in keys, screen.__name__


class TestAnEmptyNodeTableIsNotDrawn:
    """`NodesScreen.refresh_rows` says, in its own comment, "Two ways this table
    has nothing to say, and an empty grid says neither" -- and then drew one.

    It set `rows = []` and added the explaining sentence, but the DataTable stayed
    mounted with its column headers, so the reader got:

        No hangs recorded for midtrain in this window, so there is nothing to
        attribute to a node.
        NODE                    N        RATE      95% CI          VERDICT
         no node is worse than the rest; nothing to exclude.

    -- a bare header over nothing, which reads as a table that failed to load,
    followed by a second sentence answering a question the first said could not be
    asked. `report.render_nodes` returns before drawing any of it.
    """

    @staticmethod
    def _healthy():
        """A history with no bad outcome, so the table has nothing to compare."""
        jobs = [j for j in history() if j.completed and not j.open_ended]
        assert jobs, "the demo has no clean runs"
        return jobs

    def test_the_fixture_really_produces_the_empty_branch(self):
        from slurmpast.nodes import dominant_workload, node_table

        h = History(self._healthy())
        workload = dominant_workload(h.usable_jobs, metric="hang")
        table = node_table(h.usable_jobs, workload=workload, metric="hang")
        assert render.nodes_empty_reason(table, "hang", workload, widen="w")
        # The interesting part: `node_table` DOES return a row. It is the empty
        # *reason* that says the row is not worth showing, which is why setting
        # `rows = []` and leaving the widget up was possible at all.
        assert table["rows"]

    @pytest.mark.asyncio
    async def test_the_grid_is_hidden_and_the_sentence_stands_alone(self):
        from textual.widgets import DataTable

        app = make_app(self._healthy(), no_logs=True)
        async with app.run_test(size=(90, 26)) as pilot:
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, tui.NodesScreen)
            assert screen.query_one("#nodes", DataTable).display is False
            # And the redundant second line goes with it.
            assert screen.exclude_text.plain.strip() == "", screen.exclude_text.plain
            assert "nothing to attribute" in screen.summary_text.plain

    @pytest.mark.asyncio
    async def test_a_history_with_something_to_say_still_gets_its_table(self):
        """The control. Hiding the grid must not hide it when there are rows."""
        from textual.widgets import DataTable

        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(90, 26)) as pilot:
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            table = app.screen.query_one("#nodes", DataTable)
            assert table.display is True
            assert table.row_count >= 1
            assert app.screen.exclude_text.plain.strip()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", ["m", "c", "question_mark", "q"])
    async def test_the_keys_still_work_with_the_grid_hidden(self, key):
        """`on_mount` focuses the table, and it is not displayed on this branch."""
        app = make_app(self._healthy(), no_logs=True)
        async with app.run_test(size=(90, 26)) as pilot:
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            before = (app.screen.metric, app.screen.controlled)
            await pilot.press(key)
            await pilot.pause()
            if key == "q":
                assert isinstance(app.screen, tui.OverviewScreen)
            elif key == "question_mark":
                assert isinstance(app.screen, tui.HelpScreen)
            else:
                assert (app.screen.metric, app.screen.controlled) != before

    def test_the_plain_report_never_reached_any_of_it(self):
        """Which is the standard the screen is being held to."""
        from slurmpast.report import Style, render_nodes

        text = render_nodes(History(self._healthy()), metric="hang", style=Style(enabled=False))
        assert "nothing to attribute" in text
        assert "VERDICT" not in text
        assert "nothing to exclude" not in text


class TestOneGpuHourIsNotOneGpuHours:
    """The overview's summary clause, written out in both front ends as
    ``"%.0f GPU-hours total"`` and guarded in neither.

    A history whose whole GPU spend rounds to an hour -- one run of one card that
    hung, which is the first thing anyone tries `--demo <jobid>` on -- read:

        1 job in 1 workload · 0.0% completed · 1 GPU-hours total, 1 of them never used

    Two disagreements in one clause: the noun, and the pronoun after it, which
    refers back to the *total* rather than to the idle count. Round seven fixed
    nine unguarded plurals; this pair sits in the one clause that appears only when
    the idle share is material, so none of its reproductions reached it.
    """

    def test_the_singular(self):
        assert render.gpu_hours_total(1) == "1 GPU-hour total"
        assert render.idle_hours_note(1, 1) == ", 1 of it never used"

    def test_the_plural(self):
        assert render.gpu_hours_total(184) == "184 GPU-hours total"
        assert render.idle_hours_note(91, 184) == ", 91 of them never used"

    def test_the_word_agrees_with_the_printed_digit_not_the_float(self):
        """`%.0f` is what the reader sees, so that is what has to agree: 1.4 hours
        prints as "1" and must not say "hours"."""
        assert render.gpu_hours_total(1.4) == "1 GPU-hour total"
        assert render.idle_hours_note(1, 1.4) == ", 1 of it never used"
        assert render.gpu_hours_total(1.6) == "2 GPU-hours total"

    def test_the_pronoun_follows_the_total_not_the_idle_count(self):
        """The control: one idle hour out of five is still "of them"."""
        assert render.idle_hours_note(1, 5) == ", 1 of them never used"

    @pytest.mark.asyncio
    async def test_both_surfaces_say_the_same_thing(self):
        from slurmpast.report import Style, render_overview

        one = [history()[0]]
        h = History(one)
        assert h.idle_gpu_hours is not None, "the fixture must trip the idle clause"
        clause = render.gpu_hours_total(h.idle_gpu_hours[1]) + render.idle_hours_note(
            *h.idle_gpu_hours[::-1]
        )
        assert clause == "1 GPU-hour total, 1 of it never used", clause

        assert clause in render_overview(h, style=Style(enabled=False))
        app = make_app(one, no_logs=True)
        async with app.run_test(size=(100, 26)) as pilot:
            await pilot.pause()
            assert clause in app.screen.summary_text.plain, app.screen.summary_text.plain


class TestEveryCountedNounAgreesWithItsCount:
    """Round seven fixed nine unguarded plurals. Four survived, and they share a
    shape: the count can only be 1 on a *small* history, and the demo has 58 jobs.

        History.headline              1 GPU-hours, 1 of them in allocations ...
        patterns.find_repeat_failures 1 GPU-hours consumed by the failures.
        patterns.summarize            Together they held 1 GPU-hours.
        OverviewScreen.clipboard_row  ... | 1 problems | ... | 1 GPU-hours | ...

    Each was reproduced by building the input rather than by reading the format
    string -- which matters, because the same sweep flagged three more that are
    guarded after all: `diagnose`'s "of %d cores" cannot fire below `cores > 1`,
    and `render.held_back_note` and `nodes_correction_note` spell both forms out.

    `duration.plural` is the one rule now. It lives there rather than in `render`
    because three of the four sites are in `index` and `patterns`, which may not
    import `render`.
    """

    def test_the_rule_follows_the_printed_digit(self):
        from slurmpast.duration import plural

        assert plural(1, "GPU-hour") == "GPU-hour"
        assert plural(2, "GPU-hour") == "GPU-hours"
        assert plural(0, "GPU-hour") == "GPU-hours"
        # `%.0f` is what the reader sees, so 1.4 takes the singular and 1.6 does not.
        assert plural(1.4, "problem") == "problem"
        assert plural(1.6, "problem") == "problems"
        # None is what an unmeasured figure is; it must not raise.
        assert plural(None, "run") == "runs"

    @staticmethod
    def _one_gpu_hour():
        """One run of one card that held it for an hour and computed nothing."""
        job = next(j for j in history() if j.gpu_count == 1 and (j.total_cpu or 0) < 10)
        one = job._replace(elapsed=3600.0, start="2026-07-01T00:00:00", end="2026-07-01T01:00:00")
        assert round(one.gpu_hours) == 1, one.gpu_hours
        return one

    def test_the_footer_headline(self):
        h = History([self._one_gpu_hour()])
        assert h.headline() == "1 GPU-hour, 1 of it in allocations that never computed"

    def test_the_footer_headline_control(self):
        """Five hours is still "GPU-hours" and still "of them"."""
        five = self._one_gpu_hour()._replace(elapsed=18000.0, end="2026-07-01T05:00:00")
        assert History([five]).headline().startswith("5 GPU-hours, 5 of them")

    def test_the_repeat_failure_evidence(self):
        from slurmpast.patterns import REPEAT_MIN, find_repeat_failures

        base = self._one_gpu_hour()
        fails = [
            base._replace(
                job_id="70%02d" % i,
                state="TIMEOUT",
                elapsed=900.0,
                start="2026-07-%02dT00:00:00" % (i + 1),
                end="2026-07-%02dT00:15:00" % (i + 1),
            )
            for i in range(REPEAT_MIN)
        ]
        # Five quarter-hours on one card is 1.25 GPU-hours: over the `> 1.0` gate
        # that lets the clause fire, and printing as "1".
        evidence = " ".join(f.evidence for f in find_repeat_failures(fails))
        assert "1 GPU-hour consumed by the failures" in evidence, evidence

    def test_the_noop_summary(self):
        from slurmpast.patterns import REPEAT_MIN, summarize

        base = self._one_gpu_hour()
        dead = [
            base._replace(
                job_id="80%02d" % i,
                state="TIMEOUT",
                elapsed=900.0,
                start="2026-07-%02dT00:00:00" % (i + 1),
                end="2026-07-%02dT00:15:00" % (i + 1),
            )
            for i in range(REPEAT_MIN)
        ]
        evidence = " ".join(f.evidence for f in (summarize(dead) or []))
        assert "Together they held 1 GPU-hour." in evidence, evidence

    @pytest.mark.asyncio
    async def test_the_pasted_overview_row(self):
        app = make_app([self._one_gpu_hour()], no_logs=True)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            cells = app.screen.clipboard_row().split("\t")
        assert "1 problem" in cells, cells
        assert "1 GPU-hour" in cells, cells
        assert not any(c.startswith("1 ") and c.endswith("s") for c in cells), cells

    @pytest.mark.asyncio
    async def test_the_pasted_overview_row_control(self):
        """A multi-run workload keeps every plural it had."""
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.screen.query_one("#groups").move_cursor(row=1)  # midtrain, 14 runs
            await pilot.pause()
            cells = app.screen.clipboard_row().split("\t")
        assert any(c.endswith("GPU-hours") for c in cells), cells
        assert any(c.endswith("CPU-hours") for c in cells), cells

    def test_the_three_that_are_guarded_after_all(self):
        """The control on the sweep itself: a scan that reports a guarded site is
        a scan nobody will run twice."""
        from slurmpast.diagnose import diagnose
        from slurmpast.render import held_back_note, nodes_correction_note

        assert "1 node was" in held_back_note(1, 1)
        assert "1 interval clears" in held_back_note(1, 1)
        assert "1 node tested" in nodes_correction_note(1)
        # `cpu-overrequest` cannot fire on a single core -- `cores > 1` in the rule.
        one_core = next(j for j in history() if j.completed)._replace(
            alloc_cpus=1, ncpus=1, req_cpus=1, alloc_tres="cpu=1,mem=8G,node=1"
        )
        assert one_core.cpu_count == 1
        assert not [f for f in diagnose(one_core).findings if f.code == "cpu-overrequest"]


class TestATableThatMatchedNothingSaysSo:
    """Round sixteen fixed this on the node screen. The two screens a reader spends
    all their time in had it too, and theirs is reachable without a strange history:
    filter to `failed` on a week that went well, or search for a typo.

        overview, filter=problem, healthy week
          last 7 days · 33 jobs in 6 workloads · 100.0% completed
          #     JOB NAME     PARTITION  RUNS  FLAGGED  CPU / GPU-HOURS  LAST RUN
          <nothing>

    A column header over blank space, and not one word about the filter that
    emptied it. The overview could not even say "showing 0": that clause was
    guarded by `if shown and shown != total_groups`, so the one count that explains
    an empty table was the one count suppressed.

    `PatternsScreen` has always done it properly -- "That is a real answer, not an
    empty screen" -- and `filter_jobs` writes the rule down in its own comment:
    "Typing what you can plainly see and getting an empty list is the worst kind of
    empty result -- it reads as missing data."
    """

    @staticmethod
    def _healthy():
        jobs = [j for j in history() if j.completed and not j.open_ended]
        assert jobs
        return jobs

    def test_the_sentence_names_what_narrowed_and_what_undoes_it(self):
        assert render.nothing_matches("workload") == "no workload in this window."
        assert (
            render.nothing_matches("workload", filter_label="failed only")
            == "no workload matches the failed only filter — f widens it."
        )
        assert (
            render.nothing_matches("job", search="zzz")
            == 'no job matches the search "zzz" — escape clears it.'
        )
        both = render.nothing_matches("job", filter_label="failed only", search="zzz")
        assert "escape clears it" in both and "f widens it" in both

    @pytest.mark.asyncio
    async def test_the_overview_explains_an_empty_filter(self):
        from textual.widgets import DataTable

        app = make_app(self._healthy(), no_logs=True)
        async with app.run_test(size=(90, 20)) as pilot:
            await pilot.pause()
            await pilot.press("f")  # -> problems
            await pilot.pause()
            assert app.screen._rows == []
            assert app.screen.query_one("#groups", DataTable).display is False
            text = app.screen.summary_text.plain
        assert "showing 0" in text, text
        assert "no workload matches" in text, text
        assert "f widens it" in text, text

    @pytest.mark.asyncio
    async def test_the_job_list_explains_an_empty_search(self):
        from textual.widgets import DataTable

        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(90, 20)) as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            for ch in "zzz":
                await pilot.press(ch)
            # The search box re-filters once the typing stops; see
            # `tui._debounce_search` and `test_tui.settle_search`.
            await pilot.pause(tui._SEARCH_SETTLE * 2)
            await pilot.pause()
            assert app.screen._rows == []
            assert app.screen.query_one("#jobs", DataTable).display is False
            text = app.screen.summary_text.plain
        assert 'no job matches the search "zzz"' in text, text
        assert "escape clears it" in text, text

    @pytest.mark.asyncio
    async def test_a_table_with_rows_keeps_its_grid_and_says_nothing(self):
        """The control, both halves: the grid comes back, and the sentence does not
        appear on a table that has something in it."""
        from textual.widgets import DataTable

        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(90, 20)) as pilot:
            await pilot.pause()
            table = app.screen.query_one("#groups", DataTable)
            assert table.display is True
            assert table.row_count > 1
            assert "no workload matches" not in app.screen.summary_text.plain
            # And "showing N" still only appears when N differs from the total.
            assert "showing" not in app.screen.summary_text.plain

    @pytest.mark.asyncio
    async def test_showing_zero_is_reported_where_showing_two_already_was(self):
        """`if shown and ...` suppressed only the zero. Both are counts."""
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(90, 20)) as pilot:
            await pilot.pause()
            await pilot.press("f")  # problems: fewer than all, but not none
            await pilot.pause()
            partial = app.screen.summary_text.plain
        assert "showing 4" in partial, partial

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "key", ["enter", "f", "s", "slash", "1", "up", "down", "y", "Y", "question_mark"]
    )
    async def test_every_key_survives_the_hidden_grid(self, key):
        """`on_mount` focuses the table, and on this branch it is not displayed."""
        app = make_app(self._healthy(), no_logs=True)
        async with app.run_test(size=(90, 20)) as pilot:
            await pilot.pause()
            await pilot.press("f")
            await pilot.pause()
            await pilot.press(key)
            await pilot.pause()
            # Inside the context: `app.screen` raises once the app has exited.
            assert app.screen is not None


class TestATableIsNotBuiltTwiceToOpenItOnce:
    """`a` -- the flat job list -- took **6.8 seconds** on a real 30-day history.

    None of it was slurmpast's arithmetic: the cell values for all 13,363 rows
    compute in 0.32s. The table was being populated **twice**, 26,714 `add_row`
    calls for 13,363 jobs, because a screen has no size until the layout pass:
    `on_mount` built every row at `_DEFAULT_TABLE_WIDTH` and the first resize
    rebuilt every row at the real width.

        width  before   after
           80   6.06s   3.13s
          100   7.11s   3.70s
          160   9.03s   4.79s

    Only real data showed it. The demo has 58 jobs, where twice nothing is nothing.

    One change: `_rows_already_drawn` makes the second call a no-op. Deferring the
    mount build to `call_after_refresh` was tried alongside it and measured at
    3.64s against the guard's 3.55s -- it buys nothing and is not in the tree.
    Recorded because the first account of this bug blamed a provisional mount-time
    width, and the trace meant to confirm that showed both calls computing an
    identical layout.
    """

    @staticmethod
    def _many(n=400):
        """Enough rows that a double build is unambiguous, few enough to stay fast."""
        base = list(history())
        out = []
        for index in range(n):
            job = base[index % len(base)]
            out.append(job._replace(job_id="8%06d" % index))
        return out

    @staticmethod
    def _counting_add_row(monkeypatch):
        from textual.widgets import DataTable

        seen = {"n": 0}
        original = DataTable.add_row

        def counted(self, *args, **kwargs):
            seen["n"] += 1
            return original(self, *args, **kwargs)

        monkeypatch.setattr(DataTable, "add_row", counted)
        return seen

    @staticmethod
    def _builds(monkeypatch):
        """Every (layout, rows) the guard let through, i.e. every actual build.

        Counting `add_row` alone cannot express the guard's contract. It does not
        promise one build per screen -- it promises no build at a layout already
        drawn -- and on Textual 0.86 those differ. There the app lays a screen out
        at one size and then at its real one, so the overview builds a 7-column
        table and then an 8-column table that gains `COMPLETED`; both are honest
        builds of genuinely different layouts, and the guard correctly suppressed
        the duplicate *within* each pair.

        The original form of these two tests asserted `add_row == row_count`, which
        is that stronger property, and it happens to hold on modern Textual because
        a screen pushed onto a laid-out app already has its size. It was written
        against 8.2.8 and never ran on the floor until CI reached it. Asserting the
        contract the code states, rather than the coincidence one version produces,
        is the point of the class this sits in.
        """
        import slurmpast.tui as tui_module

        seen = []
        original = tui_module._rows_already_drawn

        def spy(screen, layout, key):
            already = original(screen, layout, key)
            if not already:
                seen.append((type(screen).__name__, tuple(layout), key))
            return already

        monkeypatch.setattr(tui_module, "_rows_already_drawn", spy)
        return seen

    @pytest.mark.asyncio
    async def test_the_job_list_adds_each_row_once(self, monkeypatch):
        from textual.widgets import DataTable

        jobs = self._many()
        builds = self._builds(monkeypatch)
        seen = self._counting_add_row(monkeypatch)
        app = make_app(jobs, no_logs=True)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            seen["n"] = 0
            builds.clear()
            await pilot.press("a")
            await pilot.pause()
            # Deterministically, not whenever the background fill happens to get
            # there: rows arrive in slices now, and `pilot.pause` waiting for CPU
            # idle is not a promise that every slice has run. Without this the
            # count depends on how fast the runner is, which is how this failed on
            # the oldest-Textual job and passed everywhere else.
            app.screen.ensure_all_rows()
            rows = app.screen.query_one("#jobs", DataTable).row_count
        assert rows == len(jobs), rows
        # No layout is built twice, and no row is added twice.
        assert len(builds) == len(set(builds)), builds
        # AT MOST one pass per build. It used to be exactly that. With the
        # deferred fill a build that is superseded before it finishes stops where
        # it is -- on Textual 0.86 the app lays a screen out twice, and the first
        # layout's fill is cancelled partway, so 400 rows across 2 builds cost 600
        # add_row calls rather than 800. Less work for the same table is the point
        # of the fill; more work than one pass per build is the bug this class is
        # about, and that is what is asserted.
        assert seen["n"] <= rows * len(builds), (
            "%d add_row calls for %d rows across %d build(s)" % (seen["n"], rows, len(builds))
        )
        assert seen["n"] >= rows, "%d add_row calls cannot have filled %d rows" % (seen["n"], rows)

    @pytest.mark.asyncio
    async def test_the_overview_adds_each_row_once(self, monkeypatch):
        from textual.widgets import DataTable

        builds = self._builds(monkeypatch)
        seen = self._counting_add_row(monkeypatch)
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            rows = app.screen.query_one("#groups", DataTable).row_count
        assert rows > 1
        assert len(builds) == len(set(builds)), builds
        assert seen["n"] == rows * len(builds), (
            "%d add_row calls for %d rows across %d build(s)" % (seen["n"], rows, len(builds))
        )

    @pytest.mark.asyncio
    async def test_a_refresh_that_changes_nothing_rebuilds_nothing(self, monkeypatch):

        seen = self._counting_add_row(monkeypatch)
        app = make_app(self._many(), no_logs=True)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            # Finish the fill before counting, or the slices still to come are
            # attributed to the refreshes below. See the sibling test.
            app.screen.ensure_all_rows()
            seen["n"] = 0
            app.screen.refresh_rows(keep_cursor=True)
            app.screen.refresh_rows(keep_cursor=True)
            await pilot.pause()
        assert seen["n"] == 0, seen["n"]

    @pytest.mark.asyncio
    async def test_a_filter_that_does_change_the_rows_still_rebuilds(self, monkeypatch):
        """The control that matters most: the guard must not make the table stale.
        A fingerprint keyed on `id(rows)` was the first attempt and never matched --
        every caller builds a fresh list -- so it silently never fired at all."""
        from textual.widgets import DataTable

        seen = self._counting_add_row(monkeypatch)
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            before = app.screen.query_one("#groups", DataTable).row_count
            seen["n"] = 0
            await pilot.press("f")  # -> problems
            await pilot.pause()
            after = app.screen.query_one("#groups", DataTable).row_count
        assert after < before, (before, after)
        assert seen["n"] == after, "%d add_row calls for %d rows" % (seen["n"], after)

    @pytest.mark.asyncio
    async def test_a_resize_that_changes_the_layout_still_rebuilds(self, monkeypatch):
        """The other control. A wider terminal is a different column layout, and
        the rows carry the column widths."""
        from textual.widgets import DataTable

        seen = self._counting_add_row(monkeypatch)
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(90, 30)) as pilot:
            await pilot.pause()
            narrow = list(app.screen._layout)
            seen["n"] = 0
            await pilot.resize_terminal(150, 30)
            await pilot.pause()
            wide = list(app.screen._layout)
            rows = app.screen.query_one("#groups", DataTable).row_count
        assert wide != narrow, wide
        assert seen["n"] == rows, "%d add_row calls for %d rows" % (seen["n"], rows)
