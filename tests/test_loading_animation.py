"""The gradient sweep the dashboard shows while it waits.

The window paints in 0.38 s and the history lands 2.3 s later warm, 7 s cold, so
there is a real gap. It used to hold the word `loading…` in grey, which cannot
tell "working" from "hung" -- the one question a reader has during that gap, in a
tool whose premise is not confusing a hang with work.

What is pinned here is that it MOVES, that the gradient is legible when nothing
is moving over it, that `--ascii` still shows motion without needing colour, and
that the timer driving it exists only while there is something to wait for. The
last one matters most: the rest of this file's day was spent taking idle work off
the event loop, and an animation is idle work by construction.
"""

import time

import pytest

pytest.importorskip("textual")

from slurmpast import render, tui
from slurmpast.model import Job


def _job():
    return Job(
        job_id="1",
        name="w",
        user="u",
        state="COMPLETED",
        elapsed=60.0,
        start="2026-09-01T00:00:00",
        end="2026-09-01T00:01:00",
    )


class TestTheBarItself:
    def test_it_is_exactly_as_wide_as_asked(self):
        for width in (8, 28, 60):
            assert len(render.loading_bar(0, width=width).plain) == width

    def test_every_frame_of_a_cycle_is_different(self):
        """A "cycle" is one pass of the head along the bar."""
        frames = {render.loading_bar(f).markup for f in range(render.LOADING_WIDTH)}
        assert len(frames) == render.LOADING_WIDTH

    def test_and_it_wraps_rather_than_jumping(self):
        assert render.loading_bar(0).markup == render.loading_bar(render.LOADING_WIDTH).markup

    def test_the_gradient_is_visible_with_nothing_moving_over_it(self):
        """The first cut lit only the comet; captured from a real pty, most of the
        tail came out as `38;5;16` -- black. An unlit cell has to keep its hue."""
        bar = render.loading_bar(0)
        # The cell furthest from the head, i.e. fully at rest.
        resting = bar.spans[render.LOADING_WIDTH // 2].style
        red, green, blue = render._hex_to_rgb(resting)
        assert max(red, green, blue) > 40, resting  # not black
        assert max(red, green, blue) - min(red, green, blue) > 10, resting  # not grey

    def test_the_head_is_the_brightest_cell(self):
        bar = render.loading_bar(0)
        brightness = [sum(render._hex_to_rgb(sp.style)) for sp in bar.spans]
        assert brightness.index(max(brightness)) == 0, brightness

    def test_the_hue_ring_closes(self):
        assert render.sweep_hue(0.0) == render.sweep_hue(1.0)

    def test_it_runs_through_the_apps_own_resource_hues(self):
        """Not an invented palette: the one animation here speaks the vocabulary
        every bar and column beside it already uses."""
        from slurmpast import theme

        assert render.sweep_hue(0.0) == theme.CPU_COLOR
        assert render.sweep_hue(0.25) == theme.GPU_COLOR
        assert render.sweep_hue(0.5) == theme.MEM_COLOR
        assert render.sweep_hue(0.75) == theme.ACCENT


class TestAsciiMode:
    def test_it_draws_no_block_characters(self):
        plain = render.loading_bar(6, ascii_mode=True).plain
        assert plain.isascii(), plain
        assert set(plain) <= {"#", "-"}, plain

    def test_and_the_motion_survives_without_colour(self):
        """Unicode mode carries the motion in colour alone. ASCII cannot assume
        colour, so the glyphs have to move too."""
        shapes = {render.loading_bar(f, ascii_mode=True).plain for f in range(8)}
        assert len(shapes) == 8

    def test_one_cell_per_cell_either_way(self):
        assert len(render.loading_bar(3, ascii_mode=True).plain) == len(render.loading_bar(3).plain)


def _app(gate):
    """An app whose loader blocks until `gate` is released."""

    def loader(since=None):
        while not gate["done"]:
            time.sleep(0.02)
        return [_job()]

    return tui.SlurmpastApp(loader, window="last 7 days", no_logs=True)


class TestTheTimerOnlyRunsWhileWaiting:
    @pytest.mark.asyncio
    async def test_it_advances_while_the_history_is_missing(self):
        gate = {"done": False}
        app = _app(gate)
        try:
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                seen = set()
                for _ in range(6):
                    await pilot.pause(tui._LOADING_FPS_INTERVAL + 0.02)
                    seen.add(app.screen._loading_frame)
                assert len(seen) > 1, seen
                assert app.screen._loading_timer is not None
                gate["done"] = True
                while app.history is None:
                    await pilot.pause()
                await pilot.pause()
                assert app.screen._loading_timer is None
        finally:
            gate["done"] = True

    @pytest.mark.asyncio
    async def test_the_line_says_what_it_is_waiting_on(self):
        gate = {"done": False}
        app = _app(gate)
        try:
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                # Composed onto `summary_text` like everything else this screen
                # draws, not only into the widget.
                assert "reading sacct" in app.screen.summary_text.plain
        finally:
            gate["done"] = True

    @pytest.mark.asyncio
    async def test_a_loaded_dashboard_runs_no_animation_timer(self):
        """The control. An animation left ticking behind a live screen is exactly
        the idle work the fill and the log worker were taught to avoid."""
        app = tui.SlurmpastApp(lambda: [_job()], window="w", no_logs=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            while app.history is None:
                await pilot.pause()
            await pilot.pause()
            assert app.screen._loading_timer is None
            assert "reading sacct" not in app.screen.summary_text.plain
