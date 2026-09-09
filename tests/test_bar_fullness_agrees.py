"""Two of the three bar paths drew solid well below 100%.

`bar`'s own docstring states the rule: *"Two rules keep the bar honest against
the number printed beside it: the last eighth is withheld until the percentage
rounds to 100, so a visually full bar always means 100%; and anything that
displays as >=1% keeps at least a sliver."* Its code says the same at more
length -- "anything short of 100% now ends against a FULL cell of track, and a
bar reaching the end means full and nothing else".

Only the Unicode path did that. The other two -- `ascii_mode`, and `flat`, which
is what the **plain report** draws with -- delegate to `bar_cells`, which rounded
and reserved nothing. Measured before the fix, at widths 8 and 18::

    98.0%   unicode ███████░        ascii ########      <- solid, same label
    99.6%   unicode ███████░        ascii ########
    99.9%   unicode ███████░        ascii ########

Every value from about 97% up disagreed between the paths, beside one shared
"98.0%" label. `bar_cells`' own docstring already recorded fixing exactly this
class of disagreement at the LOW end -- "Using a bare `>= 0.5` here instead made
the ASCII and Unicode bars disagree over 0.5-0.94%: one lit a cell beside a label
reading '0.7%', the other did not" -- so the rule was stated, and the top end had
drifted from it.

The reservation is keyed on `round(percent, 1)`, exactly as `bar()` keys it,
because the labels here carry one decimal: at 99.96% the label reads "100.0%" and
the bar is *meant* to be solid. That is the same one-decimal test the low-end
guard uses, and for the same stated reason.

This is the sibling of the slurmwatch fix in the same family: there the LABEL
rounded up to 100 and both its bar guards keyed on the rounded value, so bar and
label claimed 100% together. Here the label is honest to one decimal and two of
the bars were not.
"""

from __future__ import annotations

import math

import pytest

from slurmpast.render import bar, bar_cells

#: Values that are plainly short of full, including the rounding band.
SHORT_OF_FULL = [90.0, 96.6, 98.0, 99.0, 99.6, 99.9, 99.94]
#: Where the one-decimal label reads "100.0%", so the bar is meant to be solid.
READS_AS_FULL = [99.96, 99.99, 100.0]
WIDTHS = [8, 18]


def _plain(rendered: object) -> str:
    return getattr(rendered, "plain", None) or str(rendered)


def _solid(percent: float, width: int, **kw: object) -> bool:
    text = _plain(bar(percent, "white", width=width, **kw))  # type: ignore[arg-type]
    fill = "#" if kw.get("ascii_mode") else "█"
    return text.count(fill) == width


class TestNoPathDrawsSolidBelowFull:
    @pytest.mark.parametrize("width", WIDTHS)
    @pytest.mark.parametrize("percent", SHORT_OF_FULL)
    def test_the_ascii_bar_reserves_its_last_cell(self, percent: float, width: int) -> None:
        assert not _solid(percent, width, ascii_mode=True), (percent, width)

    @pytest.mark.parametrize("width", WIDTHS)
    @pytest.mark.parametrize("percent", SHORT_OF_FULL)
    def test_the_flat_bar_reserves_its_last_cell(self, percent: float, width: int) -> None:
        # `flat` is what the plain report draws with.
        assert not _solid(percent, width, flat=True), (percent, width)

    @pytest.mark.parametrize("width", WIDTHS)
    @pytest.mark.parametrize("percent", SHORT_OF_FULL)
    def test_the_cell_count_never_reaches_the_width(self, percent: float, width: int) -> None:
        # Not "exactly one short": 90% of 18 rounds to 16 on its own merits, so the
        # reservation only bites where rounding would otherwise have hit the width.
        assert bar_cells(percent, width) < width, (percent, width)

    @pytest.mark.parametrize("width", WIDTHS)
    @pytest.mark.parametrize("percent", [96.6, 98.0, 99.0, 99.6, 99.9, 99.94])
    def test_the_reservation_holds_the_last_cell(self, percent: float, width: int) -> None:
        # The values whose rounding DID reach the width before the fix.
        assert bar_cells(percent, width) == width - 1, (percent, width)

    @pytest.mark.parametrize("width", WIDTHS)
    @pytest.mark.parametrize("percent", SHORT_OF_FULL + READS_AS_FULL)
    def test_all_three_paths_agree(self, percent: float, width: int) -> None:
        uni = _solid(percent, width)
        asc = _solid(percent, width, ascii_mode=True)
        flat = _solid(percent, width, flat=True)
        assert uni == asc == flat, (percent, width, uni, asc, flat)


class TestAValueThatReadsAsFullIsStillSolid:
    @pytest.mark.parametrize("width", WIDTHS)
    @pytest.mark.parametrize("percent", READS_AS_FULL)
    def test_every_path_is_solid(self, percent: float, width: int) -> None:
        assert _solid(percent, width)
        assert _solid(percent, width, ascii_mode=True)
        assert _solid(percent, width, flat=True)

    @pytest.mark.parametrize("width", WIDTHS)
    def test_the_boundary_is_the_one_decimal_label(self, width: int) -> None:
        # 99.94 prints as "99.9%", 99.96 prints as "100.0%".
        assert bar_cells(99.94, width) == width - 1
        assert bar_cells(99.96, width) == width


class TestControls:
    """Behaviour that must not change. Each passes in BOTH states."""

    @pytest.mark.parametrize("width", WIDTHS)
    @pytest.mark.parametrize("percent", [0.0, 0.4, 1.0, 25.0, 50.0, 75.0, 90.0])
    def test_every_ordinary_value_is_unchanged(self, percent: float, width: int) -> None:
        """Pinned as MEASURED counts, not as a recomputation of the formula.

        25% of 18 is 4.5, which `round` takes to 4 -- banker's rounding. An
        expectation written from the arithmetic instead of from the code said 5.
        """
        expected = {
            (0.0, 8): 0,
            (0.4, 8): 0,
            (1.0, 8): 1,
            (25.0, 8): 2,
            (50.0, 8): 4,
            (75.0, 8): 6,
            (90.0, 8): 7,
            (0.0, 18): 0,
            (0.4, 18): 0,
            (1.0, 18): 1,
            (25.0, 18): 4,
            (50.0, 18): 9,
            (75.0, 18): 14,
            (90.0, 18): 16,
        }[(percent, width)]
        assert bar_cells(percent, width) == expected

    def test_a_sliver_is_still_kept_for_anything_printing_as_one_percent(self) -> None:
        # The low-end rule, which this fix mirrors at the top.
        assert bar_cells(1.0, 18) >= 1
        assert bar_cells(0.96, 18) >= 1  # prints as "1.0%"
        assert bar_cells(0.94, 18) == 0  # prints as "0.9%"

    def test_none_still_draws_an_empty_track(self) -> None:
        assert bar_cells(None, 8) == 0
        assert _plain(bar(None, "white", width=8)) == "░" * 8
        assert _plain(bar(None, "white", width=8, ascii_mode=True)) == "-" * 8

    def test_a_nan_still_draws_empty(self) -> None:
        assert bar_cells(math.nan, 8) == 0
        assert "█" not in _plain(bar(math.nan, "white", width=8))

    def test_a_zero_width_bar_is_still_empty(self) -> None:
        assert bar_cells(50.0, 0) == 0
        assert _plain(bar(50.0, "white", width=0)) == ""

    def test_an_over_range_value_is_still_clamped(self) -> None:
        assert bar_cells(250.0, 8) == 8
        assert _solid(250.0, 8)

    def test_the_unicode_path_is_untouched(self) -> None:
        # It already obeyed the rule; the fix must not have moved it.
        assert not _solid(98.0, 18)
        assert _solid(100.0, 18)
