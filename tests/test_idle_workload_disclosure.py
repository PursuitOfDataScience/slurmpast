"""The GPU-hours behind FLAGGED, which every surface computed and none read.

``GroupStats.wasted_gpu_hours`` -- the GPU-hours held by the runs the overview
counts under FLAGGED -- has been summed on every ``build_groups`` walk since the
first commit and was read by nothing: not the table, not ``--overview --json``,
not ``GroupStats.cost``, which is what the list is ranked by. FLAGGED is a run
*count*, so it cannot carry the difference either.

The two histories below are the proof. They are built to be identical in every
dimension the surfaces did show -- 20 runs, 16 completed, 4 flagged, 290
GPU-hours, 2,320 CPU-hours, the same partition, the same label, the same last
run, the same severity, the same rank -- and to differ only in the one they did
not: 2 idle GPU-hours against 90. Before the fix the plain overview and the
per-workload JSON object came out byte for byte the same for both.

The controls here are the halves of that proof that must stay true: the table
row is still identical (the fix does not touch a column), and a history whose
waste is immaterial still says nothing.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from slurmpast import cli, render, tui
from slurmpast.index import GroupStats, History
from slurmpast.model import Job
from slurmpast.report import Style, render_overview

# Elapsed values chosen so every hour figure is exact in binary -- 64800/3600 is
# 18.0, 45000/3600 is 12.5, 81000/3600 is 22.5 -- because the claim under test is
# byte-identical output, and a float wobble in the totals would prove it for the
# wrong reason.
_COMPLETED_RUNS = 16
_FLAGGED_RUNS = 4


def _job(index: int, state: str, elapsed: int, name: str = "train") -> Job:
    """One GPU run: eight cores, one card, closed, with a real elapsed time."""
    stamp = "2026-08-%02dT00:00:00" % (1 + index % 28)
    return Job(
        job_id=str(1000 + index),
        name="%s-%d" % (name, index),
        user="alice",
        partition="gpu",
        state=state,
        elapsed=float(elapsed),
        start=stamp,
        end=stamp,
        alloc_tres="cpu=8,mem=64G,node=1,gres/gpu=1",
        alloc_cpus=8,
    )


def _workload(completed_elapsed: int, flagged_elapsed: int, name: str = "train") -> list[Job]:
    jobs = [_job(index, "COMPLETED", completed_elapsed, name) for index in range(_COMPLETED_RUNS)]
    jobs += [
        _job(_COMPLETED_RUNS + index, "FAILED", flagged_elapsed, name)
        for index in range(_FLAGGED_RUNS)
    ]
    return jobs


#: Four flagged runs that died in half an hour each: 2 of 290 GPU-hours idle.
CHEAP_FAILURES: list[Job] = _workload(64800, 1800)

#: Four flagged runs that each held a card for 22.5 hours: 90 of 290 idle.
COSTLY_FAILURES: list[Job] = _workload(45000, 81000)

#: The sentence the fix puts on both surfaces, for the costly history.
EXPECTED = "flagged runs held the most GPU-hours in train-#: 90 of its 290"


def _history(jobs: list[Job]) -> History:
    return History(jobs, window="now-30days")


def _group(jobs: list[Job]) -> GroupStats:
    groups = _history(jobs).groups
    assert len(groups) == 1, [g.name for g in groups]
    return groups[0]


def _plain(jobs: list[Job]) -> str:
    return render_overview(_history(jobs), style=Style(enabled=False))


def _squash(text: str) -> str:
    """One line of single-spaced words.

    The sentence is wrapped to the terminal on both surfaces, so an assertion
    that reads it back has to be indifferent to where the wrap fell -- otherwise
    it passes at 100 columns and fails at 60 for a reason that is not the defect.
    """
    return " ".join(text.split())


def _table_row(text: str) -> str:
    """The overview's one data row, with everything below the table discarded."""
    below_rule = text.split("\n  --", 1)[1]
    return below_rule.splitlines()[1]


def _summary_sentence(text: str) -> str:
    """The clause under test, cut out of whichever surface drew it."""
    squashed = _squash(text)
    start = squashed.index("flagged runs held")
    return squashed[start : squashed.index(" 290", start) + len(" 290")]


def _make_app(jobs: list[Job]) -> tui.SlurmpastApp:
    return tui.SlurmpastApp(lambda: list(jobs), window="now-30days", no_logs=True)


async def _dashboard_summary(jobs: list[Job]) -> str:
    app = _make_app(jobs)
    async with app.run_test() as pilot:
        await pilot.pause()
        # `summary_text` is retained on the screen deliberately -- `tui` says why:
        # reading the sentence back off the `Static` means depending on widget
        # internals that moved between textual 0.89 and 8.x. Typed loosely because
        # `App.screen` is a `Screen[object]` as far as mypy is concerned.
        screen: Any = app.screen
        return str(screen.summary_text.plain)


def _overview_json(jobs: list[Job], monkeypatch: pytest.MonkeyPatch, capsys: Any) -> Any:
    """The `--overview --json` workloads payload, off the real CLI path.

    Through `--demo`, which is the one route that needs no scheduler, with the
    synthetic history swapped for the pair under test.
    """
    monkeypatch.setattr("slurmpast.demo.history", lambda: list(jobs))
    assert cli.main(["--demo", "--overview", "--json", "--no-color"]) in (0, 1)
    return json.loads(capsys.readouterr().out)["workloads"]


class TestThePairIsTheProof:
    """Controls. Every one of these passes with the fix in or out -- they pin the
    premise, not the remedy, and none of them reads anything the fix added."""

    def test_the_two_histories_agree_on_everything_the_surfaces_showed(self) -> None:
        cheap, costly = _group(CHEAP_FAILURES), _group(COSTLY_FAILURES)
        shown = [
            ("label", lambda g: g.label),
            ("partition", lambda g: g.partition),
            ("runs", lambda g: g.total),
            ("completed", lambda g: g.completed),
            ("failed", lambda g: g.failed),
            ("problems", lambda g: g.problems),
            ("noop", lambda g: g.noop),
            ("cancelled", lambda g: g.cancelled),
            ("gpu_hours", lambda g: g.gpu_hours),
            ("core_hours", lambda g: g.core_hours),
            ("severity", lambda g: g.severity),
            ("cost", lambda g: g.cost),
            ("last_seen", lambda g: g.last_seen),
        ]
        for field, read in shown:
            assert read(cheap) == read(costly), field

    def test_they_differ_in_exactly_one_measured_figure(self) -> None:
        assert _group(CHEAP_FAILURES).wasted_gpu_hours == 2.0
        assert _group(COSTLY_FAILURES).wasted_gpu_hours == 90.0

    def test_the_table_row_is_identical_for_both(self) -> None:
        """The half of the old defect that is correct and stays: no column moved,
        so the row a reader scans cannot tell 2 idle hours from 90."""
        assert _table_row(_plain(CHEAP_FAILURES)) == _table_row(_plain(COSTLY_FAILURES))

    def test_the_hours_cell_is_identical_for_both(self) -> None:
        assert render.hours_pair_text(_group(CHEAP_FAILURES)) == render.hours_pair_text(
            _group(COSTLY_FAILURES)
        )

    def test_the_flagged_cell_is_identical_for_both(self) -> None:
        assert _group(CHEAP_FAILURES).problems == _group(COSTLY_FAILURES).problems == 4

    def test_the_ranking_cannot_separate_them_either(self) -> None:
        assert _group(CHEAP_FAILURES).cost == _group(COSTLY_FAILURES).cost


class TestThePlainReportNamesTheWorkload:
    def test_the_sentence_is_under_the_table(self) -> None:
        assert EXPECTED in _squash(_plain(COSTLY_FAILURES))

    def test_it_carries_both_numbers_not_just_the_waste(self) -> None:
        """The slurmwatch lesson: 90 is a different instruction at 90-of-290 than
        at 90-of-9000, and the numerator alone hides which one it is."""
        sentence = _summary_sentence(_plain(COSTLY_FAILURES))
        assert "90 of its 290" in sentence

    def test_it_sits_below_the_table_not_in_the_capped_summary(self) -> None:
        """`test_the_summary_is_brief` caps everything above the table at four
        lines on purpose, so this must not land there."""
        head = _plain(COSTLY_FAILURES).split("#    JOB NAME")[0]
        assert "flagged runs held" not in head


class TestTheDashboardNamesTheSameWorkload:
    @pytest.mark.asyncio
    async def test_the_summary_line_carries_the_sentence(self) -> None:
        assert EXPECTED in _squash(await _dashboard_summary(COSTLY_FAILURES))


class TestOneSentenceForBothSurfaces:
    """`render.py` exists so the two front ends cannot word this differently."""

    @pytest.mark.asyncio
    async def test_the_two_surfaces_print_the_same_string(self) -> None:
        plain = _summary_sentence(_plain(COSTLY_FAILURES))
        dashboard = _summary_sentence(await _dashboard_summary(COSTLY_FAILURES))
        assert plain == dashboard

    def test_both_take_it_from_render(self) -> None:
        group = _group(COSTLY_FAILURES)
        note = render.idle_workload_note(group.label, group.wasted_gpu_hours, group.gpu_hours)
        assert note == EXPECTED
        assert note == _summary_sentence(_plain(COSTLY_FAILURES))


class TestItStaysQuietWhenThereIsNothingToAct:
    """The restraint `IDLE_SHARE_WORTH_NAMING` is written down for. Controls:
    silence is what both surfaces did before the fix, so these pass either way."""

    def test_the_plain_report_says_nothing_about_two_of_290(self) -> None:
        assert "flagged runs held" not in _plain(CHEAP_FAILURES)

    @pytest.mark.asyncio
    async def test_the_dashboard_says_nothing_either(self) -> None:
        assert "flagged runs held" not in await _dashboard_summary(CHEAP_FAILURES)

    def test_a_cpu_only_history_is_silent_by_construction(self) -> None:
        cpu_only = [
            Job(
                job_id=str(2000 + index),
                name="fit-%d" % index,
                user="alice",
                partition="amd",
                state="FAILED",
                elapsed=360000.0,
                start="2026-08-%02dT00:00:00" % (1 + index),
                end="2026-08-%02dT00:00:00" % (1 + index),
                alloc_tres="cpu=32,mem=64G,node=1",
                alloc_cpus=32,
            )
            for index in range(6)
        ]
        assert "flagged runs held" not in _plain(cpu_only)


class TestTheWorstIsPickedByHoursNotByShare:
    """ "the most" has to be true. Ranking on the share instead names a two-hour
    workload that wasted one of them over a 290-hour one that wasted 90."""

    def test_a_big_share_of_almost_nothing_does_not_win(self) -> None:
        # One run, 2 GPU-hours, all of it flagged: a 100% share, 2 hours.
        sliver = [_job(90, "FAILED", 7200, "probe")]
        history = History(COSTLY_FAILURES + sliver, window="now-30days")
        worst = history.idle_workload
        assert worst is not None
        assert worst[0].label == "train-#"
        assert worst[1] == 90.0

    def test_the_sliver_alone_is_named_because_nothing_outweighs_it(self) -> None:
        """Not a contradiction with the test above: picking by the absolute figure
        decides WHICH workload gets judged, not whether a small one may ever be
        named. Alone in the window the sliver is the most, and 2 of 2 GPU-hours
        clears the share arm of the gate."""
        worst = History([_job(90, "FAILED", 7200, "probe")]).idle_workload
        assert worst is not None
        assert worst[1] == 2.0
        assert "probe" in worst[0].label


class TestTheJsonPayloadCarriesTheFigure:
    def test_wasted_gpu_hours_is_emitted(
        self, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        (workload,) = _overview_json(COSTLY_FAILURES, monkeypatch, capsys)
        assert workload["wasted_gpu_hours"] == 90.0

    def test_the_two_histories_no_longer_serialise_the_same(
        self, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        cheap = _overview_json(CHEAP_FAILURES, monkeypatch, capsys)
        costly = _overview_json(COSTLY_FAILURES, monkeypatch, capsys)
        assert json.dumps(cheap) != json.dumps(costly)

    def test_the_rest_of_the_breakdown_is_untouched(
        self, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        """Control: the keys that were already emitted still are, with the same
        values, and they still agree across the pair."""
        (cheap,) = _overview_json(CHEAP_FAILURES, monkeypatch, capsys)
        (costly,) = _overview_json(COSTLY_FAILURES, monkeypatch, capsys)
        for key in ("runs", "completed", "problems", "failed", "noop", "gpu_hours", "core_hours"):
            assert cheap[key] == costly[key], key
        assert cheap["runs"] == 20
        assert cheap["problems"] == 4
        assert cheap["gpu_hours"] == 290.0
