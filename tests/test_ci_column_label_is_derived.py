"""The confidence-interval column has one spelling, and it comes from `Z`.

Round sixty-nine derived the *prose* spelling and PINNED the three
layout-coupled ones, deferring them with a reason: "`render.NODE_COLUMNS`
declares a WIDTH beside the label ... and `report.py` and `tui.py` key their row
dicts BY that label, so all three must be one string. Rebuilding them is a
layout change, not a polish one."

That reason was about changing the label's TEXT. Deriving the *same* six
characters changes no width, which this file measures rather than assumes:
`table_floor(NODE_COLUMNS)` is still 41 and the column is still 18 wide and
right-aligned. So the pin can become the thing it was standing in for.

`render.CI_COLUMN` is now the single spelling, built as
`"%s%% CI" % nodes.CONFIDENCE_PERCENT`; `render` already imported `MIN_SAMPLES`
from `nodes`, so this adds no dependency direction. The two renderers reference
it instead of repeating it.

**Why the key matters and not just the header:** `text_table` looks a row's
cells up BY the column label. A key that disagrees with the header does not
raise -- it renders the column empty. That is what these tests watch.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from slurmpast.demo import history as demo_jobs
from slurmpast.index import History
from slurmpast.nodes import CONFIDENCE_PERCENT, node_table
from slurmpast.render import CI_COLUMN, NODE_COLUMNS, table_floor
from slurmpast.report import Style, render_nodes

#: What `ci_range` produces -- two rates and a percent sign.
_RANGE = re.compile(r"\d+\.\d+ .{1,3} \d+\.\d+%")


@pytest.fixture(scope="module")
def demo() -> History:
    """The demo tape as a `History`, which is what the renderers take."""
    return History(demo_jobs(), window="test window")


def _plain_nodes(history) -> str:
    out = render_nodes(history, style=Style(enabled=False))
    return out if isinstance(out, str) else "\n".join(out)


class TestTheLabelIsDerived:
    def test_the_column_label_comes_from_the_critical_value(self) -> None:
        assert CI_COLUMN == "%s%% CI" % CONFIDENCE_PERCENT
        assert CI_COLUMN == "95% CI"

    def test_the_table_spec_uses_it(self) -> None:
        labels = [c.label for c in NODE_COLUMNS if "CI" in c.label]
        assert labels == [CI_COLUMN], labels

    def test_the_plain_cell_is_populated(self, demo) -> None:
        """A key/header mismatch renders this column blank instead of raising."""
        out = _plain_nodes(demo)
        assert CI_COLUMN in out, out
        assert _RANGE.search(out), out

    @pytest.mark.asyncio
    async def test_the_dashboard_cell_is_populated(self, demo) -> None:
        """The third site, read off the screen the way `test_tui` reads panels."""
        from slurmpast import tui

        app = tui.SlurmpastApp(lambda: list(demo.jobs), window="test window", no_logs=True)
        async with app.run_test(size=(140, 60)) as pilot:
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            assert isinstance(app.screen, tui.NodesScreen)
            # Off the COMPOSITOR, the way `test_requeue_tail_disclosure` reads a
            # panel and `test_readability` pins as a rule: the attribute a
            # `Static` holds its content in exists in textual 0.89 and not in
            # 8.x, and this screen keeps no `Text` of its own.
            screen: Any = app.screen
            text = " ".join(
                "".join(segment.text for segment in strip)
                for strip in screen._compositor.render_strips()
            )
        assert CI_COLUMN in text, text[:400]
        assert _RANGE.search(text), text[:400]


class TestControls:
    """Each passes with the three literals restored as well as derived.

    They cover the layout the deferral was about, so a neuter that reddens one
    of them means deriving the label moved something it should not have --
    verified by running it.
    """

    def test_the_column_keeps_its_declared_width_and_alignment(self) -> None:
        column = [c for c in NODE_COLUMNS if "CI" in c.label][0]
        assert column.width == 18
        assert column.align == "right"
        assert column.drop == 1

    def test_the_node_table_floor_is_unchanged(self) -> None:
        """The 41 cells `table_floor` records, which is why this was deferred."""
        assert table_floor(NODE_COLUMNS) == 41

    def test_the_label_is_six_characters(self) -> None:
        """Deriving it must not change its width, or the floor above moves."""
        assert len(CI_COLUMN) == 6

    def test_the_other_node_columns_are_untouched(self, demo) -> None:
        out = _plain_nodes(demo)
        for label in ("NODE", "RATE", "VERDICT"):
            assert label in out, (label, out)

    def test_the_payload_still_carries_the_level(self, demo) -> None:
        """`--json`'s `confidence_level`, added in round sixty-eight, is a
        separate surface and this round does not touch it."""
        table = node_table(demo.jobs, workload="cot-exp", metric="hang")
        assert table["confidence_level"] == 0.95
