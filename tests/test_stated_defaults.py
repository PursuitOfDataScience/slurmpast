"""A default written into help text must be the default the parser uses.

Three options here spell their default out in prose — `(default: now-7days)`,
`(default: hang)`, `(default: cost)` — rather than interpolating `%(default)s`.
Hardcoding is not wrong: `--since`'s gloss ("'-7days' is accepted and rewritten
for you") reads better beside a literal than an interpolation. But it is a copy,
and a copy drifts silently — change the keyword and the sentence beside it still
names the old value.

**Ported from nodetop, which has the same check, because its docstring turned
out to be wrong about this package.** It says: "A sibling package sidesteps this
by interpolating everywhere, and two others state only prose defaults, so this
is the one package where the check has anything to bite on." Measured: rapidu
does interpolate, all seven of its stated defaults (`--depth`, `--top`,
`--max-dirs-per-sec`, `--settle-window`, `--quota-timeout`,
`--max-snapshot-age`, `--color`) — so that half is right. But slurmpast states
**three comparable values**, not only prose, so the check bites here too. That
sentence is corrected in nodetop as part of this round.

Verified at the time of writing: all three agree. `--user` states `(default:
you)` for a `None` that means "resolve at run time", which is honest and cannot
be compared mechanically, so it is skipped by name.
"""

from __future__ import annotations

import argparse
import re

import pytest

from slurmpast.cli import build_parser

#: `(default: X)` anywhere in a help string. Bounded so a long sentence
#: containing the word cannot be mistaken for a value.
_STATED = re.compile(r"\(\s*default[:\s]+([^)]{1,24})\)", re.I)

#: Stated defaults that are a DESCRIPTION rather than a value. Listed rather
#: than pattern-matched, so adding one is a deliberate act.
_PROSE = frozenset({"you", "yours", "none", "all of yours", "the current directory"})


def _stated_value(text: str) -> str | None:
    """The default this help string claims, or None for prose or nothing."""
    found = _STATED.search(text)
    if not found:
        return None
    stated = found.group(1).strip().strip("`'\"")
    # A glossed value: the value, then a semicolon and an explanation.
    stated = stated.split(";")[0].strip()
    return None if stated.lower() in _PROSE else stated


def _options() -> list[tuple[str, argparse.Action, str]]:
    """Every option whose help text states a comparable default value."""
    out: list[tuple[str, argparse.Action, str]] = []
    for action in build_parser()._actions:
        if not action.option_strings or not action.help:
            continue
        if "%(default)" in action.help:
            continue  # interpolated: cannot drift
        stated = _stated_value(action.help)
        if stated is not None:
            out.append(("/".join(action.option_strings), action, stated))
    return out


def test_there_are_stated_defaults_to_check():
    """Guards against the scan going quiet and every assertion below passing.

    If this package moves to `%(default)s` throughout, this fails and says to
    delete the file rather than leaving a test that checks nothing.
    """
    found = _options()
    assert len(found) >= 3, (
        f"only {len(found)} hardcoded default(s) found; either they were "
        f"converted to %(default)s -- in which case this file has no job left -- "
        f"or the help wording changed shape and the scan no longer sees them"
    )


@pytest.mark.parametrize("case", _options(), ids=lambda c: c[0].split("/")[-1])
def test_the_stated_default_is_the_real_one(case):
    label, action, stated = case
    actual = action.default
    assert str(actual) == stated, (
        f"`slurmpast {label}` help says the default is {stated!r}, but the parser "
        f"uses {actual!r}. One of the two moved; the help text is the copy."
    )


class TestTheComparisonItself:
    """Controls -- a check that passes because it compares nothing is worse than
    none. Each holds whatever the parser's real defaults are, so they survive any
    neuter of a default or of a help string."""

    def test_a_disagreement_would_be_caught(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--wrong", default="now-1days", help="when (default: now-7days)")
        action = next(a for a in parser._actions if a.dest == "wrong")
        stated = _stated_value(action.help or "")
        assert stated == "now-7days" and str(action.default) != stated

    def test_prose_is_skipped_rather_than_failed(self):
        assert _stated_value("user to query (default: you)") is None

    def test_a_glossed_value_is_still_compared(self):
        assert _stated_value("start of the window (default: now-7days; rewritten)") == "now-7days"

    def test_help_without_a_default_is_ignored(self):
        assert _stated_value("only jobs that failed") is None

    def test_an_interpolated_default_is_left_to_argparse(self):
        """rapidu's approach, which cannot drift and so is excluded by `_options`."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--n", default=10, help="how many (default: %(default)s)")
        action = next(a for a in parser._actions if a.dest == "n")
        assert "%(default)" in (action.help or "")
