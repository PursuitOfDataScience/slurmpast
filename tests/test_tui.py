"""Headless dashboard tests.

Textual's ``run_test`` drives the real app without a terminal, so navigation and
key bindings are exercised rather than assumed. These are the tests that catch a
bad format string or a wrong widget id -- the kind of bug that only appears when
a screen actually paints.
"""

import pytest

pytest.importorskip("textual")

from slurmpast import tui  # noqa: E402


def make_app(jobs, **kwargs):
    return tui.SlurmpastApp(lambda: list(jobs), window="test window", **kwargs)


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
