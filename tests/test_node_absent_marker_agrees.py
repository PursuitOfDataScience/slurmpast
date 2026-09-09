"""The two surfaces disagreed about how to say a job has no node.

`CLAUDE.md` states the rule this file checks: "`render.py` exists so the dashboard
and `--plain` cannot drift. A change to one surface that the other also draws
belongs in `render.py`, not in both." The job table is drawn by both, from the
same twelve `JOB_COLUMNS`, and eleven of them agreed. The twelfth did not:

    report.py:765   "NODE": job.node_list or "-"
    tui.py          "NODE": Text(job.node_list or "")     <-- blank, not "-"

The convention was already settled everywhere else in that same dict. STARTED,
ENDED and GPU all write `or "-"` on both sides; NAME writes `or ""` on both,
which is right for free text where `-` could be a real name. NODE was the single
outlier, and it was the TUI that differed.

It matters because a job with no node list is a real state, not an inapplicable
column: pending, or cancelled before it was ever allocated. An empty cell reads
as "this column does not apply to this row"; `-` is this tool's marker for a
value it does not have -- which is the same distinction the package draws
everywhere between an absence and a zero.

The width computations still use `or ""` on both sides and that is correct: they
size the column, and an absent value contributes no characters. The heading
"NODE" is four wide, so a one-character `-` cannot be truncated by it.
"""

from __future__ import annotations

import re

import pytest

from slurmpast import report
from slurmpast.model import Job
from slurmpast.render import JOB_COLUMNS

PLAIN = report.Style()

#: Columns whose absent-marker must be identical on both surfaces, and what it is.
#: Read off the two sources rather than restated, so the test cannot drift from
#: the code the way the code drifted from itself.
MARKER_COLUMNS = ("STARTED", "ENDED", "GPU", "NODE")


def _jobs_with_one_nodeless() -> tuple[list[Job], Job]:
    """`Job` is a NamedTuple, so the nodeless one is built, not mutated."""
    nodeless = Job(job_id="4242", name="exp-a5", node_list="")
    withnode = Job(job_id="4243", name="exp-a6", node_list="midway3-0042")
    return [nodeless, withnode], nodeless


def _plain_cells(jobs: list[Job]) -> list[str]:
    """`render_list` returns ONE STRING, not a list of lines.

    Iterating it directly walks characters, which is how an earlier draft of this
    file compared `'J O B I D'` against `'JOBID'` and failed for the wrong reason.
    """
    out = report.render_list(jobs, style=PLAIN, limit=len(jobs))
    assert isinstance(out, str), type(out)
    return out.splitlines()


def _cell_source(path: str, column: str) -> str:
    """The CELL expression for `column`, not the width computation."""
    import pathlib

    text = pathlib.Path(path).read_text()
    for line in text.splitlines():
        if f'"{column}":' in line and "max((len(" not in line:
            return line.strip()
    raise AssertionError(f"no cell line for {column} in {path}")


class TestTheAbsentMarkerIsTheSameOnBothSurfaces:
    @pytest.mark.parametrize("column", MARKER_COLUMNS)
    def test_both_surfaces_use_the_same_marker(self, column: str) -> None:
        plain = _cell_source("src/slurmpast/report.py", column)
        tui = _cell_source("src/slurmpast/tui.py", column)
        got_plain = re.search(r'or "([^"]*)"', plain)
        got_tui = re.search(r'or "([^"]*)"', tui)
        assert got_plain and got_tui, (plain, tui)
        assert got_plain.group(1) == got_tui.group(1), (
            f"{column}: --plain says {got_plain.group(1)!r}, "
            f"the dashboard says {got_tui.group(1)!r}"
        )

    def test_the_node_marker_is_a_dash_on_both(self) -> None:
        for path in ("src/slurmpast/report.py", "src/slurmpast/tui.py"):
            assert 'or "-"' in _cell_source(path, "NODE"), path

    def test_the_dashboard_builds_the_same_string(self) -> None:
        # Read from the TUI's own cell expression rather than mounting a screen:
        # the value is what drifted, and it is a literal in that line.
        assert 'Text(job.node_list or "-"' in _cell_source("src/slurmpast/tui.py", "NODE")


class TestControls:
    """Behaviour that must not change. Each passes in BOTH states."""

    def test_the_plain_report_prints_a_dash_for_a_nodeless_job(self) -> None:
        """Passes in BOTH states -- only the TUI drifted, so this is a control.

        It is the SIDE THAT WAS RIGHT, and it is worth pinning: the fix aligned
        the dashboard to this output, so if this ever changed the alignment
        would silently point the wrong way.
        """
        jobs, target = _jobs_with_one_nodeless()
        rendered = _plain_cells(jobs)
        row = next((ln for ln in rendered if target.job_id in ln), None)
        assert row is not None, rendered[:6]
        # The NODE column is last, so an absent node shows as a trailing "-"
        # rather than nothing at all.
        assert row.rstrip().endswith("-"), row

    @pytest.mark.parametrize("column", ("STARTED", "ENDED", "GPU"))
    def test_the_already_agreeing_markers_are_untouched(self, column: str) -> None:
        for path in ("src/slurmpast/report.py", "src/slurmpast/tui.py"):
            assert 'or "-"' in _cell_source(path, column), (path, column)

    def test_name_still_uses_an_empty_string_on_both(self) -> None:
        # Right for free text: `-` could be an actual job name.
        for path in ("src/slurmpast/report.py", "src/slurmpast/tui.py"):
            assert 'or ""' in _cell_source(path, "NAME"), path

    def test_the_width_computations_still_use_an_empty_string(self) -> None:
        # They size the column; an absent value contributes no characters.
        import pathlib

        for path in ("src/slurmpast/report.py", "src/slurmpast/tui.py"):
            text = pathlib.Path(path).read_text()
            sizing = [ln for ln in text.splitlines() if '"NODE":' in ln and "max((len(" in ln]
            assert sizing, path
            assert all('or ""' in ln for ln in sizing), sizing

    def test_a_job_with_a_node_still_shows_it(self) -> None:
        jobs, _ = _jobs_with_one_nodeless()
        withnode = next(j for j in jobs if j.node_list)
        rendered = _plain_cells(jobs)
        row = next((ln for ln in rendered if withnode.job_id in ln), None)
        assert row is not None
        assert withnode.node_list in row, (withnode.node_list, row)

    def test_the_node_heading_is_wider_than_the_marker(self) -> None:
        # Why the width hint can stay at 0: the heading floors the column.
        node = next(c for c in JOB_COLUMNS if c.label == "NODE")
        assert len(node.label) >= len("-")

    def test_the_plain_report_still_renders_every_column(self) -> None:
        jobs, _ = _jobs_with_one_nodeless()
        header = _plain_cells(jobs)
        joined = " ".join(header)
        for column in ("JOBID", "STATE", "WALL TIME", "PEAK MEM", "NODE"):
            assert column in joined, column
