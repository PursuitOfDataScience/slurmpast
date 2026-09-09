"""`--demo` drops a window and an audience, and now says so.

`TestADroppedFlagIsReported` (round 81) established the rule and the wording:
a flag that was asked for and will not be used earns a **warning on stderr**,
not silence and not an error — "`--all-users -u you` has been refused since
round eighteen ('ask for different things; pick one') and the sibling package
warns for the no-effect shape ('--append has no effect without --log;
ignoring')". That round fixed `--no-logs --log-dir X`, and it explicitly named
`--demo` as the same case by a different route: "it sets `no_logs` itself ... so
`--demo --log-dir X` was equally silent."

Two more flags reach `--demo` by that same route and were still silent:

* **`-S/--since` and `-E/--until`.** Both render sites read
  `"synthetic demo data" if args.demo else humanize_window(...)`, and the query
  gets `since=None if (args.demo or args.until)`. Measured: `--demo
  -S now-1days` and `--demo -S now-365days` produce output byte-identical to
  `--demo` alone.
* **`--all-users`.** The tape is 58 jobs belonging to one synthetic user
  (`demo.history()` yields exactly one), so there is nobody to widen to.

The warning is on **stderr**, so `--json` still parses and `--plain` is
byte-identical — both checked here, because a diagnostic on stdout would
corrupt the payload this package is scripted through.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from slurmpast.cli import build_parser

ROOT = __file__.rsplit("/tests/", 1)[0]


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "slurmpast", "--demo", *args],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=ROOT,
        env={
            "PYTHONPATH": ROOT + "/src",
            "NO_COLOR": "1",
            "COLUMNS": "120",
            "PATH": "/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )


class TestTheDroppedFlagsAreNamed:
    @pytest.mark.parametrize(
        "argv,flag",
        [
            (["-S", "now-1days"], "-S/--since"),
            (["--since", "now-365days"], "-S/--since"),
            (["-E", "now"], "-E/--until"),
            (["--all-users"], "--all-users"),
        ],
    )
    def test_each_one_says_it_has_no_effect(self, argv: list[str], flag: str) -> None:
        done = _run("--plain", *argv)
        assert "has no effect with --demo" in done.stderr, done.stderr
        assert flag in done.stderr, done.stderr

    def test_several_at_once_are_one_line(self) -> None:
        """One sentence naming both, matching how `--log-dir` lists its values."""
        done = _run("--plain", "-S", "now-1days", "--all-users")
        lines = [ln for ln in done.stderr.splitlines() if "no effect with --demo" in ln]
        assert len(lines) == 1, done.stderr
        assert "-S/--since" in lines[0] and "--all-users" in lines[0], lines[0]

    def test_the_reason_is_given_not_just_the_verdict(self) -> None:
        """`--log-dir`'s warning says "(no logs are read)"; this one has to say
        why a window and an audience cannot apply either."""
        done = _run("--plain", "--all-users")
        assert "fixed tape" in done.stderr, done.stderr
        assert "one user" in done.stderr, done.stderr


class TestItDoesNotCorruptTheOutput:
    def test_the_warning_is_on_stderr_and_json_still_parses(self) -> None:
        done = _run("--json", "--all-users")
        assert "has no effect" in done.stderr
        assert "has no effect" not in done.stdout
        json.loads(done.stdout)

    def test_the_plain_view_is_byte_identical(self) -> None:
        """The flag really is a no-op, which is the PREMISE of warning at all --
        and therefore a control, not a finding test. Established by running the
        neuter: it holds with the warning block removed, because removing a
        warning does not make a dropped flag start working. If it ever reddens,
        the flag has an effect and the warning is the thing that is wrong.
        """
        assert _run("--plain").stdout == _run("--plain", "-S", "now-1days").stdout


class TestControls:
    """Each passes with the new warning block removed as well as with it.

    Verified by running that neuter -- they cover the silence that must stay
    silent and the sibling warning this one was modelled on.
    """

    def test_a_bare_demo_run_warns_about_nothing(self) -> None:
        done = _run("--plain")
        assert "has no effect" not in done.stderr, done.stderr

    def test_the_default_window_spelled_out_is_not_reported(self) -> None:
        """Compared against the parser's own default, so `--demo` alone does not
        warn. The cost is that typing the default explicitly is indistinguishable
        from not typing it -- argparse has no record of which happened without a
        sentinel default, and changing the default to one is a wider change than
        this warning is worth."""
        default = build_parser().get_default("since")
        done = _run("--plain", "-S", default)
        assert "-S/--since" not in done.stderr, done.stderr

    def test_the_log_dir_warning_still_fires_with_its_own_wording(self) -> None:
        """Round 81's warning, which this one sits beside and must not disturb."""
        done = _run("--plain", "--log-dir", "/tmp")
        assert "--log-dir has no effect with --demo (no logs are read)" in done.stderr
        assert "ignoring /tmp" in done.stderr

    def test_the_warning_is_scoped_to_demo(self) -> None:
        """Without `--demo` the window is not dropped, so nothing is reported.

        Asserted on the ABSENCE of this warning and on the exit code, not on
        what a real run says: with no `sacct` on PATH the run stops earlier with
        "cannot execute sacct", which is the correct message and is exactly the
        environment a CI runner has. A control that needed a live scheduler
        would pass here only because this host is a cluster -- the inverse of a
        runner, and a defect class this family has shipped before.
        """
        done = subprocess.run(
            [sys.executable, "-m", "slurmpast", "--json", "-S", "not-a-date"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=ROOT,
            env={
                "PYTHONPATH": ROOT + "/src",
                "NO_COLOR": "1",
                "PATH": "/usr/bin:/bin",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        assert done.returncode == 2, done.stderr
        assert "has no effect with --demo" not in done.stderr, done.stderr
