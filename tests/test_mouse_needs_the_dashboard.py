"""`--mouse` is a dashboard preference, and every text mode now says so.

`args.mouse` is read at exactly one place — `tui.run(mouse=args.mouse)` — so in
`--plain`, `--json`, any section view or a named job it is a flag that was typed
and will not be used. Round 73's block two screens up warns for `-S/--since`,
`-E/--until` and `--all-users` under `--demo`; round 81's warns for `--log-dir`;
and `--steps` without a job id takes the stricter remedy for the same class,
with the reason stated at that line: *"It used to evaporate, so a caller who
forgot the id got the ordinary overview and no hint that the flag they typed did
nothing."*

A warning rather than an error, because the report asked for still arrives
exactly as asked — only the mouse preference is moot.

**The placement is the load-bearing part.** `if not _has_terminal(): args.plain
= True` degrades to text on a pipe, and is silent for a reason it states: "a
note on stdout would corrupt the very file being written, and one on stderr
would be noise in every CI log for a fallback that did what was wanted." The
check therefore reads `args.plain` BEFORE that assignment, so only an EXPLICIT
text mode counts. Measured: the first version sat after the degrade and
`--demo --mouse | cat` warned about a mouse the caller had never asked to drop.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

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


def _mouse_warnings(done: subprocess.CompletedProcess) -> int:
    return sum("mouse has no effect" in ln for ln in done.stderr.splitlines())


class TestEveryExplicitTextModeReportsIt:
    @pytest.mark.parametrize(
        "argv",
        [
            ["--plain"],
            ["--json"],
            ["--overview"],
            ["--patterns"],
            ["--nodes"],
            ["--sizing"],
            ["--plain", "--overview"],
        ],
        ids=lambda a: " ".join(a),
    )
    def test_it_says_the_flag_has_no_effect(self, argv: list[str]) -> None:
        done = _run(*argv, "--mouse")
        assert _mouse_warnings(done) == 1, done.stderr

    def test_the_reason_names_the_dashboard(self) -> None:
        """`--log-dir`'s warning says "(no logs are read)"; this one has to say
        what is missing here, not merely that something is."""
        done = _run("--plain", "--mouse")
        assert "without the dashboard" in done.stderr, done.stderr
        assert "text mode here" in done.stderr, done.stderr

    def test_it_is_on_stderr_and_json_still_parses(self) -> None:
        """Where the warning goes, not whether it exists — so it holds under the
        neuter too (no warning cannot corrupt stdout). Established by running
        it; the point it guards is that adding a diagnostic did not put one on
        the payload stream.
        """
        done = _run("--json", "--mouse")
        assert "mouse has no effect" not in done.stdout
        json.loads(done.stdout)

    def test_it_does_not_change_the_report(self) -> None:
        """The premise: the flag really is moot, so stdout must not move."""
        assert _run("--plain").stdout == _run("--plain", "--mouse").stdout


class TestControls:
    """Each passes with the whole block removed as well as with it.

    They cover the silence that must stay silent — including the one my own
    first attempt broke — and the sibling warnings this one sits beside.
    """

    def test_a_pipe_degrading_to_text_stays_silent(self) -> None:
        """The degrade sets `args.plain` itself and says why it must not speak.

        A control for "warn at all" — removing the block leaves this passing —
        and the regression guard for WHERE the block sits. The first version was
        placed after the degrade and reddened exactly here.
        """
        done = _run("--mouse")
        assert _mouse_warnings(done) == 0, done.stderr

    def test_no_mouse_flag_means_no_warning(self) -> None:
        for argv in (["--plain"], ["--json"], ["--overview"]):
            done = _run(*argv)
            assert _mouse_warnings(done) == 0, (argv, done.stderr)

    def test_the_log_dir_warning_still_has_its_own_wording(self) -> None:
        done = _run("--plain", "--log-dir", "/tmp")
        assert "--log-dir has no effect with --demo (no logs are read)" in done.stderr

    def test_the_demo_window_warning_still_fires(self) -> None:
        """Round 73's, which this one is modelled on and must not disturb."""
        done = _run("--plain", "-S", "now-1days")
        assert "has no effect with --demo" in done.stderr, done.stderr

    def test_steps_without_a_job_is_still_the_stricter_remedy(self) -> None:
        """The same class handled as an error, which this round does not change."""
        done = _run("--plain", "--steps")
        assert done.returncode == 2, done.stderr
        assert "needs a job id" in done.stderr, done.stderr
