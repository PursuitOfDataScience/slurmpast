import pytest

from slurmpast import duration
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


class TestAValueThatIsNotANumberIsNotAMeasurement:
    """`float("NaN")` and `float("1e999")` are floats Python builds happily.

    This module's opening rule is that a sentinel must yield None, "never 0.0 --
    a 0.0 here silently becomes 'this job used no time', which is a lie". A NaN is
    the same lie told about every job at once, because it propagates: one record
    whose Elapsed did not parse turned `gpu_hours_total` and `core_hours_total`
    for a whole history into `nan`, destroying every OTHER job's figure, and then
    raised ValueError out of `format_duration` on the job screen.

    Found by fuzzing the parser, not by reading it.
    """

    NOT_NUMBERS = ["NaN", "nan", "inf", "Infinity", "-inf", "1e999", "-1e999", "1e400"]

    @pytest.mark.parametrize("text", NOT_NUMBERS)
    def test_no_parser_returns_one_or_raises(self, text):
        for parse in (duration.parse_duration, duration.parse_bytes, duration.parse_cpu_freq):
            assert parse(text) is None, "%s(%r)" % (parse.__name__, text)

    @pytest.mark.parametrize("text", NOT_NUMBERS)
    def test_the_int_reader_in_sacct_agrees(self, text):
        """`int(float("inf"))` raises OverflowError, which is not a ValueError, so
        `except ValueError` did not catch it and the whole query died."""
        from slurmpast.sacct import _int

        assert _int(text) is None

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_no_formatter_raises_or_prints_one(self, value):
        assert duration.format_duration(value) == "n/a"
        assert duration.format_bytes(value) == "n/a"
        assert duration.format_percent(value) == "n/a"
        assert duration.format_cpu_freq(value) == "n/a"
        assert duration.format_mem_flag(value) is None

    def test_real_values_are_untouched(self):
        """The control: the guard must not reject anything finite, including the
        zero and the negative that other rules here deliberately allow through."""
        assert duration.parse_duration("01:52:49") == 6769.0
        assert duration.parse_duration("00:00.539") == 0.539
        assert duration.parse_duration("62-22:51:15") == 5439075.0
        assert duration.parse_bytes("53741792K") == 53741792 * 1024
        assert duration.parse_bytes("0") == 0
        assert duration.parse_cpu_freq("3.10M") == 3.1e9
        assert duration.format_duration(0.52) == "0.52s"
        assert duration.format_bytes(0) == "0 B"
        assert duration.format_percent(0.0) == "0.0%"


class TestTheUnitLadderNeverPrintsAFigureOfTenTwentyFour:
    """`format_bytes` chose its unit from the raw value, then rounded the figure.

    The two steps disagreed just under every boundary: `1073692672` is below
    1 GiB, so MiB was selected, and `%.1f` of `1023.99969...` reads `1024.0`.
    "1024.0 MiB" means the ladder failed -- the whole point of taking the largest
    unit above 1 is to stay *below* 1024.

    Not hypothetical. That value is a real `MaxRSS`, one of 13,426 distinct byte
    values in a 90-day window on this cluster, and it printed "1024.0 MiB".
    `slurmwatch.units.format_bytes` documents the identical case as its A5 and
    resolves it the same way; these are sibling tools reporting the same
    quantities, and they disagreed on this input.

    The ceiling was the same defect with no unit to promote INTO: with TiB on top,
    everything from ~1024 TiB up read "1024.0 TiB", "2048.0 TiB". No job has a
    petabyte of RAM, but `read_bytes`/`write_bytes`/`io_rate` come through here
    too and the largest real value in that window is 30.9 TiB of disk read, which
    puts 1 PiB a factor of 33 away rather than out of reach.
    """

    #: The measured record, and the boundary each unit sits just below.
    PROMOTES = [
        (1073692672, "1.0 GiB"),  # the real MaxRSS
        (1024**2 - 1, "1.0 MiB"),
        (1024**3 - 1, "1.0 GiB"),
        (1024**4 - 1, "1.0 TiB"),
        (1024**5 - 1, "1.0 PiB"),
    ]

    @pytest.mark.parametrize("value,expected", PROMOTES)
    def test_a_figure_that_would_round_to_1024_promotes(self, value, expected):
        assert format_bytes(value) == expected

    def test_no_near_boundary_value_prints_1024_or_more(self):
        """The invariant, swept rather than spot-checked.

        Stated as a property so a later change to the tier list or the format
        string cannot reintroduce it at one tier while fixing another.
        """
        import re

        offenders = []
        for exponent in range(10, 60):
            for delta in range(1, 200):
                value = 2**exponent - delta
                if value <= 0:
                    continue
                text = format_bytes(value)
                match = re.match(r"^([\d.]+) (B|KiB|MiB|GiB|TiB|PiB)$", text)
                assert match, (value, text)
                figure, unit = float(match.group(1)), match.group(2)
                # PiB is the top of the ladder: there is nothing above to promote
                # into, so it is the one unit allowed to exceed 1024.
                if unit != "PiB" and figure >= 1024.0:
                    offenders.append((value, text))
        assert offenders == [], offenders[:5]

    def test_the_two_sibling_tools_now_agree(self):
        """slurmwatch solved this first and documents it; they must not disagree.

        Skipped rather than failed if slurmwatch is not importable — it is a
        sibling checkout, not a dependency of this package.
        """
        import sys

        sys.path.insert(0, "/home/youzhi/slurmwatch/src")
        try:
            from slurmwatch.units import format_bytes as sibling
        except ImportError:  # pragma: no cover - sibling not checked out
            pytest.skip("slurmwatch not available")
        for value, _ in self.PROMOTES:
            mine, theirs = format_bytes(value), sibling(float(value))
            assert mine.split()[1] == theirs.split()[1], (value, mine, theirs)

    def test_bytes_remain_the_floor_below_one_kib(self):
        """CONTROL — passes in both states, and pins what the docstring promises.

        A promotion rule expressed as "round the figure to 1.0" would take 1000 B
        to "1.0 KiB", because 1000/1024 rounds to 1.0 at one decimal. The
        docstring requires bytes below 1 KiB and `0` as `0 B`, so the threshold is
        where `%.1f` flips to 1024.0, not where it flips to 1.0.
        """
        assert format_bytes(0) == "0 B"
        assert format_bytes(1) == "1 B"
        assert format_bytes(1000) == "1000 B"
        assert format_bytes(1023) == "1023 B"

    def test_the_ordinary_figures_are_untouched(self):
        """CONTROL — every value not near a boundary reads exactly as before."""
        assert format_bytes(1024) == "1.0 KiB"
        assert format_bytes(1536) == "1.5 KiB"
        assert format_bytes(1024**2) == "1.0 MiB"
        assert format_bytes(200 * 1024**2) == "200.0 MiB"
        assert format_bytes(4 * 1024**3) == "4.0 GiB"
        assert format_bytes(33935225257984) == "30.9 TiB"  # the real disk-read peak
        assert format_bytes(None) == "n/a"
