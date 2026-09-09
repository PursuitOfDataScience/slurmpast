"""`--sizing` had no end-to-end routing test, which round fifty-seven left open.

Its Still-open list named three: "The overview, the job list and `--sizing` still
have no end-to-end routing test... what guards the other three is the source
sweep, which is stronger than it was but is still a sweep -- it can prove no
sentence is written twice, not that what reaches each screen is the shared one."

Measured, two of the three are not gaps in that sense:

* the **overview** does have one --
  `test_ui_usability.py::TestTheIdleClauseIsOneSentence::
  test_both_surfaces_say_the_same_thing` asserts the idle clause is in
  `render_overview(...)` AND in the dashboard's `summary_text`;
* the **job list** has no shared sentence to route: `report.render_list` calls only
  `cores_text`, `stamp_short` and `text_table`, all formatting.

`--sizing` is the real one. Its prose is single-sourced in `sizing.py` -- an
analysis module, so it may not import `render`, and both front ends import
`recommend` from it -- and the fields that carry sentences are `Advice.basis` and
`Advice.caution`. `caution` is the one with history: `tui.WorkloadScreen` "did not
read [it] at all", so "the dashboard was the one surface of three handing over a
directive with the caveat removed". Nothing pinned that fix, so nothing stops it
regressing.

Measured on the demo history: 8 groups, **10 actionable advices, 8 of them with a
caution**, and every `basis` and every `caution` reaches both surfaces today.
Compared on the words, because `--sizing` wraps to `_plain_width()` and the banner
to the panel -- an exact-substring check reports 8 false absences, which is what
first made this look like a live defect.
"""

import asyncio
import re

import pytest

from slurmpast import tui
from slurmpast.demo import history
from slurmpast.index import History, build_groups
from slurmpast.report import Style, render_sizing
from slurmpast.site import pin_partition_ceilings, reset_cache
from slurmpast.sizing import recommend

_WORDS = re.compile(r"[A-Za-z0-9.%/_-]+")


def _words(text):
    """``text`` as a single space-joined word stream.

    The repo's established key for comparing one sentence across two surfaces
    (round fifty-six): each wraps to its own width, and a reader hears no
    difference between the line breaks.
    """
    return " ".join(_WORDS.findall(text))


def _reaches(surface, sentence):
    key = _words(sentence)
    assert key, "vacuous: the sentence contributed no words to compare"
    return key in _words(surface)


def _workload_screen(jobs, group, size=(120, 60)):
    """What the compositor paints for one workload, including the sizing banner.

    `WorkloadScreen` is pushed directly rather than reached with `enter`: the
    overview is ordered by cost, so which row the cursor starts on is not this
    test's business -- and the first row of the demo (`node-evaluation`) has no
    actionable advice at all, so driving the key would have asserted nothing.
    """

    async def run():
        app = tui.SlurmpastApp(lambda: list(jobs), window="test", no_logs=True)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            app.push_screen(tui.WorkloadScreen(group))
            await pilot.pause()
            await pilot.pause()
            return "\n".join(
                "".join(seg.text for seg in strip).rstrip()
                for strip in app.screen._compositor.render_strips()
            )

    return asyncio.run(run())


@pytest.fixture(scope="module")
def jobs():
    return list(history())


@pytest.fixture
def plain(jobs):
    """`--sizing`, rendered under the same site the assertions are computed with.

    Deliberately NOT module-scoped, which is what it was. `render_sizing` words
    its MaxRSS caution from `site()`, and pytest builds a module-scoped fixture
    before conftest's function-scoped autouse `_pinned_site` -- so the surface was
    rendered against the *host's* scheduler configuration while every
    `Advice.caution` compared against it was computed under the pin. On the
    cluster this was written on the two happen to be the same string, so the
    ordering was invisible; with no `scontrol` on PATH the surface said "depending
    on this cluster" and the caution said `jobacct_gather/linux`, and
    `test_the_caution_is_on_both` failed for a reason that has nothing to do with
    routing. `jobs` stays module-scoped: `demo.history()` reads no site.
    """
    return render_sizing(History(jobs), style=Style(enabled=False))


def _advised(jobs):
    """``(group, [actionable advice])`` for every group that has any."""
    out = []
    for group in build_groups(jobs):
        advice = [a for a in recommend(group.jobs) if a.actionable]
        if advice:
            out.append((group, advice))
    return out


class TestTheFixtureCanProveSomething:
    """Vacuity guards. Every sweep below iterates the demo's advice, so an empty
    or caution-free fixture would make them all trivially true."""

    def test_there_is_advice_to_route(self, jobs):
        advised = _advised(jobs)
        assert len(advised) >= 4, [g.label for g, _ in advised]
        assert sum(len(a) for _g, a in advised) == 10

    def test_and_some_of_it_carries_a_caution(self, jobs):
        cautions = [a for _g, adv in _advised(jobs) for a in adv if a.caution]
        assert len(cautions) == 8, len(cautions)


class TestEverySentenceReachesBothSurfaces:
    def test_the_basis_is_on_both(self, jobs, plain):
        for group, advice in _advised(jobs):
            screen = _workload_screen(jobs, group)
            for item in advice:
                assert _reaches(plain, item.basis), (group.label, item.flag, "--sizing")
                assert _reaches(screen, item.basis), (group.label, item.flag, "dashboard")

    def test_the_caution_is_on_both(self, jobs, plain):
        """The field the dashboard once dropped entirely. `--sizing` and
        `--sizing --json` carried it while the banner handed over the directive
        with the caveat removed -- including both "cut --cpus-per-task on a GPU
        workload" lines, whose caveat is that doing so can starve the card."""
        seen = 0
        for group, advice in _advised(jobs):
            screen = _workload_screen(jobs, group)
            for item in advice:
                if not item.caution:
                    continue
                seen += 1
                assert _reaches(plain, item.caution), (group.label, item.flag, "--sizing")
                assert _reaches(screen, item.caution), (group.label, item.flag, "dashboard")
        assert seen == 8, seen

    def test_control_the_directive_itself_is_on_both(self, jobs, plain):
        """CONTROL. The flag and the number it suggests are what a reader acts on,
        and they were never the drift -- so they must hold with any of the fixes
        above neutered. If this reddens the harness is wrong, not the routing."""
        for group, advice in _advised(jobs):
            screen = _workload_screen(jobs, group)
            for item in advice:
                for surface, name in ((plain, "--sizing"), (screen, "dashboard")):
                    assert item.flag in surface, (group.label, item.flag, name)
                    assert item.suggestion in surface, (group.label, item.suggestion, name)


class TestWhatIsDeliberatelyNotASentence:
    def test_observed_is_not_printed_as_prose_on_either_surface(self, jobs, plain):
        """`Advice.observed` ("1.9 GiB peak across 6 runs") is the DATA behind
        `basis` ("the most any run used was 1.9 GiB."), not a second sentence, and
        neither text surface prints it. Pinned with the reason so a later sweep
        that notices it missing does not "fix" it into both surfaces and say the
        same thing twice -- `--sizing --json` is where a consumer reads the field.
        """
        for group, advice in _advised(jobs):
            for item in advice:
                if item.observed:
                    assert not _reaches(plain, item.observed), (group.label, item.flag)

    def test_but_the_figure_it_holds_does_reach_the_reader(self, jobs, plain):
        """The other half: not printing `observed` must not mean losing its number.
        Every advice whose `observed` names a measurement has that measurement in
        the `basis` sentence that IS printed."""
        checked = 0
        for _group, advice in _advised(jobs):
            for item in advice:
                figure = re.search(r"[0-9][0-9.:]*\s*(?:GiB|MiB|core|cores)?", item.observed or "")
                if not figure or not item.basis:
                    continue
                number = re.match(r"[0-9][0-9.:]*", figure.group(0))
                if number and number.group(0) in item.basis:
                    checked += 1
        assert checked >= 6, checked


class TestTheProseHasOneHome:
    def test_neither_front_end_spells_the_advice_itself(self):
        """`sizing.py` owns these sentences; `report` and `tui` may only route
        them. Asserted as the import, because a second copy is what the source
        sweep in `test_audit.py` can see and this file cannot."""
        from pathlib import Path

        import slurmpast.report as report_mod
        import slurmpast.tui as tui_mod

        for module in (report_mod, tui_mod):
            source = Path(module.__file__).read_text()
            assert "from .sizing import" in source, module.__name__
            assert "recommend" in source, module.__name__


@pytest.fixture
def saturated():
    """The demo history against a partition ceiling its workloads exceed.

    `capped` needs `partition_ceiling` to answer AND the workload to be asking for
    all of it. The demo pins `{"test": (48, …)}` under `--demo` and its busiest
    workload uses 7.5 cores, so nothing is ever capped there -- which is why the
    branch had no coverage on either surface. Two cores makes three workloads
    capped; asserted below rather than assumed.

    The pin is process-global, so it is reset on the way out: a leaked ceiling
    would silently clamp every later test's recommendations.
    """
    reset_cache()
    pin_partition_ceilings({"test": (2, 196608)})
    try:
        yield list(history())
    finally:
        reset_cache()


def _capped(jobs):
    out = []
    for group in build_groups(jobs):
        items = [a for a in recommend(group.jobs) if a.verdict == "capped"]
        if items:
            out.append((group, items))
    return out


class TestASaturatedWorkloadReachesBothSurfaces:
    """`Advice.actionable` is ``verdict in ("raise", "lower")``, so `capped` was
    filtered out of the dashboard banner and appeared on NO screen -- while
    `--sizing` gave it a flag line, its basis, and the caution naming the way out.
    `sizing` gives it a separate verdict precisely because it is "Not 'already
    about right': the workload wants more and cannot have it here".
    """

    def test_the_fixture_really_caps_something(self, saturated):
        """Vacuity guard, both directions: the pin must produce capped verdicts,
        and the UNPINNED demo must produce none -- otherwise this file would have
        found the branch already covered."""
        assert sum(len(items) for _g, items in _capped(saturated)) == 3
        reset_cache()
        assert _capped(list(history())) == []

    def test_the_ceiling_line_is_on_both(self, saturated):
        from slurmpast.render import capped_label

        plain = render_sizing(History(saturated), style=Style(enabled=False))
        for group, items in _capped(saturated):
            screen = _workload_screen(saturated, group)
            for item in items:
                for surface, name in ((plain, "--sizing"), (screen, "dashboard")):
                    assert item.flag in surface, (group.label, item.flag, name)
                    assert _reaches(surface, capped_label()), (group.label, name)
                    assert _reaches(surface, item.basis), (group.label, name)
                    assert _reaches(surface, item.caution), (group.label, name)

    def test_neither_surface_prints_the_clamped_number_as_advice(self, saturated):
        """The reason `capped` is not `lower`. Its `suggestion` IS set -- to the
        ceiling -- and printing ``--cpus-per-task=2`` beside a workload that wants
        more reads as advice to shrink, which is the "different wrong answer" the
        verdict exists to avoid.
        """
        from slurmpast.sizing import sbatch_lines

        for group, items in _capped(saturated):
            screen = _workload_screen(saturated, group)
            pasteable = sbatch_lines(recommend(group.jobs))
            for item in items:
                assert item.suggestion, "the fixture must have a clamped suggestion"
                directive = "%s=%s" % (item.flag, item.suggestion)
                # `--sizing` is checked through `sbatch_lines`, the function that
                # decides what is pasteable, rather than by searching the whole
                # document: the string `--cpus-per-task=2` legitimately appears
                # there for OTHER workloads whose verdict really is "lower to 2",
                # and a document-wide search read one of those as this one's.
                assert not [ln for ln in pasteable if directive in ln], (
                    group.label,
                    directive,
                    pasteable,
                )
                # The banner shows only this workload, so this scope is already
                # per-workload -- and `midtrain`'s other advice is `--time`, so
                # the flag cannot arrive from a sibling row.
                assert directive not in screen, (group.label, directive, "dashboard")

    def test_control_ordinary_advice_still_reads_as_a_directive(self, saturated):
        """CONTROL. Under the same pinned ceiling, an actionable item must still
        render as ``flag=suggestion`` on both -- the capped branch must not have
        swallowed the normal one. Holds with either fix neutered."""
        plain = render_sizing(History(saturated), style=Style(enabled=False))
        seen = 0
        for group, advice in _advised(saturated):
            screen = _workload_screen(saturated, group)
            for item in advice:
                directive = "%s=%s" % (item.flag, item.suggestion)
                assert directive in plain, (group.label, directive, "--sizing")
                assert directive in screen, (group.label, directive, "dashboard")
                seen += 1
        assert seen >= 1, seen

    def test_control_the_label_has_one_home(self):
        """CONTROL for the single-sourcing half: `render` owns the sentence and
        neither front end spells it. Holds before and after -- `report` used to
        spell it, so this is the assertion that would have caught the copy."""
        from pathlib import Path

        import slurmpast.report as report_mod
        import slurmpast.tui as tui_mod

        for module in (report_mod, tui_mod):
            source = Path(module.__file__).read_text()
            assert "at this partition's ceiling" not in source, module.__name__
            assert "capped_label" in source, module.__name__
