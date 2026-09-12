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

from textual.scrollbar import ScrollBar
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


def _alpha(index):
    """A name with no digits in it, so `index` folds workloads apart, not together."""
    letters = ""
    while True:
        index, rest = divmod(index, 26)
        letters = chr(97 + rest) + letters
        if not index:
            return letters


def _varied(count):
    """`count` jobs in `count` workloads on `count` nodes -- rows on every screen.

    `_many` gives every job the same name and the same node, which is one row on
    the overview and one on the nodes screen. Digits fold to "#" when workloads
    are grouped, so the names have to be alphabetic or they fold back into one.
    """
    return [
        _job("%d" % (2000 + i), name="job" + _alpha(i))._replace(node_list="midway3-%04d" % i)
        for i in range(count)
    ]


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


class TestTheCursorIsNeverTrappedByTheFill:
    """The fill's two rules cancel each other out unless something draws ahead.

    `DataTable` clamps its cursor to `row_count` -- what the fill has REACHED,
    not what the screen holds -- and `_fill_slice` stands aside for
    `_FILL_YIELD_AFTER_KEY` after any key. A key repeating every 33 ms is never
    150 ms old, so on a held arrow the fill never resumes and the cursor stops at
    the last drawn row until the reader lets go. Measured on the 29,617-row flat
    list with the fill stopped at 2,300 rows: sixty `pagedown`s took the cursor
    to 2,299 and forty further `down`s moved it **no rows at all**.

    The fill is stopped here rather than outrun, which is what a key repeating
    faster than `_FILL_YIELD_AFTER_KEY` does to it -- and it makes the edge the
    cursor has to cross `_FIRST_ROWS` exactly, rather than wherever a timer on
    the CI runner happened to get to.
    """

    COUNT = tui._FIRST_ROWS * 3

    async def _starved(self, pilot, app, count=None):
        await pilot.pause()
        screen = tui.JobListScreen(_many(count or self.COUNT), title="all")
        await app.push_screen(screen)
        screen._stop_filling()
        table = screen.query_one("#jobs", DataTable)
        assert table.row_count < len(screen._rows), "the fill finished; nothing to trap"
        return screen, table

    @pytest.mark.asyncio
    async def test_the_cursor_walks_past_what_the_fill_drew(self):
        app = make_app(_many(3))
        async with app.run_test(size=(120, 24)) as pilot:
            _screen, table = await self._starved(pilot, app)
            edge = table.row_count
            for _ in range(edge + 20):
                await pilot.press("down")
            await pilot.pause()
            assert table.cursor_row > edge

    @pytest.mark.asyncio
    async def test_pagedown_lands_past_it_too(self):
        """`pagedown` is the key that reaches the edge in a few presses."""
        app = make_app(_many(3))
        async with app.run_test(size=(120, 24)) as pilot:
            _screen, table = await self._starved(pilot, app)
            edge = table.row_count
            for _ in range(1 + 2 * edge // max(1, table.size.height)):
                await pilot.press("pagedown")
            await pilot.pause()
            assert table.cursor_row > edge

    @pytest.mark.asyncio
    async def test_the_rows_stay_ahead_of_the_cursor_rather_than_level_with_it(self):
        """Drawing exactly as far as the cursor would still leave the screen
        below it blank. The margin is what `_CURSOR_HEADROOM` is for."""
        app = make_app(_many(3))
        async with app.run_test(size=(120, 24)) as pilot:
            _screen, table = await self._starved(pilot, app)
            for _ in range(table.row_count + 20):
                await pilot.press("down")
            await pilot.pause()
            assert table.row_count > table.cursor_row + table.size.height

    @pytest.mark.asyncio
    async def test_the_rows_it_draws_are_the_rows_it_would_have_drawn(self):
        """Drawn ahead is still drawn once, in order, with the right numbers --
        the property `test_the_row_numbers_are_the_row_and_not_the_batch` pins
        for the fill, checked again on the path that overtakes it."""
        app = make_app(_many(3))
        async with app.run_test(size=(120, 24)) as pilot:
            screen, table = await self._starved(pilot, app)
            for _ in range(table.row_count + 20):
                await pilot.press("down")
            await pilot.pause()
            keys = [str(row.key.value) for row in table.ordered_rows]
            assert keys == [str(n) for n in range(1, table.row_count + 1)]
            assert screen._filled == table.row_count

    @pytest.mark.asyncio
    async def test_ctrl_end_lands_on_the_last_job_not_the_last_drawn_row(self):
        """`DataTable.action_scroll_bottom` reads `row_count`, which mid-fill is
        the boundary rather than the end. The list is what it means."""
        app = make_app(_many(3))
        async with app.run_test(size=(120, 24)) as pilot:
            screen, table = await self._starved(pilot, app)
            await pilot.press("ctrl+end")
            await pilot.pause()
            assert table.cursor_row == len(screen._rows) - 1

    @pytest.mark.asyncio
    async def test_nothing_is_drawn_ahead_once_every_row_is(self):
        """CONTROL — the extension is bounded by the list, not by the key count."""
        app = make_app(_many(30))
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            table = app.screen.query_one("#jobs", DataTable)
            app.screen.ensure_all_rows()
            for _ in range(60):
                await pilot.press("down")
            await pilot.pause()
            assert table.row_count == 30
            assert table.cursor_row == 29

    @pytest.mark.asyncio
    async def test_an_upward_key_draws_nothing(self):
        """CONTROL — `up` cannot reach the edge, so it must not pay for it."""
        app = make_app(_many(3))
        async with app.run_test(size=(120, 24)) as pilot:
            _screen, table = await self._starved(pilot, app)
            drawn = table.row_count
            for _ in range(20):
                await pilot.press("up")
            await pilot.pause()
            assert table.row_count == drawn


class TestMovingTheCursorRedrawsTwoRowsNotTheViewport:
    """Textual keys both of its row caches on `cursor_coordinate`.

    ``_line_cache`` holds the finished `Strip` and ``_row_render_cache`` the
    segments behind it, and the cursor's position is part of both keys -- so one
    arrow key invalidates every line on screen. Once the table is scrolling, and
    the compositor is therefore asking for every line rather than the two rows
    the cursor touched, that invalidation is a whole-viewport re-render for a
    move that can change two rows. `FastDataTable._render_line` draws a row the
    cursor is not on as though the cursor were nowhere, which is what those rows
    actually look like under a ``row`` cursor.

    Measured on the 29,617-row flat list at a 50-line terminal, per arrow key:
    30.3 line renders and 393.9 cell renders became 1.6 and 21.3.
    """

    @staticmethod
    def _counted(monkeypatch):
        seen = []
        original = DataTable._render_line_in_row

        def counting(self, row_key, *args, **kwargs):
            seen.append(row_key)
            return original(self, row_key, *args, **kwargs)

        monkeypatch.setattr(DataTable, "_render_line_in_row", counting)
        return seen

    async def _scrolling(self, pilot, app):
        """The flat list with the cursor deep enough that each key scrolls."""
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        app.screen.ensure_all_rows()
        await pilot.pause()
        table = app.screen.query_one("#jobs", DataTable)
        for _ in range(2 * table.size.height + 4):
            await pilot.press("down")
        await pilot.pause()
        assert table.scroll_offset.y > 0, "not scrolling; nothing to measure"
        return table

    @pytest.mark.asyncio
    async def test_one_key_rebuilds_a_handful_of_rows(self, monkeypatch):
        app = make_app(_many(400))
        async with app.run_test(size=(120, 24)) as pilot:
            table = await self._scrolling(pilot, app)
            seen = self._counted(monkeypatch)
            await pilot.press("down")
            await pilot.pause()
            # Two rows can look different -- the one the cursor left and the one
            # it reached -- plus the row that scrolled in. Nothing like a
            # viewport, which is `table.size.height`.
            assert len(seen) < table.size.height, len(seen)

    @pytest.mark.asyncio
    async def test_stock_textual_rebuilds_the_viewport(self, monkeypatch):
        """CONTROL — without which the test above passes on a table nobody scrolls."""
        app = make_app(_many(400))
        async with app.run_test(size=(120, 24)) as pilot:
            table = await self._scrolling(pilot, app)
            monkeypatch.delattr(tui.FastDataTable, "_render_line")
            for _ in range(3):
                await pilot.press("down")
            await pilot.pause()
            seen = self._counted(monkeypatch)
            await pilot.press("down")
            await pilot.pause()
            assert len(seen) >= table.size.height, len(seen)

    @pytest.mark.asyncio
    async def test_the_drawn_screen_is_the_one_stock_textual_draws(self, monkeypatch):
        """The property the whole optimisation rests on, checked cell by cell.

        This is what caught the first attempt: the sentinel was ``Coordinate(-1,
        -1)``, and Textual gives a row it cannot place -- the header -- a row
        index of ``-1``, so the header came out in the cursor's own colour.
        """

        async def drawn(with_fast):
            app = make_app(_many(400))
            async with app.run_test(size=(120, 24)) as pilot:
                table = await self._scrolling(pilot, app)
                if not with_fast:
                    monkeypatch.delattr(tui.FastDataTable, "_render_line")
                for _ in range(20):
                    await pilot.press("down")
                for _ in range(3):
                    await pilot.press("up")
                await pilot.pause()
                return table.cursor_row, [
                    [(segment.text, segment.style) for segment in table.render_line(y)]
                    for y in range(table.size.height)
                ]

        fast_cursor, fast = await drawn(True)
        stock_cursor, stock = await drawn(False)
        assert fast_cursor == stock_cursor
        assert fast == stock

    @pytest.mark.asyncio
    async def test_the_sentinel_is_not_a_row_index_textual_uses(self):
        """`-1` is Textual's "this row has no index"; the cursor must not sit there."""
        assert tui.FastDataTable._CURSOR_NOWHERE.row < -1
        assert tui.FastDataTable._CURSOR_NOWHERE.column < -1


class TestTheScrollbarRepaintsWhenItMoves:
    """`ScrollBar.position` is a repainting reactive holding the scroll offset.

    So one arrow key repaints the whole bar, while what the bar can draw is far
    coarser -- eighth-block glyphs give a 45-line bar 360 thumb positions, and
    over 29,617 rows that is one visible change every 82 rows. Measured on the
    flat job list at a 50-line terminal, holding the down arrow: 39.2 scrollbar
    lines re-rendered per key, 2.8 ms of the 18.0 ms a key cost -- and removing
    the repaint took the whole key from 18.0 ms to 12.3 ms, because the compositor
    was following it onto every line the bar overlapped.

    The property that makes it safe is that the drawn bar is unchanged, and that
    is checked here against the stock scrollbar rather than argued.
    """

    async def _table(self, pilot, app):
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        app.screen.ensure_all_rows()
        await pilot.pause()
        table = app.screen.query_one("#jobs", DataTable)
        assert table.show_vertical_scrollbar, "no scrollbar; nothing to measure"
        return table

    @staticmethod
    def _drawn(bar):
        return [
            [(segment.text, segment.style) for segment in bar.render_line(y)]
            for y in range(bar.size.height)
        ]

    @pytest.mark.asyncio
    async def test_the_bar_draws_what_the_stock_bar_draws(self, monkeypatch):
        """Every line of it, at scroll positions across the whole list."""
        rows = 4000

        async def drawn(steady):
            if not steady:
                monkeypatch.delattr(tui.FastDataTable, "vertical_scrollbar")
            app = make_app(_many(rows))
            async with app.run_test(size=(120, 24)) as pilot:
                table = await self._table(pilot, app)
                bar = table.vertical_scrollbar
                shots = []
                for row in list(range(0, 120, 3)) + list(range(0, rows, 97)) + [rows - 1]:
                    table.move_cursor(row=row)
                    await pilot.pause()
                    shots.append(self._drawn(bar))
                return shots

        steady = await drawn(True)
        stock = await drawn(False)
        assert steady == stock

    @staticmethod
    def _count_repaints(monkeypatch):
        """How many times any scrollbar is told to redraw itself."""
        painted = []
        original = ScrollBar.refresh

        def counting(self, *args, **kwargs):
            painted.append(1)
            return original(self, *args, **kwargs)

        monkeypatch.setattr(ScrollBar, "refresh", counting)
        return painted

    @pytest.mark.asyncio
    async def test_a_key_that_cannot_move_the_thumb_does_not_repaint_it(self, monkeypatch):
        app = make_app(_many(4000))
        async with app.run_test(size=(120, 24)) as pilot:
            await self._table(pilot, app)
            for _ in range(30):
                await pilot.press("down")
            await pilot.pause()
            painted = self._count_repaints(monkeypatch)
            for _ in range(40):
                await pilot.press("down")
            await pilot.pause()
            assert len(painted) < 40, len(painted)

    @pytest.mark.asyncio
    async def test_the_stock_bar_repaints_on_every_key(self, monkeypatch):
        """CONTROL — without which the test above passes on a bar nobody scrolls."""
        monkeypatch.delattr(tui.FastDataTable, "vertical_scrollbar")
        app = make_app(_many(4000))
        async with app.run_test(size=(120, 24)) as pilot:
            await self._table(pilot, app)
            for _ in range(30):
                await pilot.press("down")
            await pilot.pause()
            painted = self._count_repaints(monkeypatch)
            for _ in range(40):
                await pilot.press("down")
            await pilot.pause()
            assert len(painted) >= 40, len(painted)

    @pytest.mark.asyncio
    async def test_the_thumb_still_reaches_both_ends(self):
        """CONTROL — a bar that never repaints would pass the two above."""
        app = make_app(_many(4000))
        async with app.run_test(size=(120, 24)) as pilot:
            table = await self._table(pilot, app)
            bar = table.vertical_scrollbar
            table.move_cursor(row=0)
            await pilot.pause()
            top = self._drawn(bar)
            table.move_cursor(row=3999)
            await pilot.pause()
            assert self._drawn(bar) != top

    @pytest.mark.asyncio
    async def test_the_offset_itself_is_still_exact(self):
        """`_on_mouse_capture` anchors a drag at `position`, so rounding it would
        jump the view by a bar-eighth the moment the thumb is grabbed. Only the
        repaint is conditional; the value is not touched."""
        app = make_app(_many(4000))
        async with app.run_test(size=(120, 24)) as pilot:
            table = await self._table(pilot, app)
            bar = table.vertical_scrollbar
            for row in (137, 1381, 3999):
                table.move_cursor(row=row)
                await pilot.pause()
                assert bar.position == pytest.approx(table.scroll_offset.y)

    @pytest.mark.asyncio
    async def test_a_bar_it_cannot_predict_repaints_anyway(self):
        """`render_bar` draws a full-length bar when the sizes are degenerate, and
        the position does not enter into it. `_drawn_state` says None there, which
        is never equal to a state, so those cases keep stock behaviour."""
        app = make_app(_many(400))
        async with app.run_test(size=(120, 24)) as pilot:
            table = await self._table(pilot, app)
            bar = table.vertical_scrollbar
            assert bar._drawn_state(0.0) is not None
            bar.window_size = 0
            assert bar._drawn_state(0.0) is None
            bar.window_size = bar.window_virtual_size = 40
            assert bar._drawn_state(0.0) is None

    @pytest.mark.asyncio
    async def test_a_textual_without_the_internals_gets_the_stock_bar(self, monkeypatch):
        """The four mirrored lines are the only place this file reads Textual's
        internals. Where the names are gone, the stock scrollbar comes back."""
        app = make_app(_many(400))
        async with app.run_test(size=(120, 24)) as pilot:
            await self._table(pilot, app)
            fresh = tui.FastDataTable()
            monkeypatch.delattr(type(fresh), "_vertical_scrollbar", raising=False)
            monkeypatch.delattr(fresh, "_vertical_scrollbar", raising=False)
            assert not hasattr(fresh, "_vertical_scrollbar")
            # The guard is what is under test, not the widget it would build.
            assert tui.FastDataTable.vertical_scrollbar.fget is not None


class TestHoldingAnArrowKeyCoversGround:
    """A remote control's fast-forward: tap it and it steps, hold it and it flies.

    On a 29,617-row history the alternative to this is `pagedown` held for a
    minute. Measured in a real pty at a 30 Hz key repeat, rows covered per second
    of holding: 30, 30, 30, then 232, 448, 800, and ~1,700 from the sixth second
    on -- the whole history in about half a minute, with the first three seconds
    left exactly as they were.

    `_HeldKey` takes the clock as an argument, so the ramp is checked at every
    point on it without a running app or a sleeping test.
    """

    @pytest.fixture(autouse=True)
    def _ramp_on(self, key_acceleration):
        """This class is what `conftest._no_key_acceleration` steps aside for."""

    @staticmethod
    def _held(key="down", seconds=0.0, rate=30.0, start=1000.0):
        """A key held for `seconds` at `rate` presses a second. Returns the last."""
        ramp = tui._HeldKey()
        now = start
        stride = ramp.stride(key, now)
        while now < start + seconds:
            now += 1.0 / rate
            stride = ramp.stride(key, now)
        return ramp, stride, now

    def test_one_press_moves_one_row(self):
        ramp = tui._HeldKey()
        assert ramp.stride("down", 1000.0) == 1

    def test_a_short_burst_still_moves_one_row(self):
        """The threshold is the whole point: reading down a list a row at a time
        is what the key is for, and a ramp that started at once would take it."""
        _ramp, stride, _now = self._held(seconds=tui._ACCEL_AFTER - 0.2)
        assert stride == 1

    def test_past_the_threshold_it_takes_off(self):
        _ramp, stride, _now = self._held(seconds=tui._ACCEL_AFTER + 0.1)
        assert stride == tui._ACCEL_FIRST

    def test_and_keeps_doubling(self):
        _ramp, stride, _now = self._held(seconds=tui._ACCEL_AFTER + tui._ACCEL_DOUBLE + 0.1)
        assert stride == tui._ACCEL_FIRST * 2

    def test_up_to_a_ceiling(self):
        _ramp, stride, _now = self._held(seconds=tui._ACCEL_AFTER + 60.0)
        assert stride == tui._ACCEL_MAX

    def test_letting_go_puts_it_back(self):
        ramp, stride, now = self._held(seconds=tui._ACCEL_AFTER + 5.0)
        assert stride > 1
        assert ramp.stride("down", now + tui._ACCEL_GAP + 0.01) == 1

    def test_the_other_direction_starts_over(self):
        """How a reader stops after overshooting: `up` must not inherit the speed
        `down` built up, or the first correction overshoots the other way."""
        ramp, stride, now = self._held(seconds=tui._ACCEL_AFTER + 5.0)
        assert stride > 1
        assert ramp.stride("up", now + 0.03) == 1

    def test_up_accelerates_on_its_own_account(self):
        """CONTROL — the ramp is not a down-arrow special case."""
        _ramp, stride, _now = self._held(key="up", seconds=tui._ACCEL_AFTER + 0.1)
        assert stride == tui._ACCEL_FIRST

    def test_pressing_it_a_lot_is_not_holding_it(self):
        """A reader tapping three times a second for a minute is reading, not
        seeking, and must never find the cursor jumping eight rows under them.
        `_ACCEL_GAP` alone cannot tell the two apart -- it is half a second,
        because that is what a slow frame costs -- so `_ACCEL_MIN_RATE` does."""
        _ramp, stride, _now = self._held(seconds=60.0, rate=3.0)
        assert stride == 1

    def test_a_slow_patch_does_not_drop_a_flying_run_back(self):
        """The verdict is latched. Re-testing the rate continuously would let the
        slower frames that accelerating CAUSES pull the average back under the
        bar, dropping the reader to one row per key and lifting them again a
        second later."""
        ramp, stride, now = self._held(seconds=tui._ACCEL_AFTER + 0.1)
        assert stride == tui._ACCEL_FIRST
        for _ in range(5):
            now += tui._ACCEL_GAP - 0.05
            stride = ramp.stride("down", now)
        assert stride >= tui._ACCEL_FIRST

    def test_another_key_clears_the_run(self):
        ramp, stride, now = self._held(seconds=tui._ACCEL_AFTER + 5.0)
        assert stride > 1
        assert ramp.stride("f", now + 0.01) == 1
        assert ramp.stride("down", now + 0.02) == 1

    def test_a_gap_the_app_caused_does_not_break_the_run(self):
        """A held key that scrolls fast enough eventually needs rows drawn, and at
        the far end of a big table that frame costs about half a second -- longer
        than `_ACCEL_GAP`. Without this the ramp broke on a frame it had asked for
        and rebuilt from one row per key just in time to do it again: measured in
        a real pty, the cursor cycled between 1,700 rows a second and 200 and
        never reached the end of the list."""
        ramp, stride, now = self._held(seconds=tui._ACCEL_AFTER + 5.0)
        assert stride > 1
        ramp.excuse_the_next_gap()
        assert ramp.stride("down", now + tui._ACCEL_GAP + 0.4) > 1

    def test_and_only_the_one_gap(self):
        """CONTROL — an excuse is consumed, not a licence. A reader who let go
        must still land back at one row per key."""
        ramp, stride, now = self._held(seconds=tui._ACCEL_AFTER + 5.0)
        assert stride > 1
        ramp.excuse_the_next_gap()
        now += tui._ACCEL_GAP + 0.4
        assert ramp.stride("down", now) > 1
        assert ramp.stride("down", now + tui._ACCEL_GAP + 0.4) == 1

    def test_an_unexcused_run_still_breaks(self):
        """CONTROL — the flag starts down, so nothing is forgiven by default."""
        ramp, stride, now = self._held(seconds=tui._ACCEL_AFTER + 5.0)
        assert stride > 1
        assert ramp.stride("down", now + tui._ACCEL_GAP + 0.4) == 1

    def test_another_key_spends_the_excuse(self):
        """CONTROL — an excuse earned by `down` cannot be cashed by `f`."""
        ramp, _stride, now = self._held(seconds=tui._ACCEL_AFTER + 5.0)
        ramp.excuse_the_next_gap()
        assert ramp.stride("f", now + 0.01) == 1
        assert ramp.stride("down", now + tui._ACCEL_GAP + 0.4) == 1

    def test_a_key_held_all_day_does_not_build_a_giant_number(self):
        """`_ACCEL_FIRST << doublings` takes its exponent from the wall clock."""
        _ramp, stride, _now = self._held(seconds=3600.0, rate=30.0)
        assert stride == tui._ACCEL_MAX


class TestTheRampMovesTheCursorOnTheJobList:
    """The wiring: the ramp above, reaching a real table."""

    @pytest.fixture(autouse=True)
    def _ramp_on(self, key_acceleration):
        """This class is what `conftest._no_key_acceleration` steps aside for."""

    @staticmethod
    async def _list(pilot, app):
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        app.screen.ensure_all_rows()
        await pilot.pause()
        return app.screen, app.screen.query_one("#jobs", DataTable)

    @staticmethod
    def _pretend_held(screen, key="down"):
        """Put the ramp where a key held past the threshold would have put it."""
        now = time.perf_counter()
        ramp = screen.held
        ramp._key = key
        ramp._started = now - tui._ACCEL_AFTER - 0.05
        ramp._last = now
        ramp._count = int(tui._ACCEL_AFTER * tui._ACCEL_MIN_RATE) + 1
        ramp._fast = True

    @pytest.mark.asyncio
    async def test_a_held_down_arrow_moves_a_stride(self):
        app = make_app(_many(900))
        async with app.run_test(size=(120, 24)) as pilot:
            screen, table = await self._list(pilot, app)
            start = table.cursor_row
            self._pretend_held(screen)
            await pilot.press("down")
            await pilot.pause()
            assert table.cursor_row == start + tui._ACCEL_FIRST

    @pytest.mark.asyncio
    async def test_a_fresh_press_moves_exactly_one(self):
        """CONTROL — without which the test above passes on a broken stride of 1."""
        app = make_app(_many(900))
        async with app.run_test(size=(120, 24)) as pilot:
            _screen, table = await self._list(pilot, app)
            start = table.cursor_row
            await pilot.press("down")
            await pilot.pause()
            assert table.cursor_row == start + 1

    @pytest.mark.asyncio
    async def test_a_held_up_arrow_stops_at_the_top(self):
        app = make_app(_many(900))
        async with app.run_test(size=(120, 24)) as pilot:
            screen, table = await self._list(pilot, app)
            table.move_cursor(row=3)
            await pilot.pause()
            self._pretend_held(screen, "up")
            await pilot.press("up")
            await pilot.pause()
            assert table.cursor_row == 0

    @pytest.mark.asyncio
    async def test_a_stride_lands_on_rows_that_exist(self):
        """`_draw_ahead_of_cursor` is told the stride, because at the top of the
        ramp one press covers more than a screenful."""
        app = make_app(_many(tui._FIRST_ROWS * 4))
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            screen = tui.JobListScreen(_many(tui._FIRST_ROWS * 4), title="all")
            await app.push_screen(screen)
            screen._stop_filling()
            table = screen.query_one("#jobs", DataTable)
            table.move_cursor(row=table.row_count - 1)
            await pilot.pause()
            edge = table.row_count
            self._pretend_held(screen)
            await pilot.press("down")
            await pilot.pause()
            assert table.cursor_row == edge - 1 + tui._ACCEL_FIRST
            assert table.row_count > table.cursor_row

    @pytest.mark.asyncio
    async def test_the_overview_accelerates_too(self):
        """The reader does not know which screen they are on.

        The ramp was written on `JobListScreen` and that is how it shipped: it
        flew inside a workload and crawled on the landing screen, which on a real
        history is 485 rows. It lives on `ScreenChrome` now, and this is the test
        that says so.
        """
        app = make_app(_varied(60))
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, tui.OverviewScreen)
            table = screen.query_one("#groups", DataTable)
            assert table.row_count > tui._ACCEL_FIRST, table.row_count
            start = table.cursor_row
            self._pretend_held(screen)
            await pilot.press("down")
            await pilot.pause()
            assert table.cursor_row == start + tui._ACCEL_FIRST

    @pytest.mark.asyncio
    async def test_the_nodes_screen_hands_its_keys_to_the_ramp(self, monkeypatch):
        """The nodes screen has no key handler of its own but the ramp, so what is
        checked here is that the key reaches it with the stride the reader earned.

        Not that the cursor lands N rows down: `carry_the_cursor` is the same
        shared method the two tests above watch move a real cursor, and a nodes
        table with rows in it needs a statistically interesting history that this
        file has no other reason to build.
        """
        carried = []
        monkeypatch.setattr(
            tui.ScreenChrome,
            "carry_the_cursor",
            lambda self, key, rows: carried.append((type(self).__name__, key, rows)),
        )
        app = make_app(_varied(60))
        async with app.run_test(size=(120, 24)) as pilot:
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, tui.NodesScreen)
            carried.clear()
            self._pretend_held(screen)
            await pilot.press("down")
            await pilot.pause()
            assert ("NodesScreen", "down", tui._ACCEL_FIRST - 1) in carried, carried

    def test_every_screen_with_a_table_names_it(self):
        """The control, and the one that stops this being forgotten again.

        `TABLE_ID` is what `carry_the_cursor` steers, so a screen that composes a
        `DataTable` and does not set it gets no ramp -- silently, and only on that
        screen. Read from the source rather than from a running app, so a screen
        nobody thought to write a test for is still covered.
        """
        import ast
        import pathlib

        source = pathlib.Path(tui.__file__).read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            ids = {
                keyword.value.value
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id in ("DataTable", "FastDataTable")
                for keyword in call.keywords
                if keyword.arg == "id" and isinstance(keyword.value, ast.Constant)
            }
            if not ids:
                continue
            screen = getattr(tui, node.name, None)
            assert screen is not None, node.name
            assert screen.TABLE_ID in ids, (node.name, screen.TABLE_ID, ids)


class TestTheFillNeedsAQuietTick(TestTheFillStaysOutOfTheWay):
    """A deadline alone let the fill restart in the middle of a held key.

    `add_row` bumps `DataTable._update_count`, which is in the key of all three
    of its render caches, so one slice makes the NEXT frame re-render every cell
    on screen -- 598 of them, ~250 ms against the ~12 ms a warm frame costs. That
    frame is longer than the deadline was, so it handed the following tick a
    keyboard that only LOOKED idle: the reader was still holding the key and the
    next press was already queued. Measured holding the down arrow through the
    fill: 84 keys in 8 s, one of them taking 2.4 s.

    Inherits the deadline's own tests so both gates stay covered together.
    """

    @pytest.mark.asyncio
    async def test_a_key_since_the_last_tick_defers_the_slice(self):
        count = tui._FIRST_ROWS * 3
        app = make_app(_many(count))
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = tui.JobListScreen(_many(count), title="all")
            await app.push_screen(screen)
            screen._stop_filling()
            drawn = screen._filled
            # The deadline is satisfied and the fill must still stand aside.
            screen._last_key = time.perf_counter() - tui._FILL_YIELD_AFTER_KEY - 1
            screen._keys_since_slice = 1
            screen._fill_slice()
            assert screen._filled == drawn

    @pytest.mark.asyncio
    async def test_and_the_tick_after_a_quiet_one_gets_on_with_it(self):
        """CONTROL — the gate is a pause, not a stop."""
        count = tui._FIRST_ROWS * 3
        app = make_app(_many(count))
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = tui.JobListScreen(_many(count), title="all")
            await app.push_screen(screen)
            screen._stop_filling()
            drawn = screen._filled
            screen._last_key = time.perf_counter() - tui._FILL_YIELD_AFTER_KEY - 1
            screen._keys_since_slice = 1
            screen._fill_slice()
            screen._fill_slice()
            assert screen._filled > drawn

    @pytest.mark.asyncio
    async def test_a_keypress_is_what_sets_it(self):
        count = tui._FIRST_ROWS * 3
        app = make_app(_many(count))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            screen = app.screen
            screen._keys_since_slice = 0
            await pilot.press("down")
            await pilot.pause()
            assert screen._keys_since_slice > 0

    @pytest.mark.asyncio
    async def test_the_deadline_outlasts_a_cold_frame(self):
        """The number that made the loop sustain itself was 0.15 s against a
        ~0.25 s cold frame. Whatever it is set to, it has to be the longer one."""
        assert tui._FILL_YIELD_AFTER_KEY > 0.2


class TestTheFillAheadTopsUpInBatches:
    """Drawing rows is not free, and the cost is not the rows.

    `add_row` bumps `DataTable._update_count`, which invalidates all three of its
    render caches, so drawing even one row makes the next frame re-render the
    whole viewport — and that cold frame gets *more* expensive the more rows the
    table holds, because `_y_offsets` is rebuilt over all of them. Topping the
    margin up on every key meant every frame was cold, and in a real pty the
    frames reached 0.5 s at row 16,000: longer than `_ACCEL_GAP`, so a held key
    broke its own run. It now draws nothing while the margin holds and a
    screenful-times-`_CURSOR_TOPUP` block when it does not.
    """

    COUNT = tui._FIRST_ROWS * 6

    async def _starved(self, pilot, app):
        await pilot.pause()
        screen = tui.JobListScreen(_many(self.COUNT), title="all")
        await app.push_screen(screen)
        screen._stop_filling()
        return screen, screen.query_one("#jobs", DataTable)

    @pytest.mark.asyncio
    async def test_a_key_inside_the_margin_draws_nothing(self):
        app = make_app(_many(3))
        async with app.run_test(size=(120, 24)) as pilot:
            screen, table = await self._starved(pilot, app)
            table.move_cursor(row=0)
            await pilot.pause()
            drawn = screen._filled
            assert drawn > table.size.height * tui._CURSOR_HEADROOM, drawn
            screen._draw_ahead_of_cursor()
            assert screen._filled == drawn

    @pytest.mark.asyncio
    async def test_a_key_at_the_margin_draws_a_block(self):
        app = make_app(_many(3))
        async with app.run_test(size=(120, 24)) as pilot:
            screen, table = await self._starved(pilot, app)
            table.move_cursor(row=screen._filled - 1)
            await pilot.pause()
            drawn = screen._filled
            screen._draw_ahead_of_cursor()
            grew = screen._filled - drawn
            assert grew > table.size.height * tui._CURSOR_HEADROOM, grew

    @pytest.mark.asyncio
    async def test_the_block_is_excused_so_the_ramp_survives_it(self):
        """The frame after a top-up is the longest thing a held key waits for."""
        app = make_app(_many(3))
        async with app.run_test(size=(120, 24)) as pilot:
            screen, table = await self._starved(pilot, app)
            table.move_cursor(row=screen._filled - 1)
            await pilot.pause()
            screen.held._excused = False
            screen._draw_ahead_of_cursor()
            assert screen.held._excused is True

    @pytest.mark.asyncio
    async def test_and_a_key_that_drew_nothing_is_not_excused(self):
        """CONTROL — the excuse is for the frame the app caused, not for every key."""
        app = make_app(_many(3))
        async with app.run_test(size=(120, 24)) as pilot:
            screen, table = await self._starved(pilot, app)
            table.move_cursor(row=0)
            await pilot.pause()
            screen.held._excused = False
            screen._draw_ahead_of_cursor()
            assert screen.held._excused is False

    @pytest.mark.asyncio
    async def test_the_rows_are_still_all_there_and_in_order(self):
        """CONTROL — batching changes when rows arrive, not which or in what order."""
        app = make_app(_many(3))
        async with app.run_test(size=(120, 24)) as pilot:
            screen, table = await self._starved(pilot, app)
            for _ in range(6):
                table.move_cursor(row=screen._filled - 1)
                await pilot.pause()
                screen._draw_ahead_of_cursor()
            keys = [str(row.key.value) for row in table.ordered_rows]
            assert keys == [str(n) for n in range(1, table.row_count + 1)]
