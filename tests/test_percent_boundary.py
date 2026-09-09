"""`format_percent` named a boundary it had not reached, and the boundary is a claim.

The rule is stated twice in `duration.py` already -- `format_bytes` says "the unit
is chosen for the value as PRINTED, not as stored" and keeps `_ROUNDS_UP_AT` to
enforce it, and `format_duration` was fixed in round fifty-two for breaking it
(59.95s printing "60.0s"). `format_percent`, in the same module, did not follow it:
`%.1f` flips to `100.0` at 99.95 and to `0.0` below 0.05.

For a percentage the boundary is not a cosmetic slip, because both ends are read as
statements about whether anything happened:

    report.py:533   format_percent(stats["completion_rate"]) + " completed"
    tui.py:1053     the same line on the dashboard
    render.py:1393  format_percent(job.walltime_used)

Measured: from **2000 jobs with a single failure** the completion rate is 0.9995 and
the line reads "100.0% completed"; at the 13,051 parent jobs a 30-day window holds
on this cluster, one failure gives 0.999923 and reads the same. At the other end one
failure in 13,051 is 0.0077%, which printed "0.0%" -- so that string meant both
"none" and "some, but under a tenth", the ambiguity the function's own `n/a` rule
refuses for a failed read.

An interior value now gets a BOUND (`>99.9%`, `<0.1%`) rather than a wrong figure.
That is the spelling the sibling tools already use for "nonzero but below the
resolution" -- `rapidu.fmt` returns `<0.01x`, `nodetop.core.duration` returns `<1m`
-- and it invents no precision, which printing "0.1%" for 0.0077% would.
"""

import re

import pytest

from slurmpast.duration import format_percent
from slurmpast.index import History
from slurmpast.model import Job
from slurmpast.report import Style, render_overview


def _jobs(total, failures, name="w"):
    """``total`` runs of one workload, ``failures`` of them FAILED."""
    out = []
    for index in range(total):
        out.append(
            Job(
                job_id="%d" % (index + 1),
                name=name,
                partition="test",
                user="me",
                node_list="node-a",
                elapsed=600.0,
                timelimit=3600.0,
                state="FAILED" if index < failures else "COMPLETED",
            )
        )
    return out


class TestTheBoundaryIsNotNamedFromInside:
    @pytest.mark.parametrize("value", [1e-12, 1e-9, 1 / 13051, 0.0004, 0.00049])
    def test_a_nonzero_share_under_a_tenth_is_bounded_not_zeroed(self, value):
        assert format_percent(value) == "<0.1%"

    @pytest.mark.parametrize("value", [0.9995, 0.9996, 0.999923, 0.9999999])
    def test_a_share_under_everything_is_bounded_not_rounded_up(self, value):
        assert format_percent(value) == ">99.9%"

    def test_the_naive_formatting_really_did_name_the_boundary(self):
        """Vacuity guard: the band has to be one `%.1f` gets wrong, or the two
        cases above would pass against any implementation at all."""
        for value in (1 / 13051, 0.0004):
            assert "%.1f%%" % (100.0 * value) == "0.0%"
        for value in (0.9995, 0.999923):
            assert "%.1f%%" % (100.0 * value) == "100.0%"

    def test_the_bound_fits_the_narrowest_column_that_shows_it(self):
        """`MEM%` is six cells wide and takes `format_percent` directly, so a
        bound that overran it would push the row rather than fix a claim."""
        assert len(">99.9%") == 6
        assert len("<0.1%") == 5


class TestTheClaimOnTheRenderedOverview:
    """End to end, because the formatter is not what a reader complains about."""

    def test_one_failure_in_two_thousand_is_not_reported_as_all_completed(self):
        text = render_overview(History(_jobs(2000, 1)), style=Style(enabled=False))
        line = next(ln for ln in text.splitlines() if "completed" in ln)
        assert "100.0% completed" not in line, line
        assert ">99.9% completed" in line, line

    def test_the_failure_is_still_visible_beside_the_rate(self):
        """The rate is not the only figure on that line, and this pins that the
        fix did not merely make the wrong number vaguer: the run that failed is
        counted somewhere the reader can see."""
        text = render_overview(History(_jobs(2000, 1)), style=Style(enabled=False))
        assert "2000" in text
        assert re.search(r"\b1\b", text), text


class TestControls:
    """The exact boundaries are TRUE, and two tests already pinned them."""

    def test_control_an_exact_zero_still_prints_zero(self):
        assert format_percent(0.0) == "0.0%"
        assert format_percent(0) == "0.0%"

    def test_control_an_exact_one_still_prints_one_hundred(self):
        assert format_percent(1.0) == "100.0%"
        assert format_percent(1) == "100.0%"

    def test_control_a_genuinely_all_completed_window_still_says_so(self):
        text = render_overview(History(_jobs(2000, 0)), style=Style(enabled=False))
        assert "100.0% completed" in text

    @pytest.mark.parametrize(
        ("value", "shown"),
        [
            (0.0005, "0.1%"),
            (0.004, "0.4%"),
            (0.04, "4.0%"),
            (0.569, "56.9%"),
            (0.9994, "99.9%"),
            (1.026, "102.6%"),
            (2.0, "200.0%"),
            (-0.1, "-10.0%"),
        ],
    )
    def test_control_every_ordinary_value_is_unchanged(self, value, shown):
        """Including the two the fix must not have swallowed: 0.0005 is the first
        value that rounds to a real 0.1%, and 0.9994 the last that rounds to a
        real 99.9%. Over-100% stays as it is -- MEM% reads 102.6% for a job that
        exceeded its request, and that is a measurement, not an overflow."""
        assert format_percent(value) == shown

    def test_control_a_missing_reading_is_still_not_a_number(self):
        assert format_percent(None) == "n/a"
        assert format_percent(float("nan")) == "n/a"
        assert format_percent(float("inf")) == "n/a"

    def test_control_the_confidence_interval_range_is_untouched(self):
        """`format_rate_range` builds its own string and does not call
        `format_percent`, so the interval's spelling -- pinned elsewhere as
        "75.7 – 100.0%" -- cannot have moved. Asserted rather than assumed,
        because putting the bound in the shared helper would have moved it."""
        from slurmpast.duration import format_rate_range

        assert format_rate_range(0.757, 1.0) == "75.7 – 100.0%"
        # NOT pinning the interior band here. `format_rate_range(0.9996, 1.0)`
        # reads "100.0 – 100.0%" today, which is the same boundary defect one
        # helper over -- an interval of [99.96%, 100%] presented as a degenerate
        # one. Writing that string into an assertion would pin the bug, which is
        # this suite's named failure mode, and the fix is not the same one: a
        # range shows both ends, so it needs its own decision about whether
        # ">99.9 – 100.0%" reads better than widening the precision. Left open in
        # `issues.md` rather than blessed here.
        assert format_rate_range(0.9996, 1.0).endswith("%")
