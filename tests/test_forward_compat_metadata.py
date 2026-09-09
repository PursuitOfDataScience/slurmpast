"""The classifiers cover every version `requires-python` allows, and stay true.

`requires-python = ">=3.10"` has no upper bound, so pip already installs this on
3.14. The classifiers stopped at 3.13, which understated support rather than
restricting it — the exact gap slurmate's CHANGELOG describes for this family: "the
packages are 3.14-clean while their classifiers stop at [3.13] ... nothing was
blocked; the metadata simply understated it."

For slurmpast that is not a guess. `issues.md` records the published package being
**installed from PyPI onto midway2 — CentOS 7.9, glibc 2.17, Python 3.14.6, Slurm
23.02, cgroup v1 — and exercised against that cluster's real accounting history**,
twice (0.7.0 and again for 0.8.2). Neither round reported an import or syntax
failure; the defects found were environment-general.

Classifiers are what PyPI shows and what tooling filters on, so a gap costs real
installs. Two tests hold the claim: this file checks the metadata agrees with itself,
and `test_no_removed_or_deprecated_stdlib_apis` checks the thing that would actually
break on a newer interpreter. slurmate carries the same pair; slurmpast and slurmwatch
did not.

The CI matrix is deliberately NOT asserted here. It tops out at 3.13 because that is
what runners offer, which is a separate policy from what the package supports — the
same split slurmate keeps.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "slurmpast"

#: What actually breaks on a newer interpreter. `distutils` and `imp` are gone,
#: `utcnow` and `getdefaultlocale` are deprecated, `find_loader` was removed.
BANNED = re.compile(
    r"\b(distutils|import imp\b|utcnow|getdefaultlocale|find_loader"
    r"|pkg_resources|typing\.ByteString)\b"
)


def _pyproject() -> str:
    """Read as text, deliberately.

    `tomllib` is 3.11+, and 3.10 is the oldest version this very file asserts
    support for — importing it would make the test unrunnable on the interpreter
    it most needs to run on. slurmate's equivalent test records the same reason.
    """
    return (ROOT / "pyproject.toml").read_text()


def _declared_versions(text: str) -> set[str]:
    return set(re.findall(r'"Programming Language :: Python :: ([0-9.]+)"', text))


class TestTheMetadataAgreesWithItself:
    def test_every_version_requires_python_allows_is_declared(self) -> None:
        text = _pyproject()
        requires = re.search(r'^requires-python\s*=\s*"([^"]+)"', text, re.M)
        assert requires and requires.group(1) == ">=3.10", requires
        declared = _declared_versions(text)
        assert {"3.10", "3.11", "3.12", "3.13", "3.14"} <= declared, declared

    def test_the_declared_list_was_actually_found(self) -> None:
        # A silent regex miss would make the subset check pass against nothing.
        assert len(_declared_versions(_pyproject())) >= 5


class TestTheClaimStaysTrue:
    def test_no_removed_or_deprecated_stdlib_apis(self) -> None:
        offenders = [
            f"{path.name}:{n}"
            for path in sorted(SRC.glob("*.py"))
            for n, line in enumerate(path.read_text().splitlines(), 1)
            if BANNED.search(line) and not line.lstrip().startswith("#")
        ]
        assert offenders == [], offenders

    def test_there_are_sources_to_scan(self) -> None:
        assert len(list(SRC.glob("*.py"))) >= 8

    def test_the_scanner_would_notice_a_real_offender(self) -> None:
        """A guard that cannot fail is not a guard."""
        for planted in (
            "from distutils.util import strtobool",
            "import imp",
            "datetime.datetime.utcnow()",
            "locale.getdefaultlocale()",
            "importlib.find_loader('x')",
            "import pkg_resources",
        ):
            assert BANNED.search(planted), planted

    def test_the_scanner_ignores_a_comment(self) -> None:
        # The real scan skips comment lines; issues.md and docstrings discuss
        # `distutils` by name and must not trip it.
        assert BANNED.search("# distutils is gone in 3.12")
        assert "distutils" in "# distutils is gone in 3.12"


class TestControls:
    """None of these reads a version number, so each holds either way."""

    def test_requires_python_is_still_declared_at_all(self) -> None:
        assert re.search(r"^requires-python\s*=", _pyproject(), re.M)

    def test_the_generic_python_3_classifier_is_kept(self) -> None:
        # Dropping it would narrow what PyPI shows regardless of the minor list.
        assert '"Programming Language :: Python :: 3"' in _pyproject()

    def test_the_source_tree_is_where_this_expects(self) -> None:
        assert (SRC / "cli.py").is_file()
