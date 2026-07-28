"""AveCPUFreq is not interpretable as printed.

On this cluster the same 3.1 GHz part reports ``3.10M`` on 935 records and
``3.10G`` on 342 -- Slurm applies the magnitude suffix to a kHz base in some code
paths and a Hz base in others, so the string is ambiguous by a factor of 1000.
The tool used to print it verbatim, which showed users things like
``frequency 188K``: a number that means nothing and invites a false reading.
"""

import pytest

from slurmpast.duration import format_cpu_freq, parse_cpu_freq


class TestAmbiguousUnitBase:
    def test_mega_suffix_resolves_to_gigahertz(self):
        """3.10M is 3.10 million kHz = 3.10 GHz."""
        assert parse_cpu_freq("3.10M") == pytest.approx(3.10e9)

    def test_giga_suffix_resolves_to_the_same_clock(self):
        """The same CPU also reports 3.10G. Both must land on 3.10 GHz."""
        assert parse_cpu_freq("3.10G") == pytest.approx(3.10e9)

    def test_both_spellings_agree(self):
        assert parse_cpu_freq("3.10M") == parse_cpu_freq("3.10G")


class TestPlausibleValuesSurvive:
    @pytest.mark.parametrize(
        "given,hz",
        [("3.60M", 3.60e9), ("3M", 3.0e9), ("2.50M", 2.50e9), ("3.34M", 3.34e9)],
    )
    def test_typical_clocks(self, given, hz):
        assert parse_cpu_freq(given) == pytest.approx(hz)

    def test_a_downclocked_core_is_kept_because_it_is_a_signal(self):
        """800 MHz is low but real -- a core that idled at its floor."""
        assert parse_cpu_freq("800K") == pytest.approx(800e6)
        assert "MHz" in format_cpu_freq(parse_cpu_freq("800K"))


class TestImplausibleValuesAreDropped:
    @pytest.mark.parametrize("given", ["188K", "14K", "196K", "0", "", None, "garbage"])
    def test_omitted_rather_than_shown(self, given):
        """No CPU runs at 14 MHz. Printing it would be worse than printing nothing."""
        assert parse_cpu_freq(given) is None

    def test_absurdly_high_is_a_unit_error_not_a_clock(self):
        assert parse_cpu_freq("3.10T") is None

    def test_formatter_renders_none_as_na_never_zero(self):
        assert format_cpu_freq(None) == "n/a"


class TestSurfacedOnlyWhenTrustworthy:
    def _job(self, freq):
        from tests.conftest import row
        from slurmpast.sacct import parse

        return parse(
            "\n".join(
                [
                    row(
                        JobID="700",
                        JobName="w",
                        State="COMPLETED",
                        ElapsedRaw="3600",
                        End="2026-07-01T01:00:00",
                        AllocTRES="cpu=4,mem=64G,node=1",
                        AllocCPUS="4",
                    ),
                    row(
                        JobID="700.batch",
                        JobName="batch",
                        State="COMPLETED",
                        ElapsedRaw="3600",
                        TotalCPU="01:00:00",
                        CPUTimeRAW="14400",
                        AveCPUFreq=freq,
                        MaxRSS="1000K",
                    ),
                ]
            )
        )[0]

    def test_job_exposes_resolved_hertz(self):
        assert self._job("3.10M").cpu_freq_hz == pytest.approx(3.10e9)

    def test_untrustworthy_value_yields_none(self):
        assert self._job("188K").cpu_freq_hz is None

    def test_section_shows_a_real_clock(self):
        from slurmpast.render import job_sections

        rows = dict(
            (label, value)
            for _, block in job_sections(self._job("3.10M"))
            for label, value, _ in block
        )
        assert "avg clock" in rows
        assert "3.10 GHz" in rows["avg clock"]

    def test_section_omits_an_unusable_one(self):
        from slurmpast.render import job_sections

        labels = [label for _, block in job_sections(self._job("14K")) for label, _v, _b in block]
        assert "avg clock" not in labels

    def test_downclocking_is_called_out(self):
        from slurmpast.render import job_sections

        rows = dict(
            (label, value)
            for _, block in job_sections(self._job("800K"))
            for label, value, _ in block
        )
        assert "downclocked" in rows["avg clock"]
