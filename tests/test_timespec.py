"""sacct time-specification handling.

Found by running the installed command rather than the test suite: the default
window was `-7days`, which sacct **rejects** ("Invalid time specification"). Every
prior test used absolute dates, so a bare `slurmpast` -- the most common
invocation there is -- would have failed for every user.
"""

import pytest

from slurmpast.cli import build_parser, normalize_time_spec


class TestNormalizeTimeSpec:
    @pytest.mark.parametrize(
        "given,expected",
        [
            ("-7days", "now-7days"),
            ("-30days", "now-30days"),
            ("-1day", "now-1day"),
            ("-12hours", "now-12hours"),
            ("-2weeks", "now-2weeks"),
            ("-6months", "now-6months"),
            ("-90minutes", "now-90minutes"),
        ],
    )
    def test_bare_relative_gets_a_now_prefix(self, given, expected):
        assert normalize_time_spec(given) == expected

    def test_case_insensitive(self):
        assert normalize_time_spec("-7DAYS") == "now-7DAYS"

    def test_internal_space_tolerated(self):
        assert normalize_time_spec("-7 days") == "now-7days"

    @pytest.mark.parametrize(
        "given",
        [
            "now-7days",      # already valid
            "2026-07-01",     # absolute
            "2026-07-01T08:00:00",
            "today",
            "midnight",
            "noon",
            "07/01/26",
        ],
    )
    def test_valid_specs_are_left_alone(self, given):
        assert normalize_time_spec(given) == given

    def test_none_and_empty_pass_through(self):
        assert normalize_time_spec(None) is None
        assert normalize_time_spec("") == ""

    def test_not_fooled_by_a_negative_number_alone(self):
        """`-7` has no unit; sacct would read it as seconds, so do not rewrite."""
        assert normalize_time_spec("-7") == "-7"


class TestDefaultWindow:
    def test_default_since_is_a_spec_sacct_accepts(self):
        """The regression this file exists for: the default must not be `-7days`."""
        default = build_parser().parse_args([]).since
        assert default == "now-7days"
        assert not default.startswith("-")

    def test_default_survives_normalization_unchanged(self):
        default = build_parser().parse_args([]).since
        assert normalize_time_spec(default) == default


class TestArgparseStillAcceptsLeadingDash:
    """`-S -7days` must parse rather than dying at argparse, then be rewritten."""

    def test_short_option_with_dashed_value(self):
        from slurmpast.cli import _glue_negative_values

        args = build_parser().parse_args(_glue_negative_values(["-S", "-7days"]))
        assert normalize_time_spec(args.since) == "now-7days"

    def test_long_option_with_dashed_value(self):
        from slurmpast.cli import _glue_negative_values

        args = build_parser().parse_args(_glue_negative_values(["--since", "-30days"]))
        assert normalize_time_spec(args.since) == "now-30days"
