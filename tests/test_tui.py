"""Headless dashboard tests.

Textual's ``run_test`` drives the real app without a terminal, so navigation and
key bindings are exercised rather than assumed. These are the tests that catch a
bad format string or a wrong widget id -- the kind of bug that only appears when
a screen actually paints.
"""

import pytest

pytest.importorskip("textual")

from slurmpast import theme, tui


def make_app(jobs, **kwargs):
    return tui.SlurmpastApp(lambda: list(jobs), window="test window", **kwargs)


async def settle_search(pilot):
    """Wait out the search box's debounce.

    `tui._debounce_search` re-filters once the keystrokes STOP rather than on
    each one: rebuilding the flat job list is 100-311 ms at 29,617 jobs -- 139 ms
    of that is `DataTable.clear`, which is Textual's own -- so typing "test" was
    four of those back to back. Only the tests that type need this; enter commits
    and escape cancels without waiting, which is the point of both.
    """
    await pilot.pause(tui._SEARCH_SETTLE * 2)
    await pilot.pause()


@pytest.fixture
def history_jobs(repeat_timeouts, oom_series, healthy_job):
    return list(repeat_timeouts) + list(oom_series) + [healthy_job]


class TestBoot:
    @pytest.mark.asyncio
    async def test_lands_on_overview_after_loading(self, history_jobs):
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.history is not None
            assert isinstance(app.screen, tui.OverviewScreen)

    @pytest.mark.asyncio
    async def test_theme_registered(self, history_jobs):
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.theme == "slurmpast"

    @pytest.mark.asyncio
    async def test_loader_failure_surfaces_not_swallowed(self):
        def boom():
            raise RuntimeError("sacct exploded")

        app = tui.SlurmpastApp(boom, window="w")
        async with app.run_test() as pilot:
            await pilot.pause()
        assert app.load_error is not None
        assert "sacct exploded" in app.load_error


class TestNavigation:
    @pytest.mark.asyncio
    async def test_enter_opens_a_workload(self, history_jobs):
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, tui.WorkloadScreen)

    @pytest.mark.asyncio
    async def test_escape_returns_to_overview(self, history_jobs):
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, tui.OverviewScreen)

    @pytest.mark.asyncio
    async def test_drill_all_the_way_to_a_job(self, history_jobs):
        app = make_app(history_jobs, no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, tui.JobScreen)

    @pytest.mark.asyncio
    async def test_nodes_screen(self, history_jobs):
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            assert isinstance(app.screen, tui.NodesScreen)

    @pytest.mark.asyncio
    async def test_patterns_screen(self, history_jobs):
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            assert isinstance(app.screen, tui.PatternsScreen)

    @pytest.mark.asyncio
    async def test_all_jobs_screen(self, history_jobs):
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            assert isinstance(app.screen, tui.JobListScreen)

    @pytest.mark.asyncio
    async def test_help_screen(self, history_jobs):
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            assert isinstance(app.screen, tui.HelpScreen)


class TestOverviewControls:
    @pytest.mark.asyncio
    async def test_filter_cycles(self, history_jobs):
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            start = app.screen.filter_mode
            await pilot.press("f")
            await pilot.pause()
            assert app.screen.filter_mode != start

    @pytest.mark.asyncio
    async def test_sort_cycles_and_rows_survive(self, history_jobs):
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            before = len(app.screen._rows)
            await pilot.press("s")
            await pilot.pause()
            assert app.screen.sort_mode != "cost"
            assert len(app.screen._rows) == before

    @pytest.mark.asyncio
    async def test_every_sort_mode_renders(self, history_jobs):
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            for _ in range(6):
                await pilot.press("s")
                await pilot.pause()
            assert isinstance(app.screen, tui.OverviewScreen)

    @pytest.mark.asyncio
    async def test_every_filter_mode_renders(self, history_jobs):
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            for _ in range(4):
                await pilot.press("f")
                await pilot.pause()
            assert isinstance(app.screen, tui.OverviewScreen)


class TestNodesScreenControls:
    @pytest.mark.asyncio
    async def test_metric_and_control_toggle(self, history_jobs):
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause()
            assert app.screen.metric == "failure"
            await pilot.press("c")
            await pilot.pause()
            assert app.screen.controlled is False

    @pytest.mark.asyncio
    async def test_a_withheld_interval_is_explained_on_screen(self):
        """The dashboard shows the same CI column as the report, so it needs the same
        sentence when the correction withholds a verdict -- and this is the branch
        that only paints on a history where that actually happens."""
        import random

        from slurmpast.model import Job
        from slurmpast.nodes import node_table

        rng = random.Random(4242)
        jobs = []
        for node in range(20):
            for _ in range(30):
                jobs.append(
                    Job(
                        job_id="%d" % len(jobs),
                        name="w",
                        node_list="node%03d" % node,
                        elapsed=600.0,
                        timelimit=3600.0,
                        state="FAILED" if rng.random() < 0.20 else "COMPLETED",
                    )
                )
        assert node_table(jobs, workload="w")["held_back"], "seed no longer exercises the note"

        app = make_app(jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            await pilot.press("m")  # the failure metric, which is what these carry
            await pilot.pause()
            assert isinstance(app.screen, tui.NodesScreen)
            flat = " ".join(app.screen.exclude_text.plain.split())
        assert "not yet evidence" in flat, flat
        assert "20 nodes were tested" in flat


class TestRowJump:
    def test_single_digit(self):
        jump = tui._RowJump()
        assert jump.push("3", 50) == 3

    def test_two_digits_accumulate(self):
        """ "12" must reach row 12, not row 1 then row 2."""
        jump = tui._RowJump()
        assert jump.push("1", 50) == 1
        assert jump.push("2", 50) == 12

    def test_commits_when_no_longer_number_possible(self):
        jump = tui._RowJump()
        jump.push("9", 12)  # 90+ impossible with 12 rows -> buffer clears
        assert jump.push("1", 12) == 1

    def test_out_of_range_restarts(self):
        jump = tui._RowJump()
        assert jump.push("9", 5) is None or jump.push("9", 5) is None

    def test_clear_resets(self):
        jump = tui._RowJump()
        jump.push("1", 50)
        jump.clear()
        assert jump.push("2", 50) == 2

    def test_a_non_digit_key_ends_the_pending_jump(self):
        """The buffer used to outlive the jump: press 3 to reach row 3, navigate
        away, press 7 later and the accumulated "37" landed on a row neither key
        asked for. `clear` existed and nothing called it."""
        jump = tui._RowJump()
        assert jump.push("3", 60) == 3
        jump.on_key_pressed("down")
        assert jump.push("7", 60) == 7

    def test_consecutive_digits_still_accumulate(self):
        jump = tui._RowJump()
        assert jump.push("1", 60) == 1
        jump.on_key_pressed("2")  # a digit must NOT reset the buffer
        assert jump.push("2", 60) == 12

    @pytest.mark.asyncio
    async def test_an_arrow_between_digits_does_not_accumulate_in_the_app(self, history_jobs):
        app = make_app(history_jobs, no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.screen
            await pilot.press("1")
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            assert screen._jump._buffer == ""


class TestEscapeCancelsSearch:
    """Escape is the universal "cancel this". On the overview it was bound to
    Quit and the search Input does not consume it, so cancelling a search ENDED
    THE SESSION; on a job list it popped the screen. Enter commits the filter,
    escape discards it -- and neither should lose your place."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("open_keys,table", [([], "#groups"), (["a"], "#jobs")])
    async def test_escape_clears_the_search_and_keeps_the_app(self, history_jobs, open_keys, table):
        from textual.widgets import DataTable

        app = make_app(history_jobs, no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            for key in open_keys:
                await pilot.press(key)
                await pilot.pause()
            before = app.screen.query_one(table, DataTable).row_count
            await pilot.press("slash")
            await pilot.pause()
            for char in "cot":
                await pilot.press(char)
            await settle_search(pilot)
            assert app.screen.query_one(table, DataTable).row_count < before
            await pilot.press("escape")
            await pilot.pause()
            assert app.is_running, "escape cancelled the search by killing the app"
            assert app.screen.query_one(table, DataTable).row_count == before
            assert app.screen.search_text == ""
            assert isinstance(app.screen.focused, DataTable)

    @pytest.mark.asyncio
    async def test_escape_with_no_search_still_backs_out(self, history_jobs):
        """Cancelling a search must not cost escape its normal job."""
        app = make_app(history_jobs, no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            assert isinstance(app.screen, tui.JobListScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, tui.OverviewScreen)

    @pytest.mark.asyncio
    async def test_enter_commits_the_search_instead(self, history_jobs):
        from textual.widgets import DataTable

        app = make_app(history_jobs, no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            for char in "cot":
                await pilot.press(char)
            await settle_search(pilot)
            narrowed = app.screen.query_one("#groups", DataTable).row_count
            await pilot.press("enter")
            await pilot.pause()
            assert app.screen.query_one("#groups", DataTable).row_count == narrowed
            assert app.screen.search_text == "cot"


class TestRequeryKeepsTheAppAlive:
    """`r` popped screens "while deeper than one", but the overview is itself a
    pushed screen sitting on the App's own default Screen -- so it popped the
    overview too and left a blank screen that swallowed every later key. Reported
    as "some of these options can crash the program and are useless"."""

    def _app(self, jobs, **kwargs):
        return tui.SlurmpastApp(
            lambda since=None: list(jobs), window="last 7 days", no_logs=True, **kwargs
        )

    @pytest.mark.asyncio
    async def test_reload_lands_back_on_the_overview(self, history_jobs):
        app = self._app(history_jobs, since="now-7days")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("r")
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, tui.OverviewScreen)
            assert app.history is not None

    @pytest.mark.asyncio
    async def test_the_app_still_responds_after_a_reload(self, history_jobs):
        """The blank screen was not just empty -- it had no bindings, so the app
        was unusable from that point on."""
        app = self._app(history_jobs, since="now-7days")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("r")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            assert isinstance(app.screen, tui.JobListScreen)

    @pytest.mark.asyncio
    async def test_a_drilled_in_screen_is_popped_but_not_the_overview(self, history_jobs):
        app = self._app(history_jobs, since="now-7days")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("n")  # NodesScreen on top
            await pilot.pause()
            assert isinstance(app.screen, tui.NodesScreen)
            await pilot.press("w")  # app-level binding, works from any screen
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, tui.OverviewScreen)
            assert app.history is not None

    @pytest.mark.asyncio
    async def test_cycling_the_window_leaves_a_usable_overview(self, history_jobs):
        app = self._app(history_jobs, since="now-7days")
        async with app.run_test() as pilot:
            await pilot.pause()
            for _ in range(3):
                await pilot.press("w")
                await pilot.pause()
                await pilot.pause()
                assert isinstance(app.screen, tui.OverviewScreen)
                assert app.screen.query_one("#groups").row_count > 0


class TestWindowCycling:
    """The window was fixed by -S at launch, so "what about last month?" meant
    quitting and starting again."""

    def _spy_app(self, jobs):
        """An app whose loader takes a window, and records which it was asked for."""
        seen = []

        def load(since=None):
            seen.append(since)
            return list(jobs)

        app = tui.SlurmpastApp(load, window="last 7 days", no_logs=True, since="now-7days")
        return app, seen

    def test_only_specs_sacct_accepts_are_offered(self):
        """Verified against Slurm 20.11.8: `-S now-6months` is "Invalid time
        specification". Only days and weeks survive."""
        for spec in tui.WINDOWS:
            assert spec.startswith("now-")
            assert spec.endswith(("days", "day", "weeks", "week", "hours"))

    def test_the_labels_come_from_the_shared_humanizer(self):
        from slurmpast.duration import humanize_window

        for spec in tui.WINDOWS:
            assert "now-" not in humanize_window(spec)

    @pytest.mark.asyncio
    async def test_w_requeries_with_the_next_window(self, history_jobs):
        app, seen = self._spy_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert seen == ["now-7days"]
            await pilot.press("w")
            await pilot.pause()
            await pilot.pause()
            assert seen[-1] == "now-30days"
            assert app.window == "last 30 days"

    @pytest.mark.asyncio
    async def test_the_cycle_comes_back_round(self, history_jobs):
        app, _seen = self._spy_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            for _ in range(len(tui.WINDOWS)):
                await pilot.press("w")
                await pilot.pause()
            assert app.window == "last 7 days"

    @pytest.mark.asyncio
    async def test_a_launch_window_outside_the_presets_stays_in_the_cycle(self, history_jobs):
        app = tui.SlurmpastApp(
            lambda since=None: list(history_jobs),
            window="since 2026-01-01",
            no_logs=True,
            since="2026-01-01",
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            for _ in range(len(tui.WINDOWS) + 1):
                await pilot.press("w")
                await pilot.pause()
            assert app._since == "2026-01-01"

    @pytest.mark.asyncio
    async def test_an_empty_window_is_backed_out_of_not_fatal(self, history_jobs):
        """Cycling into a window with no jobs must not exit the app -- the reader
        still has the data they had a keypress ago."""
        calls = []

        def load(since=None):
            calls.append(since)
            if len(calls) > 1:
                raise RuntimeError("no jobs for youzhi since %s" % since)
            return list(history_jobs)

        app = tui.SlurmpastApp(load, window="last 7 days", no_logs=True, since="now-7days")
        async with app.run_test() as pilot:
            await pilot.pause()
            before = app.history
            await pilot.press("w")
            await pilot.pause()
            await pilot.pause()
            assert app.load_error is None
            assert app.history is before
            assert app.window == "last 7 days"
            assert app._since == "now-7days"

    @pytest.mark.asyncio
    async def test_a_zero_argument_loader_disables_cycling(self, history_jobs):
        """--demo and the tests pass one; there is no window over synthetic data."""
        app = make_app(history_jobs, no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app._can_requery is False
            await pilot.press("w")
            await pilot.pause()
            assert app.window == "test window"
            assert app.load_error is None


class TestPathElision:
    """A log path is shown so the reader knows WHICH log was read."""

    def test_a_short_path_is_untouched(self):
        assert tui._elide("/home/y/slurm-1.out") == "/home/y/slurm-1.out"

    def test_the_leading_directory_survives(self):
        """`"/a/b".partition("/")` yields an empty head, so every absolute path
        collapsed to a bare "/…/slurm-123.out" -- the directory, which was the
        only reason to print a path at all, was thrown away."""
        long_path = "/scratch/midway3/youzhi/runs/cot-exp/logs/slurm-51170455.out"
        elided = tui._elide(long_path)
        assert elided.startswith("/scratch/")
        assert elided.endswith("slurm-51170455.out")
        assert elided != "/…/slurm-51170455.out"

    def test_a_relative_path_keeps_its_first_component(self):
        elided = tui._elide("runs/deep/deeper/evenmore/andmore/slurm-1.out")
        assert elided.startswith("runs/")
        assert elided.endswith("slurm-1.out")

    def test_a_single_long_component_is_left_alone(self):
        name = "s" * 80
        assert tui._elide(name) == name


class TestAsciiMode:
    @pytest.mark.asyncio
    async def test_ascii_mode_boots(self, history_jobs):
        app = make_app(history_jobs, ascii_mode=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.ascii_mode is True
            assert isinstance(app.screen, tui.OverviewScreen)


class TestDemoMode:
    """`--demo` has to work with no Slurm at all: it is how a new user tries the
    tool, and it is what the VHS tape records."""

    def test_demo_history_parses(self):
        from slurmpast.demo import history

        jobs = history()
        assert len(jobs) > 40
        assert all(j.job_id for j in jobs)

    def test_demo_contains_the_shapes_the_tool_looks_for(self):
        from slurmpast.demo import history
        from slurmpast.diagnose import diagnose
        from slurmpast.index import History

        h = History(history())
        codes = {f.code for f in h.patterns}
        assert "repeat-failure" in codes
        assert "memory-search" in codes
        per_job = set()
        for job in h.usable_jobs:
            per_job |= {f.code for f in diagnose(job).findings}
        assert {
            "timeout-hang",
            "host-oom",
            "system-cpu-heavy",
            "straggler",
            "paging",
            "noop-allocation",
        } <= per_job

    def test_demo_includes_healthy_jobs_that_draw_nothing(self):
        """Restraint must be visible in the demo, not just claimed."""
        from slurmpast.demo import history
        from slurmpast.diagnose import diagnose

        clean = [j for j in history() if j.name == "midtrain"]
        assert clean
        for job in clean:
            assert not [f for f in diagnose(job).findings if f.severity == "critical"]

    def test_demo_exercises_the_name_rollup(self):
        from slurmpast.demo import history
        from slurmpast.index import build_groups

        names = {g.name for g in build_groups(history())}
        assert "att-speed-#" in names

    @pytest.mark.asyncio
    async def test_dashboard_boots_on_demo_data(self):
        from slurmpast.demo import history

        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, tui.OverviewScreen)
            assert len(app.screen._rows) > 5


class TestLongPathsDoNotBreakTheLayout:
    """A 118-character workdir wrapped to column 0, leaving the label looking
    empty with an orphaned line of path beneath it."""

    # Longer than the line has room for at the 118-wide size used below, which is
    # the condition eliding exists for -- not merely longer than some constant.
    LONG_DIR = (
        "/project/rcc/youzhi/.cache/tmp/claude-940740146/-home-youzhi-ArgonneAI"
        "/deeper/still/and/deeper/again/until/it/cannot/fit"
    )

    def _job_with_a_long_workdir(self, history_jobs):
        long_dir = self.LONG_DIR
        assert len(long_dir) > 118 - (4 + 16 + 1) - tui._SCROLLBAR
        return history_jobs[0]._replace(work_dir=long_dir), long_dir

    @pytest.mark.asyncio
    async def test_a_long_path_is_elided_inline(self, history_jobs):
        job, long_dir = self._job_with_a_long_workdir(history_jobs)
        app = make_app(history_jobs, no_logs=True)
        async with app.run_test(size=(118, 44)) as pilot:
            await pilot.pause()
            app.push_screen(tui.JobScreen(job))
            await pilot.pause()
            body = "\n".join(
                "".join(s.text for s in strip) for strip in app.screen._compositor.render_strips()
            )
            row = [ln for ln in body.splitlines() if "workdir" in ln][0]
            assert "…" in row, row
            assert long_dir not in row
            # Elided, not emptied: both ends of the path survive.
            assert "/project" in row and "fit" in row

    @pytest.mark.asyncio
    async def test_p_reveals_the_whole_path(self, history_jobs):
        job, long_dir = self._job_with_a_long_workdir(history_jobs)
        app = make_app(history_jobs, no_logs=True)
        async with app.run_test(size=(118, 44)) as pilot:
            await pilot.pause()
            app.push_screen(tui.JobScreen(job))
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            body = "\n".join(
                "".join(s.text for s in strip) for strip in app.screen._compositor.render_strips()
            )
            assert long_dir.split("/")[-1] in body

    def test_plain_output_never_elides_a_path(self, history_jobs):
        """A path you cannot copy whole is no use in a ticket."""
        from slurmpast.report import Style, render_job

        job, long_dir = self._job_with_a_long_workdir(history_jobs)
        text, _ = render_job(job, style=Style(enabled=False))
        assert long_dir in text


class TestNavigatingWhileSearching:
    """Reported as "i can never move the highlightor up or down at all". An Input
    swallows the arrows -- left/right move its caret, up/down do nothing -- so once
    a query was typed the highlight was stuck until enter, with nothing saying so.
    Type to filter, arrow to choose, enter to commit."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("open_keys,table", [([], "#groups"), (["a"], "#jobs")])
    async def test_arrows_move_the_cursor_from_the_search_box(self, history_jobs, open_keys, table):
        from textual.widgets import DataTable, Input

        app = make_app(history_jobs, no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            for key in open_keys:
                await pilot.press(key)
                await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            assert isinstance(app.screen.focused, Input), "search box should have focus"
            grid = app.screen.query_one(table, DataTable)
            assert grid.row_count > 2, "need rows to move between"
            await pilot.press("down")
            await pilot.pause()
            assert grid.cursor_row == 1
            await pilot.press("down")
            await pilot.pause()
            assert grid.cursor_row == 2
            await pilot.press("up")
            await pilot.pause()
            assert grid.cursor_row == 1
            # And focus never left the box, so typing continues to filter.
            assert isinstance(app.screen.focused, Input)

    @pytest.mark.asyncio
    async def test_home_and_end_reach_both_ends(self, history_jobs):
        from textual.widgets import DataTable

        app = make_app(history_jobs, no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            grid = app.screen.query_one("#groups", DataTable)
            await pilot.press("end")
            await pilot.pause()
            assert grid.cursor_row == grid.row_count - 1
            await pilot.press("home")
            await pilot.pause()
            assert grid.cursor_row == 0

    @pytest.mark.asyncio
    async def test_typing_still_filters(self, history_jobs):
        """The steering must not eat the printable keys."""
        from textual.widgets import DataTable

        app = make_app(history_jobs, no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            before = app.screen.query_one("#groups", DataTable).row_count
            await pilot.press("slash")
            await pilot.pause()
            for char in "cot":
                await pilot.press(char)
            await settle_search(pilot)
            assert app.screen.search_text == "cot"
            assert app.screen.query_one("#groups", DataTable).row_count < before


class TestJobRowsHaveNoSelectionLookalike:
    @pytest.mark.asyncio
    async def test_no_dot_leads_a_job_row(self, history_jobs):
        """A filled circle on every row was read as "all the entries are
        selected", and it duplicated the STATE column beside it."""
        from textual.widgets import DataTable

        app = make_app(history_jobs, no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            grid = app.screen.query_one("#jobs", DataTable)
            for r in range(min(5, grid.row_count)):
                assert "●" not in str(grid.get_row_at(r)[0])

    @pytest.mark.asyncio
    async def test_the_overview_keeps_its_dot(self, history_jobs):
        """There it carries group severity, which has no column of its own."""
        from textual.widgets import DataTable

        app = make_app(history_jobs, no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            grid = app.screen.query_one("#groups", DataTable)
            assert any("●" in str(grid.get_row_at(r)[0]) for r in range(grid.row_count))


class TestLogResolutionIsCrossChecked:
    """A job screen must not be shown a log that belongs to a different run.

    Resolving one job at a time cannot see the conflict: measured on a real
    history, 51 timing matches pointed at a file another job also claimed. The
    dashboard therefore resolves the whole history in a worker and reads from that.
    """

    @pytest.mark.asyncio
    async def test_no_logs_asks_the_filesystem_nothing(self, history_jobs, monkeypatch):
        called = []
        monkeypatch.setattr(tui, "assign_logs", lambda *a, **k: called.append(1) or {})
        app = make_app(history_jobs, no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert called == []
            assert app.log_for(history_jobs[0]) == (None, None, False)

    @pytest.mark.asyncio
    async def test_the_whole_history_assignment_is_preferred(self, history_jobs, monkeypatch):
        job = history_jobs[0]
        monkeypatch.setattr(tui, "assign_logs", lambda *a, **k: {job.job_id: ("/x/mine.err", True)})
        monkeypatch.setattr(tui, "read_tail", lambda path, **k: "tail of %s" % path)
        monkeypatch.setattr(tui, "load_for", lambda *a, **k: pytest.fail("should not fall back"))
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app._log_map is not None, "the worker should have landed"
            assert app.log_for(job) == ("/x/mine.err", "tail of /x/mine.err", True)

    @pytest.mark.asyncio
    async def test_a_job_the_assignment_withheld_shows_nothing(self, history_jobs, monkeypatch):
        """The point of the cross-check: a run whose only candidate belonged to a
        sibling gets None, not the sibling's log."""
        job = history_jobs[0]
        monkeypatch.setattr(tui, "assign_logs", lambda *a, **k: {job.job_id: (None, False)})
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.log_for(job) == (None, None, False)

    @pytest.mark.asyncio
    async def test_it_falls_back_before_the_worker_lands(self, history_jobs, monkeypatch):
        monkeypatch.setattr(tui, "load_for", lambda *a, **k: ("/x/fallback.err", "text", True))
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            app._log_map = None  # as it is for the first keypress after a load
            assert app.log_for(history_jobs[0]) == ("/x/fallback.err", "text", True)

    @pytest.mark.asyncio
    async def test_a_failed_scan_does_not_take_the_dashboard_down(self, history_jobs, monkeypatch):
        def boom(*a, **k):
            raise OSError("permission denied")

        monkeypatch.setattr(tui, "assign_logs", boom)
        monkeypatch.setattr(tui, "load_for", lambda *a, **k: (None, None, False))
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.history is not None
            assert app._log_map is None


class TestPathsGetTheRoomTheLineHas:
    """Reported: a 47-character log path shown as `/home/…/145-train.err` on a
    150-column terminal. Both budgets were constants -- and the log line used
    _elide's default 46 while the workdir above it used 62, so the path a reader
    most wants to copy was cut shortest of anything on the screen.
    """

    LOG = "/home/youzhi/ArgonneAI-4.0/report/145-train.err"  # 47 characters

    def _screen_text(self, app):
        return "\n".join(
            "".join(s.text for s in strip) for strip in app.screen._compositor.render_strips()
        )

    @pytest.mark.asyncio
    async def test_a_log_path_that_fits_is_shown_whole(self, history_jobs, monkeypatch):
        job = history_jobs[0]
        monkeypatch.setattr(tui, "assign_logs", lambda *a, **k: {job.job_id: (self.LOG, True)})
        monkeypatch.setattr(tui, "read_tail", lambda *a, **k: "text")
        app = make_app(history_jobs)
        async with app.run_test(size=(150, 44)) as pilot:
            await pilot.pause()
            app.push_screen(tui.JobScreen(history_jobs[0]))
            await pilot.pause()
            body = self._screen_text(app)
            assert self.LOG in body, "47 chars on a 150-wide terminal must not be elided"
            assert "/home/…/" not in body

    @pytest.mark.asyncio
    async def test_it_is_still_elided_when_the_line_is_genuinely_too_narrow(
        self, history_jobs, monkeypatch
    ):
        job = history_jobs[0]
        monkeypatch.setattr(tui, "assign_logs", lambda *a, **k: {job.job_id: (self.LOG, True)})
        monkeypatch.setattr(tui, "read_tail", lambda *a, **k: "text")
        app = make_app(history_jobs)
        async with app.run_test(size=(40, 44)) as pilot:
            await pilot.pause()
            app.push_screen(tui.JobScreen(history_jobs[0]))
            await pilot.pause()
            body = self._screen_text(app)
            assert self.LOG not in body
            assert "145-train.err" in body, "the filename is the part that must survive"

    def test_the_budget_never_drops_below_the_floor(self):
        """Eliding below this hides the filename, which is the one part that has to
        survive; a two-column terminal is not worth degrading further for."""
        assert len("…/145-train.err") <= tui._MIN_PATH_WIDTH

    def test_the_log_line_is_no_longer_the_tightest_budget_on_the_screen(self):
        """It has a 7-character prefix against the workdir row's 21, so it has MORE
        room, not sixteen cells less."""
        from slurmpast import render

        log_prefix = len("  log  ")
        cell_prefix = 4 + render.PAIR_LABEL_WIDTH + 1
        assert log_prefix < cell_prefix


class TestTheBlockIsCentred:
    """fit_columns leaves width no column needs UNUSED -- stretching a table into
    empty space makes canyons between its columns -- and the leftover then sat
    entirely on the right, which reads as the layout having abandoned half the
    terminal. Centring spends it evenly.
    """

    async def _probe(self, jobs, width, keys=(), table="#groups"):
        """Measure inside the running app: the DOM is torn down on exit."""
        from textual.widgets import DataTable, Footer, Header

        app = make_app(jobs, no_logs=True)
        async with app.run_test(size=(width, 30)) as pilot:
            await pilot.pause()
            for key in keys:
                await pilot.press(key)
                await pilot.pause()
            await pilot.pause()
            screen = app.screen
            content = screen.query_one("#content")
            found = screen.query(DataTable)
            return {
                "name": type(screen).__name__,
                "width": content.size.width,
                "x": content.region.x,
                "columns": len(found.first().columns) if found else 0,
                "header": screen.query_one(Header).size.width,
                "footer": screen.query_one(Footer).size.width,
            }

    @pytest.mark.asyncio
    async def test_the_block_uses_the_terminal(self, history_jobs):
        """Centring came first and was not enough on its own: the columns stopped
        at the width their content needed, so a 150-column terminal held a 100-cell
        table with 25 cells of nothing either side. It now spends the leftover."""
        got = await self._probe(history_jobs, 150)
        assert got["width"] >= 150 - 2, got["width"]

    @pytest.mark.asyncio
    async def test_the_margins_are_even_when_there_are_any(self, history_jobs):
        """Filling makes the margins zero on a normal terminal. Centring still
        matters where the columns cannot absorb the width -- a spec whose every
        column is capped -- and it must stay symmetric there."""
        got = await self._probe(history_jobs, 150)
        left, right = got["x"], 150 - got["width"] - got["x"]
        assert abs(left - right) <= 1, (left, right)

    @pytest.mark.asyncio
    async def test_the_columns_still_track_the_terminal(self, history_jobs):
        """The trap this refactor had to avoid. The table now sits in a container
        sized to the columns it picked, so sizing the columns from the TABLE's own
        width would be circular and would freeze the column set at the default on
        every terminal."""
        wide = await self._probe(history_jobs, 150)
        narrow = await self._probe(history_jobs, 60)
        assert wide["columns"] > narrow["columns"], (wide["columns"], narrow["columns"])

    @pytest.mark.asyncio
    async def test_it_never_asks_for_more_width_than_the_terminal(self, history_jobs):
        """The never-dropped columns have a floor, so on a narrow terminal the table
        wants more room than exists. Asking for it hands the Screen a horizontal
        scrollbar where it used to simply clip."""
        for term in (40, 60, 80):
            got = await self._probe(history_jobs, term)
            assert got["width"] <= term, (term, got["width"])
            assert got["x"] == (term - got["width"]) // 2

    @pytest.mark.asyncio
    async def test_the_bars_still_span_the_terminal(self, history_jobs):
        """A centred block, not a centred application: a header and footer stopping
        short of the edges would look broken."""
        got = await self._probe(history_jobs, 150)
        assert got["header"] == 150
        assert got["footer"] == 150

    @pytest.mark.asyncio
    async def test_the_node_screen_behaves_like_the_others(self, history_jobs):
        """Its columns used to be hardcoded at the widget, so it was the one screen
        that stayed narrow while its neighbours filled -- which looks like a broken
        layout rather than a deliberate one. It goes through fit_columns now."""
        got = await self._probe(history_jobs, 150, keys=("n",))
        assert got["name"] == "NodesScreen"
        assert got["width"] >= 150 - 2, got["width"]

    @pytest.mark.asyncio
    async def test_the_node_screen_drops_columns_when_narrow(self, history_jobs):
        """And the reason keying its cells by label matters: a fixed tuple of five
        cells raises the moment one is dropped."""
        wide = await self._probe(history_jobs, 150, keys=("n",))
        narrow = await self._probe(history_jobs, 55, keys=("n",))
        assert narrow["columns"] < wide["columns"], (narrow["columns"], wide["columns"])


class TestTheFooterSaysWhatThingsAre:
    """Asked of the footer: "what is patterns and what is window? why all jobs
    deserves a button?" Two labels named the implementation rather than the answer,
    and one action was taking a slot it had not earned.
    """

    async def _footer(self, jobs, width):
        app = make_app(jobs, no_logs=True)
        async with app.run_test(size=(width, 20)) as pilot:
            await pilot.pause()
            strips = app.screen._compositor.render_strips()
            return "".join(s.text for s in strips[-1])

    @pytest.mark.asyncio
    async def test_the_labels_name_the_answer_not_the_screen(self, history_jobs):
        text = await self._footer(history_jobs, 150)
        assert "Repeat failures" in text, "'Patterns' named the code, not the finding"
        assert "Time range" in text, "'Window' is sacct's word, not a reader's"
        assert "Patterns" not in text and "Window" not in text

    @pytest.mark.asyncio
    async def test_every_shown_binding_actually_fits(self, history_jobs):
        """Textual truncates the tail, so a label that grows costs a later one its
        place silently: "Copy row" being shown pushed `r Reload` and `w Time range`
        off the end at 100 columns. 100 is the width to hold, being the narrowest
        anyone reads a 13-column table in."""
        text = await self._footer(history_jobs, 100)
        for label in ("Quit", "Search", "Filter", "Sort", "Nodes", "Repeat failures", "Reload"):
            assert label in text, label

    @pytest.mark.asyncio
    async def test_the_niche_views_keep_their_keys_without_a_slot(self, history_jobs):
        """`a` and `y` are off the footer, not gone: the overview groups by workload
        because a flat list of thousands of jobs is not an interface, so the flat
        list is an escape hatch rather than a headline action."""
        text = await self._footer(history_jobs, 150)
        assert "All jobs" not in text and "Copy row" not in text
        app = make_app(history_jobs, no_logs=True)
        async with app.run_test(size=(150, 20)) as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            assert isinstance(app.screen, tui.JobListScreen)

    @pytest.mark.asyncio
    async def test_help_explains_the_ones_the_footer_cannot(self, history_jobs):
        app = make_app(history_jobs, no_logs=True)
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            text = "".join(
                "".join(s.text for s in st) for st in app.screen._compositor.render_strips()
            )
            assert "what keeps failing" in text
            assert "how far back to look" in text
            assert "every job in one flat list" in text


class TestChangingTheTimeRangeIsNoticeable:
    """Reported: "when pressing `w` to switch the time frames, the only update is
    'slurmpast — last 12 weeks'. users have a hard time noticing that."

    The row you were looking at usually survives the requery and the counts move by
    a few, so the one phrase that changed sat in the title bar where nobody looks.
    """

    def _loader(self, jobs):
        def load(since=None):
            return jobs if since == "now-7days" else jobs[:20]

        return load

    def _app(self, jobs):
        return tui.SlurmpastApp(
            self._loader(jobs), window="last 7 days", no_logs=True, since="now-7days"
        )

    @pytest.mark.asyncio
    async def test_it_announces_the_new_range(self, history_jobs):
        app = self._app(history_jobs)
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()
            messages = [n.message for n in app._notifications]
            assert any("time range: last 30 days" in m for m in messages), messages

    @pytest.mark.asyncio
    async def test_the_toast_names_the_whole_cycle(self, history_jobs):
        """So `w` is discoverable as a cycle rather than a mystery step."""
        app = self._app(history_jobs)
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()
            message = next(n.message for n in app._notifications)
            assert "last 24 hours" in message and "last 52 weeks" in message

    @pytest.mark.asyncio
    async def test_the_range_is_on_screen_after_the_toast_goes(self, history_jobs):
        """A toast is transient. The body has to carry it too, or the screen stops
        saying what it is showing."""
        app = self._app(history_jobs)
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            before = app.screen.summary_text.plain
            assert before.startswith("last 7 days")
            await pilot.press("w")
            await pilot.pause()
            await pilot.pause()
            after = app.screen.summary_text.plain
            assert after.startswith("last 30 days"), after
            assert after != before

    @pytest.mark.asyncio
    async def test_the_range_is_styled_apart_from_the_counts(self, history_jobs):
        """Asked for: "you might need to have different colors to denote the changed
        parts." The range carries the accent; the counts stay ink."""
        app = self._app(history_jobs)
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            summary = app.screen.summary_text
            first = summary.spans[0]
            assert summary.plain[first.start : first.end] == "last 7 days"
            assert theme.ACCENT in str(first.style)

    @pytest.mark.asyncio
    async def test_a_fixed_window_still_says_why_nothing_happened(self, history_jobs):
        app = make_app(history_jobs, no_logs=True)
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()
            assert any("window is fixed" in n.message for n in app._notifications)


class TestTheWorkloadHeaderStaysShort:
    """Reported: "can you tell me why the top of the ui needs all the useless info
    like that? it's verbose and fucking annoying" -- of

        software · test · 132 jobs · 1 of them never computed · 1 cancelled
        · 1 unterminated, excluded

    Three separate ones out of 132, 0.8% each, taking three quarters of the line.
    """

    def _screen(self, jobs, group_jobs, excluded=0):
        from slurmpast.index import build_groups

        group = build_groups(group_jobs)[0]
        if excluded:
            group = group._replace(excluded=excluded)
        return group

    async def _summary(self, jobs, group, width=150):
        app = make_app(jobs, no_logs=True)
        async with app.run_test(size=(width, 24)) as pilot:
            await pilot.pause()
            app.push_screen(tui.WorkloadScreen(group))
            await pilot.pause()
            await pilot.pause()
            return app.screen.summary_text.plain

    @pytest.mark.asyncio
    async def test_one_stray_run_in_a_hundred_is_not_a_headline(self, healthy_job):
        many = [healthy_job._replace(job_id=str(4000 + i)) for i in range(100)]
        many[0] = many[0]._replace(state="CANCELLED by 1")
        group = self._screen(many, many, excluded=1)
        text = await self._summary(many, group)
        assert "100 jobs" in text
        assert "cancelled" not in text, text
        assert "unterminated" not in text, text

    @pytest.mark.asyncio
    async def test_a_material_share_still_earns_its_clause(self, healthy_job):
        """5 of 15 cancelled is a third of the workload, and is the answer to "15
        total but 10 success and 2 flagged, where are the rest 3?"."""
        some = [healthy_job._replace(job_id=str(4200 + i)) for i in range(15)]
        for i in range(5):
            some[i] = some[i]._replace(state="CANCELLED by 1")
        group = self._screen(some, some)
        text = await self._summary(some, group)
        assert "5 cancelled" in text, text

    @pytest.mark.asyncio
    async def test_the_threshold_is_a_share_not_a_count(self, healthy_job):
        from slurmpast.tui import QUALIFIER_SHARE

        assert 0 < QUALIFIER_SHARE < 1


class TestTheAdviceBasisIsNotCutOff:
    """It was wrapped to 84 cells and then sliced to the FIRST line, so a basis of
    any length lost its ending: "the rest is room to" reads as the app breaking
    rather than as a sentence that did not fit.
    """

    @pytest.mark.asyncio
    async def test_the_whole_sentence_survives(self, history_jobs):
        from slurmpast.index import build_groups
        from slurmpast.sizing import recommend

        group = build_groups(history_jobs)[0]
        app = make_app(history_jobs, no_logs=True)
        async with app.run_test(size=(150, 30)) as pilot:
            await pilot.pause()
            app.push_screen(tui.WorkloadScreen(group))
            await pilot.pause()
            await pilot.pause()
            body = "".join(
                "".join(s.text for s in st) for st in app.screen._compositor.render_strips()
            )
        for advice in recommend(group.jobs):
            if not advice.actionable:
                continue
            # The last few words are what a first-line slice threw away.
            assert advice.basis.rstrip(".").split()[-1] in body, advice.basis


class TestNothingInTheLoadWorkerTakesTheAppDown:
    """The except clause promises errors are "surfaced in the UI, never swallowed".

    `History(...)` was built after it, and Textual's `run_worker` defaults to
    `exit_on_error=True` -- so anything raised there reached
    `App._handle_exception`, which always exits, and the dashboard died with a raw
    traceback while `load_error` stayed None. `exit_on_error=False` would be the
    wrong fix: nothing else calls `_loaded`, so the UI would sit on "loading…"
    for ever.
    """

    @pytest.mark.asyncio
    async def test_a_failure_building_the_history_is_reported(self, monkeypatch, history_jobs):
        def boom(*args, **kwargs):
            raise ValueError("grouping exploded")

        monkeypatch.setattr(tui, "History", boom)
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
        assert app.load_error is not None
        assert "grouping exploded" in app.load_error

    @pytest.mark.asyncio
    async def test_a_failure_finding_logs_leaves_the_dashboard_up(self, monkeypatch, history_jobs):
        """`except OSError` did not deliver its own comment's guarantee.

        A log search walks directories and expands filename patterns from
        user-supplied strings; it is the most speculative thing here, and logs are
        an enhancement to a screen that is useful without them.
        """

        def boom(*args, **kwargs):
            raise ValueError("log walk exploded")

        monkeypatch.setattr(tui, "assign_logs", boom)
        app = make_app(history_jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.history is not None
            assert isinstance(app.screen, tui.OverviewScreen)
        assert app.load_error is None


class TestReloadSurvivesATransientFailure:
    """`r` did not snapshot `_previous` before re-querying, so it took the exit
    path in `_loaded` that `w` degrades gracefully out of.

    `_requery` clears `self.history` first, and a successful load clears
    `_previous`, so after any normal session `r` plus a slurmdbd blip or a query
    timeout tore the dashboard down with the history already discarded -- while
    the identical failure on `w` toasted and stayed put. `_loaded`'s own comment
    gives the reason: "Backing out beats exiting: they still have the data they
    had."
    """

    @staticmethod
    def _flaky(jobs):
        """A loader that works once, then raises the way slurmdbd does."""
        state = {"calls": 0}

        def load(*_args):
            state["calls"] += 1
            if state["calls"] > 1:
                raise RuntimeError("slurm_load_jobs error: Socket timed out")
            return list(jobs)

        return load

    @pytest.mark.asyncio
    async def test_the_app_stays_up_and_keeps_its_data(self, history_jobs):
        app = tui.SlurmpastApp(self._flaky(history_jobs), window="test window")
        async with app.run_test() as pilot:
            await pilot.pause()
            before = app.history
            assert before is not None
            await pilot.press("r")
            await pilot.pause()
            assert app.is_running, "a transient query failure must not exit the app"
            assert app.history is before, "the history the user had was discarded"

    @pytest.mark.asyncio
    async def test_a_first_load_that_fails_still_exits(self, history_jobs):
        """The control. With nothing to fall back to there is no data to keep, and
        exiting with the error is the right answer -- that path is unchanged."""

        def always_fails(*_args):
            raise RuntimeError("no such cluster")

        app = tui.SlurmpastApp(always_fails, window="test window")
        async with app.run_test() as pilot:
            await pilot.pause()
        assert app.load_error == "no such cluster"


class TestOnlyPathsAreElidedLikePaths:
    """`"/" in value` is not a test for a path. The `submitted as` row (SubmitLine,
    Slurm 21.08+) is a command line, and middle-eliding it threw away the
    `--output` directory on the one row that records where the output went."""

    SUBMIT_LINE = (
        "sbatch --job-name=midtrain --partition=gpu --gres=gpu:4 "
        "--output=/scratch/midway3/youzhi/logs/%x-%j.out train.sh"
    )

    def test_a_command_line_keeps_its_head(self):
        clipped = tui._clip(self.SUBMIT_LINE, 60)
        assert clipped.startswith("sbatch --job-name=midtrain")
        assert "/…/" not in clipped
        assert len(clipped) == 60

    def test_a_path_row_is_still_elided_middle_out(self):
        """The control: `workdir` is a path and keeps both ends."""
        from slurmpast.render import PATH_ROWS

        assert "workdir" in PATH_ROWS
        assert "submitted as" not in PATH_ROWS

    def test_elide_honours_its_budget(self):
        """At keep=30 this returned 122 characters, so the row soft-wrapped to
        column 0 anyway -- the only thing eliding exists to prevent."""
        path = "/scratch/midway3/youzhi/runs/cot-exp/logs/slurm-51170455.out"
        assert len(tui._elide(path, keep=30)) <= 30

    def test_the_readable_form_is_still_preferred_when_it_fits(self):
        path = "/scratch/midway3/youzhi/runs/cot-exp/logs/slurm-51170455.out"
        elided = tui._elide(path, keep=46)
        assert elided == "/scratch/…/slurm-51170455.out"


class TestProseIsWrappedToTheWidgetNotTheScreen:
    """`_prose_width` subtracted a constant `_SCROLLBAR = 2` from the *screen*
    width, and `JobScreen`'s `#body` is 96 cells inside a 100-cell screen. So a
    finding wrapped to 90 was drawn at 8 + 90 = 98, Textual soft-wrapped the last
    word to column 0, and the indent separating evidence from its heading was lost
    — which is the exact failure `_prose_width` was written to stop, surviving in
    it because the constant was guessed rather than measured.

    Reproduced on the node-history finding, whose evidence is the longest the
    dashboard draws: "midway3-0385 failed 12 of 12 placements there (100.0%, 95% CI
    75.7-100.0%) against 25.0% on every other node for cot-exp."
    """

    @staticmethod
    async def _open_a_job_with_a_long_finding(pilot, app):
        await pilot.pause()
        for key in ("f", "2", "enter", "down", "enter", "end"):
            await pilot.press(key)
            await pilot.pause()
        return app.screen

    @pytest.mark.asyncio
    @pytest.mark.parametrize("width", [70, 80, 100, 120])
    async def test_no_body_line_is_wider_than_the_body(self, width):
        from textual.widgets import Static

        from slurmpast.demo import history as demo

        app = make_app(demo(), no_logs=True)
        async with app.run_test(size=(width, 40)) as pilot:
            screen = await self._open_a_job_with_a_long_finding(pilot, app)
            body = screen.query_one("#body", Static)
            assert body.size.width, "the body must be laid out before this means anything"
            for strip in screen._compositor.render_strips():
                text = "".join(cell.text for cell in strip).rstrip()
                assert len(text) <= width, "%d cells on a %d-cell screen: %r" % (
                    len(text),
                    width,
                    text,
                )

    @pytest.mark.asyncio
    async def test_the_width_comes_from_the_body_not_the_screen(self):
        """The control on the mechanism, not just the symptom: the two numbers are
        different, and the wrap has to use the smaller one."""
        from textual.widgets import Static

        from slurmpast.demo import history as demo

        app = make_app(demo(), no_logs=True)
        async with app.run_test(size=(100, 40)) as pilot:
            screen = await self._open_a_job_with_a_long_finding(pilot, app)
            body = screen.query_one("#body", Static)
            assert body.size.width < screen.size.width, "no gap left to get wrong"
            assert tui._prose_width(screen, 8) == body.size.width - 8


class TestTextWidthNeverExceedsTheTerminal:
    """A Static can be sized to its *content* rather than to its container, and
    then reports a width wider than the terminal. Trusting it wraps text off the
    right-hand edge — which is what Textual 0.89 does with `WorkloadScreen`'s
    `#summary`, sending the banner out at 83 cells on a 70-cell screen.

    Pinned here against a stub rather than against a Textual version, so it holds
    on every release in the supported range instead of only the one CI happens to
    resolve.
    """

    class _Size:
        def __init__(self, width):
            self.width = width

    class _Widget:
        def __init__(self, width):
            self.size = TestTextWidthNeverExceedsTheTerminal._Size(width)

    class _Screen:
        def __init__(self, screen_width, widget_width):
            self.size = TestTextWidthNeverExceedsTheTerminal._Size(screen_width)
            self.app = self
            self._widget_width = widget_width

        def query(self, _selector):
            if self._widget_width is None:
                return []
            return [TestTextWidthNeverExceedsTheTerminal._Widget(self._widget_width)]

    @pytest.mark.parametrize("widget_width", [None, 0, 40, 96, 120, 4096])
    def test_it_is_never_wider_than_the_screen_less_its_chrome(self, widget_width):
        screen = self._Screen(100, widget_width)
        assert tui._text_width(screen) <= 100 - tui._SCROLLBAR

    def test_a_container_sized_widget_is_still_preferred(self):
        """The control: the whole point is to use the widget when it is narrower,
        because that is the two cells the screen measurement was missing."""
        assert tui._text_width(self._Screen(100, 96)) == 96

    def test_an_unmounted_screen_falls_back_instead_of_raising(self):
        """`WorkloadScreen.on_mount` builds its banner before the screen is in the
        DOM, where querying it raises."""

        class Unmounted(self._Screen):
            def query(self, _selector):
                raise RuntimeError("not mounted")

        assert tui._text_width(Unmounted(100, None)) == 100 - tui._SCROLLBAR


class TestTheNodesScreenSentencesAreShared:
    """Round six. Both screens draw these sentences and each spelled them out for
    itself, so they drifted -- `report` said "below threshold", `tui` said "below
    sample threshold" -- and when round five wrapped the prose above them it
    wrapped `report`'s copy only. They live in `render` now, which is what that
    module is for.
    """

    def test_both_front_ends_use_render_for_the_baseline_sentence(self):
        import inspect

        from slurmpast import report, tui

        for module in (report, tui):
            source = inspect.getsource(module)
            assert "nodes_baseline" in source, module.__name__
            assert "baseline %s over %d placements" not in source, (
                "%s spells the sentence out again instead of sharing it" % module.__name__
            )

    def test_both_front_ends_use_render_for_the_empty_reasons(self):
        import inspect

        from slurmpast import report, tui

        for module in (report, tui):
            source = inspect.getsource(module)
            assert "nodes_empty_reason" in source, module.__name__
            assert "so there is nothing" not in source, (
                "%s still carries its own copy of the empty-table sentence" % module.__name__
            )

    def test_the_empty_reason_carries_the_workload_name_it_controlled_on(self):
        """The control: sharing the sentence must not drop what it says. The name
        is the reason the line is unbounded, and also the reason it is worth
        printing -- a reader has to know which workload found nothing."""
        from slurmpast.render import nodes_empty_reason

        table = {"hits": 0, "rows": [], "skipped_nodes": 3}
        assert "for cot-exp" in nodes_empty_reason(table, "hang", "cot-exp")
        assert "hangs" in nodes_empty_reason(table, "hang", None)
        assert "for" not in nodes_empty_reason(table, "hang", None).split("recorded")[1][:6]

    def test_a_table_with_rows_has_no_empty_reason(self):
        from slurmpast.render import nodes_empty_reason

        table = {"hits": 4, "rows": [{"node": "n1"}], "skipped_nodes": 0}
        assert nodes_empty_reason(table, "hang", "cot-exp") == ""


class TestTheDashboardDrawsTheSharedSentences:
    """The other half of `test_audit.TestTheTwoSurfacesCannotDriftApart`.

    That one proves no sentence is written out twice in the source. This one
    proves the dashboard actually puts the shared string on screen, so the two
    together mean a change to `render.py` moves both surfaces and nothing else can.
    """

    @pytest.mark.asyncio
    async def test_the_node_screen_uses_render_for_every_prose_line(self):
        from slurmpast import render
        from slurmpast.demo import history

        app = make_app(list(history()), no_logs=True)
        async with app.run_test(size=(120, 44)) as pilot:
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            assert isinstance(app.screen, tui.NodesScreen)
            summary = " ".join(app.screen.summary_text.plain.split())
            exclude = " ".join(app.screen.exclude_text.plain.split())

        assert render.nodes_workload_control("cot-exp") in summary, summary
        assert render.nodes_correction_note(1) in exclude, exclude
        assert render.nodes_exclude_disclaimer() in exclude, exclude
        # The clause that had drifted: the dashboard used to add ", and that is
        # your call." to the end of it.
        assert "that is your call" not in exclude

    @pytest.mark.asyncio
    async def test_the_patterns_screen_uses_the_shared_empty_sentence(self):
        from slurmpast import render
        from slurmpast.demo import history

        clean = [j for j in history() if j.completed]
        app = make_app(clean, no_logs=True)
        async with app.run_test(size=(120, 44)) as pilot:
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            # From the compositor: `PatternsScreen` keeps no `Text` of its own, and
            # `Static.renderable` exists in textual 0.89 and not in 8.x.
            body = " ".join(
                "".join(segment.text for segment in strip)
                for strip in app.screen._compositor.render_strips()
            )
        assert render.patterns_empty() in " ".join(body.split()), body


class TestTheNodeScreenMeasuresItsChromeRatherThanGuessing:
    """`_prose_width` exists because "screen width minus a constant" is two cells
    optimistic, and its docstring says so. Two `render.wrap` calls on the node
    screen were still spelling out `self.size.width - 8` and `- 6` -- the guessed
    chrome, in the one module that had already been burned by it, wrapping those
    two lines two cells narrower than every other sentence on the same screen.
    """

    def test_no_wrap_on_the_node_screen_hardcodes_a_width(self):
        import ast
        import pathlib

        source = pathlib.Path(tui.__file__).read_text()
        tree = ast.parse(source)
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = getattr(node.func, "attr", None)
            if target != "wrap":
                continue
            for argument in node.args[1:]:
                # `_prose_width(screen, n)` is the sanctioned spelling, and a floor
                # over an already-measured width is fine -- `HelpScreen` clamps its
                # own box width that way. What is banned is deriving the width from
                # `size.width` at the call site, which is the guess `_prose_width`
                # exists to make once and correctly.
                names = {
                    ast.unparse(inner)
                    for inner in ast.walk(argument)
                    if isinstance(inner, ast.Attribute)
                }
                if any(name.endswith("size.width") for name in names):
                    offenders.append(argument.lineno)
        assert not offenders, "render.wrap given a hand-computed width at lines %s" % offenders

    def test_the_sweep_still_recognises_the_spelling_it_bans(self):
        """The control. A sweep that can no longer match anything proves nothing,
        and narrowing it to `size.width` is exactly the change that could do that."""
        import ast

        tree = ast.parse("render.wrap(sentence, max(40, self.size.width - 8))")
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and n.args[1:])
        names = {
            ast.unparse(inner)
            for inner in ast.walk(call.args[1])
            if isinstance(inner, ast.Attribute)
        }
        assert any(name.endswith("size.width") for name in names)

    @pytest.mark.asyncio
    async def test_the_two_lines_wrap_to_the_same_width_as_their_neighbours(self):
        from slurmpast.demo import history

        app = make_app(list(history()), no_logs=True)
        async with app.run_test(size=(100, 44)) as pilot:
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            screen = app.screen
            # What every other prose line on this screen is wrapped to.
            assert tui._prose_width(screen, 2) == tui._text_width(screen) - 2
            assert tui._prose_width(screen, 4) == tui._text_width(screen) - 4
            # The guessed constants were two cells short of both.
            assert tui._prose_width(screen, 2) != max(40, screen.size.width - 6)
            assert tui._prose_width(screen, 4) != max(40, screen.size.width - 8)


class TestTheHelpScreenIsWrappedLikeEveryOtherScreen:
    """The one surface rounds five, six and seven all missed.

    Each of those rounds wrapped the prose on some screen and said why; `HelpScreen`
    was on none of their lists, and it had every symptom at once -- two rows over
    the box's real width, a site-controlled path interpolated into a third, and a
    fixed `width: 78` that a terminal narrower than 80 simply cut.
    """

    @staticmethod
    async def _open(width, jobs):
        app = make_app(jobs, no_logs=True)
        return app

    @pytest.mark.parametrize("width", [60, 70, 80, 100, 140])
    @pytest.mark.asyncio
    async def test_nothing_in_the_box_overruns_the_terminal(self, history_jobs, width):
        app = make_app(history_jobs, no_logs=True)
        async with app.run_test(size=(width, 60)) as pilot:
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            assert isinstance(app.screen, tui.HelpScreen)
            painted = [
                "".join(segment.text for segment in strip).rstrip()
                for strip in app.screen._compositor.render_strips()
            ]
        over = [line for line in painted if len(line) > width]
        assert not over, "help overran a %d-column terminal: %r" % (width, over[:2])

    @pytest.mark.parametrize("width", [60, 70, 79])
    @pytest.mark.asyncio
    async def test_the_box_shrinks_to_a_terminal_narrower_than_it_wants(self, history_jobs, width):
        """`width: 78` in CSS is a floor as well as a ceiling: below 80 columns the
        box was drawn wider than the screen and cut, with no marker."""
        app = make_app(history_jobs, no_logs=True)
        async with app.run_test(size=(width, 60)) as pilot:
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            assert app.screen.box_width() <= width
            painted = "\n".join(
                "".join(segment.text for segment in strip)
                for strip in app.screen._compositor.render_strips()
            )
        # The horizontal claim, and only that: the top rule has to carry both of
        # its corners on one line, which it cannot if the box was cut off the
        # right-hand edge. The bottom rule may legitimately be scrolled out of a
        # short terminal -- the modal scrolls, which is why the scrollbar that
        # `box_width` now allows for is there at all.
        top = next((line for line in painted.splitlines() if "╭" in line), "")
        assert top and "╮" in top, repr(top)

    @pytest.mark.asyncio
    async def test_a_wrapped_description_hangs_under_its_column(self, history_jobs):
        """The two rows that overran were soft-wrapped by Textual to column 2, out
        from under the description they continue."""
        app = make_app(history_jobs, no_logs=True)
        async with app.run_test(size=(80, 60)) as pilot:
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            lines = app.screen.help_text.plain.splitlines()

        keyed = [line for line in lines if line.startswith("  a ")]
        assert keyed, lines[:6]
        # The continuation of the `a` row starts in the description column, not in
        # the key column and not at the left margin.
        index = lines.index(keyed[0])
        continuation = lines[index + 1]
        assert continuation.startswith(" " * tui._HELP_KEY_WIDTH), repr(continuation)
        assert continuation.strip(), "the row should still wrap at 80 columns"

    @pytest.mark.asyncio
    async def test_the_interpolated_clip_path_gets_its_own_line(
        self, history_jobs, tmp_path, monkeypatch
    ):
        """Its length is site-controlled, so inlining it broke the sentence around
        it -- round six's folded-workload-name trap in a new place."""
        long_root = tmp_path.joinpath(*("a-long-scratch-path-segment",) * 6)
        long_root.mkdir(parents=True)
        monkeypatch.setenv("XDG_CACHE_HOME", str(long_root))
        app = make_app(history_jobs, no_logs=True)
        async with app.run_test(size=(80, 70)) as pilot:
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            lines = [line.rstrip() for line in app.screen.help_text.plain.splitlines()]

        sentence = [line for line in lines if "OSC 52" in line]
        assert len(sentence) == 1, sentence
        # The sentence stands alone and stays inside the box; the path follows it.
        assert len(sentence[0]) <= 80 - tui._HELP_BOX_CHROME
        assert str(long_root) in "\n".join(lines)
        assert str(long_root) not in sentence[0]


class TestTheHelpScreenNamesEveryVisibleKey:
    """`m` and `c` are shown in the nodes screen's own footer and appeared in no
    help at all, and `p` meant something else entirely on a job screen -- where
    this help is reachable, and where the only line describing `p` was wrong."""

    def test_every_footer_binding_is_documented(self):
        documented = {key for key, _ in tui._HELP_KEYS}
        # The key column holds spellings like "enter / →"; split them back out,
        # except for "/" itself, which is a key rather than a separator.
        spellings = set(documented)
        for entry in documented:
            if entry != "/":
                spellings.update(part.strip() for part in entry.split("/"))
        missing = []
        for screen in (tui.OverviewScreen, tui.JobListScreen, tui.NodesScreen, tui.JobScreen):
            for binding in screen.BINDINGS:
                if not getattr(binding, "show", False):
                    continue
                key = binding.key.replace("question_mark", "?").replace("slash", "/")
                if key in ("escape", "left", "right"):
                    continue
                if key not in spellings:
                    missing.append("%s: %s" % (screen.__name__, key))
        assert not missing, "shown in a footer and absent from the help: %s" % missing

    def test_the_p_row_names_both_of_its_meanings(self):
        row = dict(tui._HELP_KEYS)["p"]
        assert "across runs" in row
        assert "job screen" in row, row

    def test_the_nodes_screen_keys_are_there(self):
        keys = dict(tui._HELP_KEYS)
        assert "nodes screen" in keys["m"]
        assert "nodes screen" in keys["c"]
