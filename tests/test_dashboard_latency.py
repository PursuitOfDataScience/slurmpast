"""What makes the dashboard answer a keypress rather than freeze on one.

Three changes, each of which trades work for latency, and each of which is only
safe while a property holds. This file pins the properties, not the timings --
a benchmark in a test suite measures the CI runner.

    FastDataTable          skips Textual's per-cell measuring pass, which is
                           dead work while every column has a fixed width.
    the deferred fill      draws a screenful now and the rest between
                           keystrokes, so the table still ends up holding every
                           row.
    SlurmpastApp.job_cells keeps a job's rendered cells across refreshes, which
                           is only correct while the loaded history is.

Measured on a real seven-day history of 29,624 jobs before any of it: opening
the flat job list took 9.7 s and every search keystroke on it took 9.6 s, with
the app answering nothing in between.
"""

import time

import pytest

pytest.importorskip("textual")

from textual.widgets import DataTable

from slurmpast import tui
from slurmpast.model import Job


def _job(job_id, name="w", state="COMPLETED"):
    return Job(
        job_id=job_id,
        name=name,
        user="u",
        partition="test",
        state=state,
        submit="2026-01-01T00:00:00",
        start="2026-01-01T00:00:00",
        end="2026-01-01T00:10:00",
        elapsed=600.0,
        node_list="midway3-0001",
    )


def _many(count):
    return [_job("%d" % (1000 + i)) for i in range(count)]


def make_app(jobs):
    return tui.SlurmpastApp(lambda: list(jobs), window="test window", no_logs=True)


class TestFastDataTable:
    """The skip is only sound while nothing reads what it skips computing.

    Textual's `_update_dimensions` measures each cell of each new row to grow
    `Column.content_width`, and `Column.get_render_width` reads that back only
    `if self.auto_width`. `_sync_columns` gives every column an explicit width,
    so the pass computes a number nothing will look at -- 355,404 measure()
    calls and 4.12 s of the 9.7 s that opening the flat job list cost, repeated
    on every filter change.
    """

    WIDE = "a very wide cell indeed"

    async def _column(self, pilot, app, table, width):
        await app.screen.mount(table)
        table.add_column("A", width=width)
        table.add_row(self.WIDE)
        await pilot.pause()
        return next(iter(table.columns.values()))

    @pytest.mark.asyncio
    async def test_a_wide_cell_does_not_grow_a_fixed_column(self):
        """`content_width` is what the measuring pass computes; here nobody reads it."""
        app = make_app(_many(3))
        async with app.run_test() as pilot:
            await pilot.pause()
            column = await self._column(pilot, app, tui.FastDataTable(), 6)
            assert not column.auto_width
            assert column.content_width < len(self.WIDE)
            assert column.width == 6

    @pytest.mark.asyncio
    async def test_a_stock_table_does_measure_the_same_cell(self):
        """First control: the difference above is this subclass, not Textual."""
        app = make_app(_many(3))
        async with app.run_test() as pilot:
            await pilot.pause()
            column = await self._column(pilot, app, DataTable(), 6)
            assert column.content_width >= len(self.WIDE)

    @pytest.mark.asyncio
    async def test_an_auto_width_column_is_still_measured(self):
        """Second control: the guard, not the subclass, is what decides."""
        app = make_app(_many(3))
        async with app.run_test() as pilot:
            await pilot.pause()
            column = await self._column(pilot, app, tui.FastDataTable(), None)
            assert column.auto_width
            assert column.content_width >= len(self.WIDE)

    @pytest.mark.asyncio
    async def test_a_fixed_column_renders_at_the_width_it_was_given(self):
        """The reason the skip is safe, stated as the thing a reader sees.

        A fixed column's render width comes from `width`, never from
        `content_width` -- so leaving the latter unmeasured cannot move a column.
        """
        app = make_app(_many(3))
        async with app.run_test() as pilot:
            await pilot.pause()
            fast = tui.FastDataTable()
            stock = DataTable()
            wide = await self._column(pilot, app, fast, 6)
            narrow = await self._column(pilot, app, stock, 6)
            assert wide.get_render_width(fast) == narrow.get_render_width(stock)

    @pytest.mark.asyncio
    async def test_the_scroll_extent_still_grows_with_the_rows(self):
        """`virtual_size` is set by the TAIL of the method being short-circuited.

        Which is why the skip is `super()._update_dimensions(())` and not a
        `return`: the scrollbar and the scroll limit come from this, so a table
        that skipped the tail would hold rows nobody could reach.
        """
        table = tui.FastDataTable()
        app = make_app(_many(3))
        async with app.run_test() as pilot:
            await pilot.pause()
            await app.screen.mount(table)
            table.add_column("A", width=6)
            for i in range(50):
                table.add_row(str(i))
            await pilot.pause()
            assert table.virtual_size.height >= 50


class TestTheTableEndsUpComplete:
    """Deferred, not paged: every row still arrives."""

    @pytest.mark.asyncio
    async def test_more_rows_than_the_first_batch_all_arrive(self):
        count = tui._FIRST_ROWS * 3
        app = make_app(_many(count))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, tui.JobListScreen)
            table = screen.query_one("#jobs", DataTable)
            assert len(screen._rows) == count
            screen.ensure_all_rows()
            assert table.row_count == count

    @pytest.mark.asyncio
    async def test_the_first_batch_is_there_before_anything_else_runs(self):
        """The point of the whole thing: a screenful without yielding."""
        count = tui._FIRST_ROWS * 3
        app = make_app(_many(count))
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = tui.JobListScreen(_many(count), title="all")
            await app.push_screen(screen)
            # No pause: whatever is in the table now was drawn synchronously.
            assert screen._filled >= tui._FIRST_ROWS

    async def _part_drawn(self, app, count):
        """A job list frozen after its first batch, with rows still to come."""
        screen = tui.JobListScreen(_many(count), title="all")
        await app.push_screen(screen)
        screen._stop_filling()
        assert screen._filled < count, "the fixture is too small to test this"
        return screen

    @pytest.mark.asyncio
    async def test_end_reaches_the_last_row_mid_fill(self):
        """`end` asks the TABLE where the end is, so the fill has to finish first."""
        count = tui._FIRST_ROWS * 3
        app = make_app(_many(count))
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = await self._part_drawn(app, count)
            await pilot.press("slash")  # `end` is steered from the search box
            await pilot.press("end")
            await pilot.pause()
            table = screen.query_one("#jobs", DataTable)
            assert table.cursor_row == count - 1

    @pytest.mark.asyncio
    async def test_a_digit_jump_past_the_drawn_rows_lands(self):
        count = tui._FIRST_ROWS * 3
        app = make_app(_many(count))
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = await self._part_drawn(app, count)
            target = tui._FIRST_ROWS + 50
            for digit in str(target):
                screen.action_digit(digit)
            table = screen.query_one("#jobs", DataTable)
            assert table.cursor_row == target - 1

    @pytest.mark.asyncio
    async def test_the_row_numbers_are_the_row_and_not_the_batch(self):
        """The `#` column numbers positions, so it must not restart per slice."""
        count = tui._FIRST_ROWS * 3
        app = make_app(_many(count))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            screen = app.screen
            screen.ensure_all_rows()
            table = screen.query_one("#jobs", DataTable)
            labels = [label for label, _ in screen._layout]
            assert "#" in labels
            at = labels.index("#")
            last = table.get_row_at(count - 1)[at]
            assert last.plain.strip() == str(count)

    @pytest.mark.asyncio
    async def test_a_new_filter_cancels_the_fill_it_replaced(self):
        count = tui._FIRST_ROWS * 3
        app = make_app(_many(count))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            screen = app.screen
            screen.search_text = "no such job anywhere"
            await pilot.pause()
            assert screen._rows == []
            assert screen._fill_timer is None
            assert screen.query_one("#jobs", DataTable).row_count == 0


class TestTheCellCache:
    """Cells are kept across refreshes, so they must not outlive their history."""

    @pytest.mark.asyncio
    async def test_a_reload_drops_the_cached_cells(self):
        jobs = _many(5)
        app = make_app(jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            assert app.job_cells, "nothing was cached, so this proves nothing"
            app._loaded(app.history, None)
            assert app.job_cells == {}

    @pytest.mark.asyncio
    async def test_a_cached_row_still_says_what_the_job_says(self):
        jobs = [_job("2001", name="alpha"), _job("2002", name="beta", state="FAILED")]
        app = make_app(jobs)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            screen = app.screen
            screen.ensure_all_rows()
            for job in jobs:
                cells = app.job_cells[job.job_id]
                assert cells["JOBID"].plain == job.job_id
                assert cells["NAME"].plain == job.name
                assert cells["STATE"].plain == job.base_state


class TestTheResizeGuard:
    """Textual sends a Resize right after a screen is laid out.

    The rows were already guarded (`_rows_already_drawn`), but everything around
    them ran a second time at the same size: the filter, the sort, the summary's
    per-job counts. 122 ms of the 391 ms that opening the flat list cost.
    """

    @pytest.mark.asyncio
    async def test_a_resize_at_the_same_size_rebuilds_nothing(self):
        app = make_app(_many(20))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            screen = app.screen
            calls = []
            original = screen.refresh_rows
            screen.refresh_rows = lambda *a, **k: calls.append(a) or original(*a, **k)
            screen.on_resize()
            assert calls == []

    @pytest.mark.asyncio
    async def test_a_resize_to_a_new_size_does_rebuild(self):
        """The control: the guard must not swallow a real relayout."""
        app = make_app(_many(20))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            screen = app.screen
            calls = []
            original = screen.refresh_rows
            screen.refresh_rows = lambda *a, **k: calls.append(a) or original(*a, **k)
            screen._sized_at = None
            screen.on_resize()
            assert calls


class TestWhatTurnsTheSkipOff:
    """The two row shapes the skipped loop is the only thing that measures."""

    @pytest.mark.asyncio
    async def test_an_auto_height_row_restores_stock_behaviour(self):
        app = make_app(_many(3))
        async with app.run_test() as pilot:
            await pilot.pause()
            table = tui.FastDataTable()
            await app.screen.mount(table)
            table.add_column("A", width=6)
            assert table.fixed_cell_sizes
            table.add_row("one\ntwo", height=None)
            await pilot.pause()
            assert not table.fixed_cell_sizes
            assert table.rows[next(iter(table.rows))].height >= 2

    @pytest.mark.asyncio
    async def test_a_labelled_row_restores_stock_behaviour(self):
        app = make_app(_many(3))
        async with app.run_test() as pilot:
            await pilot.pause()
            table = tui.FastDataTable()
            await app.screen.mount(table)
            table.add_column("A", width=6)
            table.add_row("x", label="a long row label")
            await pilot.pause()
            assert not table.fixed_cell_sizes
            assert table._label_column.content_width >= len("a long row label")

    @pytest.mark.asyncio
    async def test_the_screens_never_pass_either(self):
        """The control: this is why the switch is a safety net and not a cost."""
        app = make_app(_many(20))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            for table in app.screen.query(tui.FastDataTable):
                assert table.fixed_cell_sizes


class TestTheFillStaysOutOfTheWay:
    """The background fill must lose to the keyboard, not race it.

    Measured in a real pty on the 29,617-row flat list: at a four-fifths duty
    cycle an arrow key pressed while the fill ran took **110 ms, worst 350 ms**.
    A third of the idle time plus standing aside for 150 ms after any keypress
    took the same key to **5 ms**. The rows still all arrive -- see
    `TestTheTableEndsUpComplete` -- they simply arrive when nobody is looking.
    """

    @pytest.mark.asyncio
    async def test_a_slice_does_nothing_while_a_key_is_recent(self):
        count = tui._FIRST_ROWS * 3
        app = make_app(_many(count))
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = tui.JobListScreen(_many(count), title="all")
            await app.push_screen(screen)
            screen._stop_filling()
            drawn = screen._filled
            screen._last_key = time.perf_counter()
            screen._fill_slice()
            assert screen._filled == drawn

    @pytest.mark.asyncio
    async def test_and_gets_on_with_it_once_the_keyboard_is_quiet(self):
        """CONTROL — without which the test above passes on a fill that is broken."""
        count = tui._FIRST_ROWS * 3
        app = make_app(_many(count))
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = tui.JobListScreen(_many(count), title="all")
            await app.push_screen(screen)
            screen._stop_filling()
            drawn = screen._filled
            screen._last_key = time.perf_counter() - tui._FILL_YIELD_AFTER_KEY - 1
            screen._fill_slice()
            assert screen._filled > drawn

    @pytest.mark.asyncio
    async def test_a_keypress_is_what_stamps_it(self):
        count = tui._FIRST_ROWS * 3
        app = make_app(_many(count))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            screen = app.screen
            screen._last_key = 0.0
            await pilot.press("down")
            await pilot.pause()
            assert screen._last_key > 0.0

    @pytest.mark.asyncio
    async def test_the_duty_cycle_leaves_most_of_the_time_free(self):
        """A slice must be shorter than the gap between slices, or the fill IS
        the event loop. This is the number the pty measurement was of."""
        assert tui._FILL_BUDGET < tui._FILL_EVERY


class TestTheSearchBoxWaitsForYouToStop:
    """Typing was one full rebuild per character.

    At 29,617 jobs that is 100-311 ms each -- 139 ms of it `DataTable.clear`,
    which is Textual's own and scales with the rows in the widget -- so "test"
    was four of them back to back. It now re-filters once the keystrokes stop.
    Enter and escape do NOT wait: both of them END a search, and making the reader
    watch a debounce after committing would be the same lag by another name.
    """

    async def _typed(self, pilot, app, text):
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("slash")
        await pilot.pause()
        for char in text:
            await pilot.press(char)
        return app.screen

    @pytest.mark.asyncio
    async def test_typing_does_not_filter_straight_away(self):
        app = make_app(_many(40) + [_job("7777", name="needle")])
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = await self._typed(pilot, app, "needle")
            await pilot.pause()
            assert screen.search_text == ""

    @pytest.mark.asyncio
    async def test_and_does_once_the_typing_stops(self):
        app = make_app(_many(40) + [_job("7777", name="needle")])
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = await self._typed(pilot, app, "needle")
            await pilot.pause(tui._SEARCH_SETTLE * 2)
            await pilot.pause()
            assert screen.search_text == "needle"
            assert [j.job_id for j in screen._rows] == ["7777"]

    @pytest.mark.asyncio
    async def test_enter_commits_without_waiting(self):
        app = make_app(_many(40) + [_job("7777", name="needle")])
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = await self._typed(pilot, app, "needle")
            await pilot.press("enter")
            await pilot.pause()
            assert screen.search_text == "needle"

    @pytest.mark.asyncio
    async def test_escape_cancels_without_the_query_coming_back(self):
        """The debounce must be cancelled, not merely outrun.

        A timer still in flight when escape resets the box would put the
        cancelled query straight back a moment later.
        """
        app = make_app(_many(40) + [_job("7777", name="needle")])
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = await self._typed(pilot, app, "needle")
            await pilot.press("escape")
            await pilot.pause(tui._SEARCH_SETTLE * 2)
            await pilot.pause()
            assert screen.search_text == ""
            assert len(screen._rows) == 41
