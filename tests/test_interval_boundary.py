"""A confidence interval could print an end as a boundary it had not reached.

`format_rate_range` built its own ``"%.1f – %.1f%%"`` instead of asking
`format_percent`, so it kept the defect `format_percent` was fixed for::

    format_rate_range(0.9996, 1.0)  ->  '100.0 – 100.0%'
    format_rate_range(0.0, 0.0004)  ->  '0.0 – 0.0%'

The claim in the wrong figure is the point, and it is a claim only at these two
values. ``100.0%`` of a failure rate means *nothing succeeded* and ``0.0%``
means *nothing failed* — each is where the reader stops looking — so printing
one for an end that is strictly inside the interval states a fact of a different
kind from the one measured. The same `%.1f` flip is what made `format_percent`
print "100.0% completed" for 2000 jobs with one failure.

**Only those two boundaries are fixed, and the docstring used to claim more.**
"A range whose two ends print identically says the measurement was exact" is not
true as a general rule, and this change does not make it true. Measured, with
the fix in place::

    format_rate_range(0.50001, 0.50009)  ->  '50.0 – 50.0%'
    format_rate_range(0.0006,  0.0009)   ->  '0.1 – 0.1%'

Those are left alone deliberately, and they are a different thing: an interior
tie is the printed *resolution*, the same one decimal place every ``50.0%`` in
this tool carries, and a reader who reads exactness into it is over-reading a
rounded figure rather than being told something false. Widening to ``%.2f`` to
close them would re-spell every interval the tool prints — the option round
fifty-six weighed and declined — and would only move the tie to the third
decimal. `format_percent` governs exactly the two bands where the rounded figure
changes the KIND of statement, and routing each end through it is the whole fix.

Round fifty-six found it, recorded it in `issues.md` under **Open — the same
defect one helper over, NOT fixed here**, and left it deliberately: "a range
shows both ends, so it needs its own decision about whether ``>99.9 – 100.0%``
reads better than widening the precision, and ``ci_range``'s spelling is pinned
in three places."

Both halves of that reason are answered rather than ignored:

* **The decision was already made.** `format_percent` renders a single value in
  [99.95%, 100%) as ``>99.9%`` — with three cases in its docstring arguing why a
  bound beats a wrong figure — so routing each end through it adds no fourth
  spelling and invents no precision. Widening to ``%.2f`` would change every
  interval the tool prints to answer one boundary.
* **The three pins do not move.** They are ``ci_range(0.757, 1.0)``,
  ``95% CI 72.2 – 100.0%`` and `test_interval_spelling`'s "``ci_range`` must not
  re-derive the format". The first two have ends that `format_percent` renders
  identically (the exact boundaries are still exact), and the third is about
  ownership, which is unchanged: `duration` still owns the one format.

The interesting surviving case is pinned below: when BOTH ends fall in the same
bounded band, the range reads ``>99.9 – >99.9%``. That is not the old defect
wearing a new hat — it says neither end reached 100%, which is true, where
``100.0 – 100.0%`` said both were exactly 100%, which was false.
"""

from __future__ import annotations

import asyncio

import pytest

from slurmpast.duration import format_percent, format_rate_range
from slurmpast.index import History
from slurmpast.model import Job
from slurmpast.nodes import node_table, wilson_interval
from slurmpast.render import ascii_fold
from slurmpast.report import Style, render_nodes

#: Failures on one node, enough of them that the Wilson lower bound lands in the
#: band `format_percent` renders as ``>99.9%``. Measured: `wilson_interval(n, n)`
#: first reaches 99.95% at **n = 7680**, so a table has to be about this big
#: before this package's own statistics will produce the interval at all. Rounded
#: up to 8000 for a little room, and building it costs ~0.13 s.
BOUNDARY_TRIALS = 8000
#: A second node, so the table has a leave-one-out comparison to make and both
#: renderers draw a full row rather than the "nothing to attribute" message.
CONTROL_TRIALS = 200


def _one_node_at_the_boundary() -> list[Job]:
    jobs = [
        Job(
            job_id="a%d" % i,
            name="w",
            node_list="nodeA",
            elapsed=600.0,
            timelimit=3600.0,
            state="FAILED",
        )
        for i in range(BOUNDARY_TRIALS)
    ]
    jobs += [
        Job(
            job_id="b%d" % i,
            name="w",
            node_list="nodeB",
            elapsed=600.0,
            timelimit=3600.0,
            state="COMPLETED",
        )
        for i in range(CONTROL_TRIALS)
    ]
    return jobs


def _boundary_row(jobs: list[Job]) -> tuple[float, float]:
    """``nodeA``'s interval, taken from the analysis rather than assumed."""
    table = node_table(jobs, workload="w", metric="failure")
    row = next(r for r in table["rows"] if r["node"] == "nodeA")
    return row["ci_low"], row["ci_high"]


def _nodes_screen_text(jobs: list[Job], size: tuple[int, int] = (120, 40)) -> str:
    """What the dashboard actually paints on the nodes screen, as plain lines.

    Through Textual's own harness, so this is the compositor's output rather
    than a reconstruction of it -- the same reason `test_audit` renders a screen
    instead of comparing source fragments. ``n`` opens the screen and ``m``
    turns the metric from hang to failure, which is the one these jobs populate.
    """
    pytest.importorskip("textual")
    from slurmpast import tui

    async def run() -> str:
        app = tui.SlurmpastApp(lambda: list(jobs), window="test", no_logs=True)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            for key in ("n", "m"):
                await pilot.press(key)
                await pilot.pause()
            await pilot.pause()
            return "\n".join(
                "".join(segment.text for segment in strip).rstrip()
                for strip in app.screen._compositor.render_strips()
            )

    return asyncio.run(run())


class TestAnIntervalIsNotFlattenedToABoundary:
    def test_the_reported_range_is_no_longer_degenerate(self) -> None:
        got = format_rate_range(0.9996, 1.0)
        assert got == ">99.9 – 100.0%", got
        low, high = got.rstrip("%").split(" – ")
        assert low != high, got

    @pytest.mark.parametrize(
        ("low", "high", "expected"),
        [
            (0.9996, 1.0, ">99.9 – 100.0%"),
            (0.99951, 1.0, ">99.9 – 100.0%"),
            (0.0, 0.0004, "0.0 – <0.1%"),
            (0.0001, 0.5, "<0.1 – 50.0%"),
        ],
    )
    def test_an_interior_end_gets_a_bound(self, low: float, high: float, expected: str) -> None:
        assert format_rate_range(low, high) == expected

    def test_both_ends_in_one_band_say_neither_reached_it(self) -> None:
        # True, where `100.0 – 100.0%` was false.
        assert format_rate_range(0.9995, 0.99999) == ">99.9 – >99.9%"

    @pytest.mark.parametrize(
        "value",
        [
            0.0,  # exact zero, and `format_percent` keeps it exact
            0.0004,  # the <0.1 band
            0.0006,  # one step out of it
            0.246,
            0.5,
            0.9994,  # one step below the >99.9 band
            0.9996,  # inside it
            1.0,  # exact one, kept exact
        ],
    )
    def test_each_end_is_spelled_the_way_a_single_value_is(self, value: float) -> None:
        """The property, asserted on OUTPUT rather than on source text.

        This used to read `duration.py` and assert ``"%.1f" not in`` the body of
        `format_rate_range` — which pins the implementation and detects a
        *reverted edit* rather than a wrong string, and would go red on a
        rewrite that spelled every band correctly. What the fix actually claims
        is that one helper decides how a percentage is spelled, so that is what
        is checked: each end of a range is byte-identical to `format_percent` of
        that end, across every band `format_percent` distinguishes. No
        independently derived ``%.1f`` can satisfy this, because it disagrees at
        both bounded bands.
        """
        one = format_percent(value)
        assert format_rate_range(value, value) == "%s – %s" % (one.rstrip("%"), one)

    def test_a_bounded_end_still_folds_for_ascii(self) -> None:
        # The new spelling has to survive `--ascii` like every other one.
        assert ascii_fold(format_rate_range(0.9996, 1.0)) == ">99.9 - 100.0%"

    def test_both_surfaces_print_the_bounded_interval(self) -> None:
        """Report's text table and the dashboard's cell, one job set, real renderers.

        This replaces ``ci_range(0.9996, 1.0) == format_rate_range(0.9996, 1.0)``,
        which was a tautology: `render.ci_range` is literally
        ``return format_rate_range(low, high)``, so it held with the fix
        reverted and could not fail for any input.

        Agreement alone still could not fail — both surfaces call the same
        helper either way — so the interval is driven into the bounded band by
        the DATA and the bounded spelling is what is asserted on both screens.
        8000 failures on one node is what it takes: `wilson_interval(8000, 8000)`
        is [99.952%, 100%], and 7680 is the smallest table for which this
        package's own statistics reach the band at all. Reverting the fix prints
        ``100.0 – 100.0%`` in both places instead — measured, on both surfaces.
        """
        jobs = _one_node_at_the_boundary()
        low, high = _boundary_row(jobs)
        cell = format_rate_range(low, high)
        assert cell == ">99.9 – 100.0%", (cell, low, high)
        text = render_nodes(History(jobs), metric="failure", style=Style(enabled=False))
        assert cell in text, text
        assert cell in _nodes_screen_text(jobs), cell


class TestControls:
    """Behaviour that must not change. Each passes in BOTH states."""

    @pytest.mark.parametrize(
        ("low", "high", "expected"),
        [
            (0.246, 0.577, "24.6 – 57.7%"),  # the docstring's own example
            (0.757, 1.0, "75.7 – 100.0%"),  # pinned in test_audit.py
            (0.722, 1.0, "72.2 – 100.0%"),  # pinned in the comparison note
            (0.0, 1.0, "0.0 – 100.0%"),
            (1.0, 1.0, "100.0 – 100.0%"),  # exact, and therefore true
            (0.0, 0.0, "0.0 – 0.0%"),
        ],
    )
    def test_every_previously_pinned_string_is_byte_identical(
        self, low: float, high: float, expected: str
    ) -> None:
        assert format_rate_range(low, high) == expected

    def test_the_en_dash_still_folds_to_a_hyphen_for_ascii(self) -> None:
        # `--ascii` and piped output must stay byte-identical to what they were.
        assert ascii_fold(format_rate_range(0.246, 0.577)) == "24.6 - 57.7%"
        assert ascii_fold(format_rate_range(0.757, 1.0)) == "75.7 - 100.0%"

    def test_the_percent_sign_is_still_only_at_the_end(self) -> None:
        for low, high in ((0.246, 0.577), (0.9996, 1.0), (0.0001, 0.5)):
            got = format_rate_range(low, high)
            assert got.count("%") == 1 and got.endswith("%"), got

    def test_ci_range_still_delegates_rather_than_formatting(self) -> None:
        import pathlib

        src = pathlib.Path("src/slurmpast/render.py").read_text()
        body = src[src.index("def ci_range") :].split("\n\n\n")[0]
        assert "format_rate_range" in body, body

    def test_the_single_value_helper_is_untouched(self) -> None:
        assert format_percent(1.0) == "100.0%"
        assert format_percent(0.0) == "0.0%"
        assert format_percent(0.9996) == ">99.9%"
        assert format_percent(0.0001) == "<0.1%"
        assert format_percent(None) == "n/a"

    def test_a_range_still_reads_low_to_high(self) -> None:
        got = format_rate_range(0.1, 0.9)
        assert got == "10.0 – 90.0%", got

    @pytest.mark.parametrize(
        ("low", "high", "expected"),
        [
            (0.50001, 0.50009, "50.0 – 50.0%"),
            (0.0006, 0.0009, "0.1 – 0.1%"),
            (0.12341, 0.12349, "12.3 – 12.3%"),
        ],
    )
    def test_an_interior_tie_is_left_alone(self, low: float, high: float, expected: str) -> None:
        """The limit of the fix, asserted rather than only described.

        Byte-identical with the fix present and with the local ``%.1f`` restored
        — which is what makes it a control AND the evidence that the module
        docstring's old wording ("a range whose two ends print identically says
        the measurement was exact") was wider than the change. An interval
        narrower than 0.05 pp still prints one figure twice; that is the
        resolution the whole tool prints percentages at, not a false claim about
        a boundary, and closing it would mean re-spelling every interval.
        """
        assert format_rate_range(low, high) == expected

    def test_the_boundary_fixture_really_reaches_the_band(self) -> None:
        """Otherwise the cross-surface test could pass on an ordinary interval.

        Asserted off `wilson_interval` directly, so it holds whatever
        `format_rate_range` does with the numbers.
        """
        low, high = wilson_interval(BOUNDARY_TRIALS, BOUNDARY_TRIALS)
        assert 0.9995 <= low < 1.0, low
        assert high == 1.0, high
        assert format_percent(low) == ">99.9%"
