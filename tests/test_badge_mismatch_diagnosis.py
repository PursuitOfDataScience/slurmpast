"""The badge failure says WHICH of two opposite causes it is.

`test_the_test_badge_matches_the_suite` compares the README badge against a live
`--collect-only`. Two very different things produce a mismatch, and they want
opposite actions:

* the badge is stale — somebody added tests and did not bump it. That is the case
  the test's own docstring records ("`tests-1029` sat in the README for two
  rounds"), and the fix is to bump the badge.
* the working tree holds test files that are not committed. Then the badge is
  *correct* for the suite that ships, the failure is expected locally, and CI is
  green. Bumping the badge would **red CI** — the opposite of the fix.

The message used to be `"README says N tests, the suite collects M"`, which cannot
tell them apart. This repo has been in the second state for many rounds, and
`issues.md` has carried it as an open item since round fifty-three while every round
re-derived the explanation by hand.

Pinned here as a helper rather than by asserting on another test's failure text, so
both branches are reachable without arranging a git state.
"""

import pathlib
import shutil
import subprocess

from tests.test_layout import _badge_mismatch_reason, _untracked_test_files

ROOT = pathlib.Path(__file__).resolve().parent.parent
UNTRACKED = ["tests/test_a.py", "tests/test_b.py", "tests/test_c.py", "tests/test_d.py"]


class TestTheReasonNamesTheCause:
    def test_untracked_files_are_named_as_the_benign_cause(self) -> None:
        reason = _badge_mismatch_reason(1969, 2174, UNTRACKED)
        assert "untracked" in reason, reason
        assert "4 test file(s)" in reason, reason
        # And the action, which is the opposite of the stale case.
        assert "red CI" in reason, reason
        assert "stale" not in reason, reason

    def test_the_file_list_is_elided_rather_than_dumped(self) -> None:
        reason = _badge_mismatch_reason(1969, 2174, UNTRACKED)
        assert "tests/test_a.py" in reason and "..." in reason, reason
        assert "tests/test_d.py" not in reason, reason

    def test_with_nothing_untracked_it_says_the_badge_is_stale(self) -> None:
        reason = _badge_mismatch_reason(1029, 2174, [])
        assert "stale" in reason and "2174" in reason, reason
        assert "untracked" not in reason, reason

    def test_a_badge_ahead_of_the_suite_is_also_stale_not_untracked(self) -> None:
        """Untracked files can only make the live count LARGER, never smaller."""
        reason = _badge_mismatch_reason(3000, 2174, UNTRACKED)
        assert "stale" in reason, reason
        assert "untracked" not in reason, reason

    def test_agreement_produces_no_reason_at_all(self) -> None:
        assert _badge_mismatch_reason(2174, 2174, UNTRACKED) == ""


class TestTheUntrackedProbe:
    def test_whatever_it_reports_here_is_genuinely_untracked(self) -> None:
        """Read against this checkout, in whichever of the two states it is in.

        The first version of this test asserted the probe could see *this file* --
        true only while the file was uncommitted, and false the moment the round
        landed. A test that can only pass before its own commit reds CI on the
        commit that adds it, which is the same "expected locally, broken on a
        runner" shape the module above exists to explain. What is pinned instead
        is the property that holds in both states; the positive case is arranged
        in a scratch repository below rather than borrowed from this one.
        """
        found = _untracked_test_files(ROOT)
        assert all(f.startswith("tests/") and f.endswith(".py") for f in found), found
        assert all((ROOT / f).is_file() for f in found), found
        tracked = subprocess.run(
            ["git", "ls-files", "--", "tests/"], cwd=ROOT, capture_output=True, text=True
        )
        if tracked.returncode == 0:
            assert not set(found) & set(tracked.stdout.splitlines()), found

    def test_an_untracked_test_file_is_found(self, tmp_path: pathlib.Path) -> None:
        """The positive case, on a repository this test builds itself.

        Also gives the `.py` filter teeth: an untracked non-Python file under
        `tests/` is reported by `git ls-files --others` and must not survive the
        helper, because the count in the badge is a count of test modules.
        """
        if shutil.which("git") is None:
            # No git, no arrangement -- and then the documented degradation is
            # the only behaviour there is to assert.
            assert _untracked_test_files(tmp_path) == []
            return
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_tracked.py").write_text("")
        (tmp_path / "tests" / "test_untracked.py").write_text("")
        (tmp_path / "tests" / "fixture.txt").write_text("")
        git = [
            "git",
            "-c",
            "user.email=nobody@example.invalid",
            "-c",
            "user.name=nobody",
            "-c",
            "commit.gpgsign=false",
        ]
        for argv in (
            ["init", "-q"],
            ["add", "tests/test_tracked.py"],
            ["commit", "-qm", "one tracked test"],
        ):
            done = subprocess.run(
                [*git, *argv], cwd=tmp_path, capture_output=True, text=True, timeout=60
            )
            assert done.returncode == 0, (argv, done.stdout, done.stderr)
        assert _untracked_test_files(tmp_path) == ["tests/test_untracked.py"]

    def test_it_degrades_to_empty_outside_a_repository(self, tmp_path: pathlib.Path) -> None:
        """No git, no claim: the caller then uses the plain "bump it" wording."""
        assert _untracked_test_files(tmp_path) == []


class TestControls:
    """These read neither helper, so they hold with the diagnosis in or out."""

    def test_the_readme_still_carries_a_test_badge(self) -> None:
        import re

        assert re.search(r"tests-(\d+)-brightgreen", (ROOT / "README.md").read_text())

    def test_the_badge_still_states_the_committed_count(self) -> None:
        # The rule the diagnosis explains, asserted independently of it: the badge
        # must equal what HEAD collects, which is what CI runs.
        import re

        badge = re.search(r"tests-(\d+)-brightgreen", (ROOT / "README.md").read_text())
        assert badge
        shown = subprocess.run(
            ["git", "show", "HEAD:README.md"], cwd=ROOT, capture_output=True, text=True
        )
        if shown.returncode != 0:
            return  # not a checkout; nothing to compare against
        at_head = re.search(r"tests-(\d+)-brightgreen", shown.stdout)
        assert at_head and at_head.group(1) == badge.group(1), (at_head, badge.group(1))

    def test_the_live_collect_count_is_still_readable(self) -> None:
        import re
        import sys

        out = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--collect-only", "-p", "no:cacheprovider"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        ).stdout
        assert re.search(r"(\d+) tests collected", out), out[-300:]
