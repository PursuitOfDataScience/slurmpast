import pytest

from slurmpast.duration import (
    format_bytes,
    format_duration,
    format_percent,
    mem_scope,
    parse_bytes,
    parse_duration,
)


class TestParseDuration:
    def test_hms(self):
        assert parse_duration("01:52:49") == 6769.0

    def test_days(self):
        assert parse_duration("1-12:00:00") == 129600.0

    def test_two_digit_days(self):
        # job 50108238's stale elapsed
        assert parse_duration("62-22:51:15") == 62 * 86400 + 22 * 3600 + 51 * 60 + 15

    def test_mm_ss_millis_is_not_hours(self):
        """The trap: 00:00.539 is half a second of CPU, not 39 seconds and not 30 minutes.

        Read as HH:MM this becomes 0, and read as MM:SS.mmm scaled wrong it becomes
        huge. Either way the hung-job diagnosis inverts.
        """
        assert parse_duration("00:00.539") == pytest.approx(0.539)

    def test_mm_ss_millis_larger(self):
        # job 46893309: 30 minutes 30.919 seconds of real CPU work
        assert parse_duration("30:30.919") == pytest.approx(30 * 60 + 30.919)

    def test_zero_time(self):
        assert parse_duration("00:00:00") == 0.0

    @pytest.mark.parametrize(
        "text", ["UNLIMITED", "INVALID", "Partition_Limit", "", "   ", "Unknown", "None"]
    )
    def test_sentinels_are_none_not_zero(self, text):
        """A 0.0 here would read as 'the job used no time', which is a different claim."""
        assert parse_duration(text) is None

    def test_none_input(self):
        assert parse_duration(None) is None

    def test_garbage(self):
        assert parse_duration("not-a-time") is None
        assert parse_duration("1:2:3:4") is None

    def test_bare_seconds(self):
        assert parse_duration("45") == 45.0


class TestParseBytes:
    def test_kibibytes(self):
        # MaxRSS from job 43742638 -- 51.25 GiB
        assert parse_bytes("53741792K") == 53741792 * 1024

    def test_gibibytes_per_node(self):
        assert parse_bytes("40Gn") == 40 * 1024**3

    def test_mebibytes_per_cpu(self):
        assert parse_bytes("3810Mc") == 3810 * 1024**2

    def test_no_suffix(self):
        assert parse_bytes("80G") == 80 * 1024**3

    def test_bare_number(self):
        assert parse_bytes("1024") == 1024

    def test_fractional(self):
        assert parse_bytes("1.5G") == int(1.5 * 1024**3)

    @pytest.mark.parametrize("text", ["", "Unknown", None, "n/a"])
    def test_missing_is_none(self, text):
        assert parse_bytes(text) is None


class TestMemScope:
    def test_per_node(self):
        assert mem_scope("40Gn") == "node"

    def test_per_cpu(self):
        assert mem_scope("3810Mc") == "cpu"

    def test_absent(self):
        assert mem_scope("80G") is None


class TestFormatting:
    def test_none_renders_na_not_zero(self):
        assert format_duration(None) == "n/a"
        assert format_bytes(None) == "n/a"
        assert format_percent(None) == "n/a"

    def test_subsecond_keeps_precision(self):
        """0.54s must not round to 0s -- that is the whole hung-job signal."""
        assert format_duration(0.539) == "0.54s"

    def test_minutes(self):
        """Slurm's own notation, not this tool's: sacct prints "01:52:49" and
        --time= accepts it, so "30m26s" made the reader translate."""
        assert format_duration(1826) == "00:30:26"

    def test_hours(self):
        assert format_duration(6769) == "01:52:49"

    def test_days(self):
        assert format_duration(129600) == "1-12:00:00"

    def test_it_round_trips_through_the_parser(self):
        """The strongest check that the format really is Slurm's: our own parser,
        written against sacct output, reads back what we print."""
        from slurmpast.duration import parse_duration

        for seconds in (60, 1826, 6769, 129600, 3600, 86399):
            assert parse_duration(format_duration(seconds)) == seconds

    def test_a_walltime_suggestion_matches_the_display(self):
        """--sizing emitted "--time=09:45:00" while the display said "9h45m00s"."""
        from slurmpast.sizing import _fmt_walltime

        assert _fmt_walltime(35100) == format_duration(35100)

    def test_fixed_width_so_columns_align(self):
        widths = {len(format_duration(s)) for s in (60, 1826, 6769, 86399)}
        assert widths == {8}

    def test_bytes(self):
        assert format_bytes(53741792 * 1024) == "51.3 GiB"

    def test_percent(self):
        assert format_percent(0.9228) == "92.3%"

    def test_zero_is_distinguishable_from_none(self):
        assert format_percent(0.0) == "0.0%"
        assert format_percent(None) == "n/a"
