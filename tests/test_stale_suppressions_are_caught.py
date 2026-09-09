"""A `# noqa` claims the line has a known violation, and the gate now checks it.

Every other claim in this repo is checked by something. The suppressions were
not, and nine had gone stale: `conftest.py`, `test_readability.py`,
`test_tui.py` and `test_ui_usability.py` each carried `# noqa: E402` on imports
that follow a `sys.path.insert`, and ruff does not flag them. `E402` IS in the
select list and `per-file-ignores` for `tests/*` is `["ARG"]` only, so nothing
was exempting them -- the directives simply suppressed nothing while telling a
reader those lines were known exceptions.

All nine were BARE: `# noqa: E402` with no rationale after it. That mattered to
the decision. The same sweep found stale directives in `nodetop` and `rapidu`
that all carry a reviewer's note -- `# noqa: S603 - fixed argv, never a shell`,
`# noqa: BLE001  (a hang is worse than a report)` -- and enabling this rule
there would demand deleting the note to satisfy the linter. It was not enabled
there, on purpose.

**Measured on both ends of the dev bound before removing anything.** The bound
is `ruff>=0.15,<0.17` and CI resolves the upper end; 0.15.18 and 0.16.6 agree on
all nine. This repo's `select` comment records the version spread biting once
already (0.16 surfaced 206 findings a local 0.15 run never saw), so a directive
one version calls unused can be load-bearing on another.

With `RUF100` selected the gate keeps them honest, so nothing here re-implements
`ruff check`. What is pinned is that the rule stays selected, plus one
end-to-end check that it does catch a planted stale directive.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The codes that were selected before this round, which must survive it.
ESTABLISHED = ["E", "F", "W", "I", "N", "UP", "B", "SIM", "ARG", "C4", "T20"]


def _codes(pattern: str) -> list[str]:
    """The string list on the single `pyproject.toml` line matching `pattern`.

    Read with a regex rather than `tomllib`, which is stdlib only from 3.11
    while this package's floor is `requires-python = ">=3.10"`. slurmpast's
    `TestNothingImportsPastTheDeclaredPythonFloor` catches exactly that and it
    caught this file; slurmwatch has no such test, so the same import passed
    its gate while being unrunnable on the floor it declares. Every value
    needed here is a single line, so a parser is not required to read one.
    """
    text = (ROOT / "pyproject.toml").read_text()
    match = re.search(pattern + r"\s*=\s*\[([^\]]*)\]", text)
    assert match is not None, pattern
    return re.findall(r'"([^"]+)"', match.group(1))


class TestTheRuleIsSelected:
    def test_ruf100_is_in_the_select_list(self) -> None:
        selected = _codes("select")
        assert "RUF100" in selected, selected

    def test_no_bare_noqa_survives_in_the_tree(self) -> None:
        """The nine that were removed, as a property rather than a count.

        A directive with a note after it is a reviewer's record and is allowed;
        a bare one is the shape that went stale here.

        This round has two halves and this test guards only one of them. It is
        the finding test for the CLEANUP -- it reddens if a bare directive comes
        back -- and a CONTROL for the config change, since dropping `RUF100`
        from the select list leaves the tree just as clean. Established by
        running that neuter, not by choosing a name.
        """
        offenders = []
        here = pathlib.Path(__file__).resolve()
        for path in sorted(ROOT.glob("tests/*.py")) + sorted(ROOT.glob("src/slurmpast/*.py")):
            # THIS file quotes the directive it scans for, in the classifier and
            # in the control below. A source-scanning test that does not exclude
            # itself finds its own explanation -- the third time that shape has
            # bitten in this campaign.
            if path.resolve() == here:
                continue
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if "# noqa:" not in line:
                    continue
                tail = line.split("# noqa:", 1)[1].strip()
                code = tail.split()[0] if tail else ""
                if tail == code:  # nothing but the code
                    offenders.append(f"{path.name}:{number}")
        assert offenders == [], offenders

    @pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not on PATH")
    def test_a_planted_stale_directive_is_reported(self, tmp_path) -> None:
        """The behavioural half: the rule actually fires, under this config."""
        planted = tmp_path / "planted.py"
        planted.write_text("x = 1  # noqa: E402\n")
        result = subprocess.run(
            [
                "ruff",
                "check",
                "--config",
                str(ROOT / "pyproject.toml"),
                "--output-format",
                "concise",
                str(planted),
            ],
            capture_output=True,
            text=True,
        )
        assert "RUF100" in result.stdout, (result.stdout, result.stderr)


class TestControls:
    """Each passes with `RUF100` removed from the select list as well as with it.

    They cover the configuration the change did not touch, so a neuter that
    reddens one of them means more moved than the one code -- verified by
    running it.
    """

    def test_every_previously_selected_code_is_still_there(self) -> None:
        for code in ESTABLISHED:
            assert code in _codes("select"), code

    def test_the_ignore_list_is_unchanged(self) -> None:
        """`UP031` is a recorded, deliberate exemption; this round is not about it."""
        assert _codes("ignore") == ["UP031"]

    def test_the_tests_exemption_is_still_arg_only(self) -> None:
        """Because it is what proves `E402` was never exempted for `tests/`."""
        assert _codes(r'"tests/\*"') == ["ARG"]

    def test_a_noted_directive_would_be_allowed(self) -> None:
        """The distinction the sweep turned on, asserted on the classifier rather
        than on the tree: a code followed by a note is not a bare directive."""
        for line, bare in [
            ("x = 1  # noqa: E402", True),
            ("x = 1  # noqa: S603 - fixed argv, never a shell", False),
            ("x = 1  # noqa: BLE001  (a hang is worse than a report)", False),
        ]:
            tail = line.split("# noqa:", 1)[1].strip()
            assert (tail == tail.split()[0]) is bare, line

    def test_the_config_reader_actually_finds_the_list(self) -> None:
        """Vacuity guard: every assertion above rests on `_codes`, and a
        regex that matched nothing would make them all pass trivially -- the
        helper asserts a match, and this checks the match is the real list."""
        selected = _codes("select")
        assert len(selected) >= 11, selected
        assert "E" in selected and "F" in selected
