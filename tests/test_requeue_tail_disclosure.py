"""The abandoned hours behind the requeue tail, which every surface counted and none read.

``find_requeues`` caps its output at ``REPEAT_REPORT_LIMIT`` workloads and adds one
INFO line for the rest. That line read the tail list -- ``hidden = findings[limit:]``
-- for ``len()`` and for nothing else, so it published how MANY workloads the cap had
dropped and withheld the quantity the rule *sorts* on. The rule's own docstring calls
that quantity the number that makes the case: "a requeued allocation really ran, and
its hours appear in no other total the tool prints."

The pair below is the proof. Five workloads qualify, four are printed, one is hidden,
and the two histories are identical in every dimension any surface showed -- the same
names, partitions, run counts, requeue counts, dominant state, ordering, severities
and titles -- differing only in what the hidden workload's abandoned attempts burned:
``00:03:00`` against ``1-00:00:00``. Before the fix ``--plain --patterns``, the
dashboard's patterns panel and ``--patterns --json`` all came out byte for byte the
same for both.

The sibling in the same module is what shows the disclosure was both possible and
wanted: ``find_repeat_failures`` totals *its* hidden rows -- "Together they account
for %d more failed runs" -- and has done since it was capped.

The controls hold the premise rather than the remedy: the pair agrees on everything
that was already on screen, a history under the cap still says nothing at all, each
printed workload still names its own abandoned time, and a tail whose attempts
recorded no elapsed still stays silent about time.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from slurmpast import cli, patterns, tui
from slurmpast.index import History
from slurmpast.model import INFO, Finding, Job
from slurmpast.patterns import REPEAT_REPORT_LIMIT, find_requeues
from slurmpast.report import Style, render_patterns

#: Names that do not fold into one another, so five workloads stay five workloads.
#: `group_key` keys on `normalize_name`, which collapses digit runs -- `shown0` and
#: `shown1` are one workload called `shown#`, which is how a first draft of this
#: fixture reported two findings where it meant five.
_SHOWN_NAMES = ("alpha", "bravo", "charlie", "delta")
_TAIL_NAME = "echo"

#: Runs per workload, and how many of them Slurm requeued. 3 of 10 clears both
#: floors: REQUEUE_MIN is 3 and REQUEUE_FRACTION is 0.10.
_RUNS = 10
_REQUEUED = 3

#: What each abandoned attempt of a *printed* workload ran. 100 hours apiece, so
#: those four sort above the tail whichever variant the tail is built with -- the
#: hidden workload has to stay hidden for the pair to be comparable at all.
_SHOWN_ATTEMPT_SECONDS = 360000.0

#: The one dimension the pair differs in: 3 x 60s = 00:03:00 against 3 x 8h =
#: 1-00:00:00 of abandoned time behind the workload the cap hides.
_CHEAP_ATTEMPT_SECONDS = 60.0
_COSTLY_ATTEMPT_SECONDS = 28800.0

#: The sentence the fix puts on all three surfaces, for the costly history.
EXPECTED = "The abandoned attempts ran 1-00:00:00 between them."

#: What the line said before, and still says after it. The instruction is not the
#: fix and must survive it.
INSTRUCTION = "Shown in full with a narrower --since window."


def _attempt(job_id: str, name: str, elapsed: float) -> Job:
    """One abandoned incarnation: it ran, it ended, Slurm requeued the id.

    ``end`` matters. ``find_requeues`` counts only attempts that closed, because
    Elapsed on an open record is measured to *now*.
    """
    return Job(
        job_id=job_id,
        name=name,
        user="alice",
        partition="amd",
        state="NODE_FAIL",
        submit="2026-08-17T10:08:59",
        start="2026-08-17T10:20:46",
        end="2026-08-17T10:48:35",
        elapsed=elapsed,
        alloc_cpus=8,
    )


def _run(index: int, name: str, attempt_seconds: float | None) -> Job:
    """The surviving incarnation, with its abandoned attempt attached or not."""
    job_id = str(5400000 + index)
    stamp = "2026-08-%02dT11:00:00" % (1 + index % 28)
    earlier: tuple[Job, ...] = ()
    if attempt_seconds is not None:
        earlier = (_attempt(job_id, name, attempt_seconds),)
    return Job(
        job_id=job_id,
        name=name,
        user="alice",
        partition="amd",
        state="COMPLETED",
        submit="2026-08-17T10:48:35",
        start=stamp,
        end=stamp,
        elapsed=563.0,
        alloc_cpus=8,
        earlier=earlier,
    )


def _workload(name: str, base: int, attempt_seconds: float) -> list[Job]:
    return [
        _run(base + index, name, attempt_seconds if index < _REQUEUED else None)
        for index in range(_RUNS)
    ]


def _history(tail_attempt_seconds: float, shown: int = len(_SHOWN_NAMES)) -> History:
    """Four printed workloads plus one the cap hides, or fewer to stay under it."""
    jobs: list[Job] = []
    for position, name in enumerate(_SHOWN_NAMES[:shown]):
        jobs += _workload(name, position * 1000, _SHOWN_ATTEMPT_SECONDS)
    jobs += _workload(_TAIL_NAME, 9000, tail_attempt_seconds)
    return History(jobs, window="now-30days")


CHEAP_TAIL: History = _history(_CHEAP_ATTEMPT_SECONDS)
COSTLY_TAIL: History = _history(_COSTLY_ATTEMPT_SECONDS)


def _squash(text: str) -> str:
    """One line of single-spaced words.

    Both front ends wrap the evidence to the terminal, so an assertion that reads
    the sentence back has to be indifferent to where the wrap fell -- otherwise it
    passes at 120 columns and fails at 60 for a reason that is not the defect.
    """
    return " ".join(text.split())


def _tail(history: History) -> Finding:
    """The one INFO finding the cap adds, whichever surface will draw it."""
    tails = [f for f in history.patterns if f.code == "requeue-repeat-more"]
    assert len(tails) == 1, [f.code for f in history.patterns]
    return tails[0]


def _shown(history: History) -> list[Finding]:
    return [f for f in history.patterns if f.code == "requeue-repeat"]


def _plain(history: History) -> str:
    return _squash(render_patterns(history, style=Style(enabled=False)))


async def _dashboard(history: History) -> str:
    """The patterns panel as the compositor draws it.

    Read off the screen rather than out of the widget: `PatternsScreen` keeps no
    `Text` of its own, and the attribute a `Static` holds its content in exists in
    textual 0.89 and not in 8.x -- which `test_readability` pins as a rule, and is
    why `test_tui` reads this panel the same way. Tall enough that the INFO line --
    sorted last, being the least severe -- is on screen rather than below the
    scroll.
    """
    app = tui.SlurmpastApp(lambda: list(history.jobs), window="now-30days", no_logs=True)
    async with app.run_test(size=(120, 80)) as pilot:
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        screen: Any = app.screen
        return _squash(
            " ".join(
                "".join(segment.text for segment in strip)
                for strip in screen._compositor.render_strips()
            )
        )


def _patterns_json(
    history: History, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> list[dict[str, Any]]:
    """The `--patterns --json` findings array, off the real CLI path.

    Through `--demo`, the one route that needs no scheduler, with the synthetic
    history swapped for the one under test.
    """
    monkeypatch.setattr("slurmpast.demo.history", lambda: list(history.jobs))
    assert cli.main(["--demo", "--patterns", "--json", "--no-color"]) == 0
    findings: list[dict[str, Any]] = json.loads(capsys.readouterr().out)["findings"]
    return findings


class TestThePairIsTheProof:
    """Controls. Each passes with the fix in or out: they pin the premise, and none
    of them reads the figure the fix added."""

    def test_five_workloads_qualify_and_four_are_printed(self) -> None:
        for history in (CHEAP_TAIL, COSTLY_TAIL):
            assert len(_shown(history)) == REPEAT_REPORT_LIMIT == 4
            assert len(find_requeues(list(history.jobs))) == 5

    def test_the_pair_agrees_on_everything_the_surfaces_showed(self) -> None:
        cheap, costly = _shown(CHEAP_TAIL), _shown(COSTLY_TAIL)
        assert [f.evidence for f in cheap] == [f.evidence for f in costly]
        assert [f.action for f in cheap] == [f.action for f in costly]
        assert [f.severity for f in cheap] == [f.severity for f in costly]
        assert _tail(CHEAP_TAIL).title == _tail(COSTLY_TAIL).title
        assert _tail(CHEAP_TAIL).severity == _tail(COSTLY_TAIL).severity == INFO

    def test_the_tail_title_still_counts_workloads_and_agrees(self) -> None:
        """The half of the line that was already right, and its plural."""
        assert _tail(COSTLY_TAIL).title == "1 further workload is requeued as often"
        assert _tail(CHEAP_TAIL).title == _tail(COSTLY_TAIL).title

    def test_each_printed_workload_still_names_its_own_abandoned_time(self) -> None:
        """Pre-existing behaviour, and the wording the tail now borrows."""
        for finding in _shown(COSTLY_TAIL):
            assert "The abandoned attempts ran 12-12:00:00 between them." in finding.evidence

    def test_the_tail_still_carries_no_action(self) -> None:
        """`report.render_patterns` guards on this: an empty action must stay empty
        or the plain view draws an arrow pointing at nothing."""
        assert _tail(CHEAP_TAIL).action == ""
        assert _tail(COSTLY_TAIL).action == ""

    def test_the_tail_still_says_how_to_see_the_rest(self) -> None:
        assert INSTRUCTION in _tail(CHEAP_TAIL).evidence
        assert INSTRUCTION in _tail(COSTLY_TAIL).evidence

    def test_a_history_under_the_cap_has_no_tail_line_at_all(self) -> None:
        """Separate input from every finding test above: four qualifying workloads,
        so the cap is not reached and the INFO line does not exist to carry
        anything."""
        under = _history(_COSTLY_ATTEMPT_SECONDS, shown=3)
        codes = [f.code for f in under.patterns]
        assert codes.count("requeue-repeat") == 4
        assert "requeue-repeat-more" not in codes


class TestThePlainReportNamesTheHours:
    def test_the_sentence_is_on_the_tail_line(self) -> None:
        assert EXPECTED in _plain(COSTLY_TAIL)

    def test_the_two_histories_no_longer_render_the_same(self) -> None:
        assert _plain(CHEAP_TAIL) != _plain(COSTLY_TAIL)

    def test_the_cheap_tail_reports_its_own_smaller_figure(self) -> None:
        """Not merely "a sentence appeared": the figure is the tail's own total."""
        assert "The abandoned attempts ran 00:03:00 between them." in _plain(CHEAP_TAIL)

    def test_the_figure_is_the_hidden_total_not_the_printed_one(self) -> None:
        """3 x 8h = 1-00:00:00 for the one workload hidden, against 12-12:00:00 for
        each of the four printed ones. Summing the wrong slice reads as the latter."""
        tail = _tail(COSTLY_TAIL).evidence
        assert "1-00:00:00" in tail
        assert "12-12:00:00" not in tail

    def test_the_figure_comes_before_the_instruction(self) -> None:
        """The shape `find_repeat_failures` already uses for its own tail: what was
        measured, then what to type."""
        evidence = _tail(COSTLY_TAIL).evidence
        assert evidence.index(EXPECTED) < evidence.index(INSTRUCTION)


class TestTheDashboardNamesTheSameHours:
    @pytest.mark.asyncio
    async def test_the_patterns_panel_carries_the_sentence(self) -> None:
        assert EXPECTED in await _dashboard(COSTLY_TAIL)

    @pytest.mark.asyncio
    async def test_the_two_histories_no_longer_draw_the_same_panel(self) -> None:
        assert await _dashboard(CHEAP_TAIL) != await _dashboard(COSTLY_TAIL)


class TestTheJsonPayloadCarriesTheFigure:
    def test_the_tail_finding_carries_the_sentence(
        self, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        findings = _patterns_json(COSTLY_TAIL, monkeypatch, capsys)
        tails = [f for f in findings if f["code"] == "requeue-repeat-more"]
        assert len(tails) == 1
        assert EXPECTED in tails[0]["evidence"]

    def test_the_two_payloads_no_longer_serialise_the_same(
        self, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        cheap = _patterns_json(CHEAP_TAIL, monkeypatch, capsys)
        costly = _patterns_json(COSTLY_TAIL, monkeypatch, capsys)
        assert json.dumps(cheap) != json.dumps(costly)

    def test_the_printed_findings_are_untouched(
        self, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        """Control on the payload: only the INFO line moved, and the four
        `requeue-repeat` objects still agree across the pair."""
        cheap = _patterns_json(CHEAP_TAIL, monkeypatch, capsys)
        costly = _patterns_json(COSTLY_TAIL, monkeypatch, capsys)
        keep = [f for f in cheap if f["code"] == "requeue-repeat"]
        assert keep == [f for f in costly if f["code"] == "requeue-repeat"]
        assert len(keep) == 4


class TestOneSpellingForAllThreeSurfaces:
    """`render.py` exists so the two front ends cannot word a shared fact
    differently. This sentence cannot live there -- `render` imports `rich` and the
    analysis modules may not -- so it lives once in `patterns`, and these pin that
    the three surfaces really do read that one spelling."""

    @pytest.mark.asyncio
    async def test_the_surfaces_print_the_same_string(
        self, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        findings = _patterns_json(COSTLY_TAIL, monkeypatch, capsys)
        (tail,) = [f for f in findings if f["code"] == "requeue-repeat-more"]
        assert EXPECTED in tail["evidence"]
        assert EXPECTED in _plain(COSTLY_TAIL)
        assert EXPECTED in await _dashboard(COSTLY_TAIL)

    def test_the_tail_and_the_rows_use_one_helper(self) -> None:
        """The tail borrows the wording the printed rows already own, so the two
        cannot drift into two nouns for one measurement."""
        note = patterns._abandoned_time_note(3 * _COSTLY_ATTEMPT_SECONDS)
        assert note == EXPECTED
        assert note in _tail(COSTLY_TAIL).evidence
        row_note = patterns._abandoned_time_note(3 * _SHOWN_ATTEMPT_SECONDS)
        assert row_note in _shown(COSTLY_TAIL)[0].evidence


class TestItSaysNothingWhereThereIsNoTimeToReport:
    """The gate, and a control: silence is what every surface did before the fix,
    so these pass either way. An earlier attempt can close carrying no Elapsed at
    all, and "ran 00:00:00" reads as a measurement where there is none."""

    def test_a_zero_length_tail_reports_only_the_instruction(self) -> None:
        history = _history(0.0)
        assert _tail(history).evidence == INSTRUCTION

    def test_the_helper_is_empty_on_nothing_burned(self) -> None:
        assert patterns._abandoned_time_note(0.0) == ""
        assert patterns._abandoned_time_note(None) == ""

    def test_the_plain_view_draws_no_time_clause_there(self) -> None:
        assert "The abandoned attempts ran" not in _plain(_history(0.0)).split("[INFO]")[1]
