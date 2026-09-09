"""Two `--plain` notes went out at whatever length they happened to be.

`report.py` has a rule about this and states it in `_prose_width`'s own docstring:
the paragraph widths "were hardcoded at 72, 82 and 84, so a finding hard-broke
mid-sentence two thirds of the way across a wide terminal and overran a narrow
one." Nine paragraphs are wrapped through `wrap(..., _prose_width(n))`. Two were
not, and both were measured overrunning a real terminal:

    slurmpast --overview -S now-14days, COLUMNS=90
      [109]   40,994 rows parsed, about 40.0 MiB held - a window ten times ...
    ... and at COLUMNS=60
      [63]   ... 354 more workloads (8262 runs) holding 14.0% of the compute

The memory-footprint note is 109 cells on a real history and so overran at EVERY
width tested (60, 70, 80, 90, 100) -- including the 90 and 100 the owner's
terminals are. The tail summary is 63 and overruns only at `PLAIN_MIN_WIDTH`, the
floor `_plain_width` clamps to.

Neither is drawn by the dashboard (checked: `tui.py` and `render.py` mention
neither), so this is a `--plain` fix with no second surface to keep in step.

The tail keeps a hanging indent -- `  ... ` then four spaces -- because its
continuation sits directly under a table, and a continuation line flush with the
rows above reads as another row.
"""

from __future__ import annotations

import pytest

from slurmpast import report
from slurmpast.demo import history as demo_history
from slurmpast.index import History

PLAIN = report.Style()

#: Widths a real terminal is, plus `PLAIN_MIN_WIDTH` (60) which is where
#: `_plain_width` stops shrinking.
WIDTHS = [60, 70, 80, 90, 100, 120]

#: A row count above `_FOOTPRINT_NOTE_ROWS`, from the measured history.
BIG_ROWS = 40_994


def _history(rows: int = BIG_ROWS) -> History:
    """The demo history with a real cluster's row count on it.

    `stats` is a plain dict attribute, so the count is set rather than faked
    through a subclass -- the note reads exactly this key.
    """
    h = History(demo_history())
    h.stats["parsed_rows"] = rows
    return h


def _lines(width: int, rows: int = BIG_ROWS, limit: int = 2) -> list[str]:
    import os
    from unittest import mock

    with mock.patch.dict(os.environ, {"COLUMNS": str(width)}):
        out = report.render_overview(_history(rows), style=PLAIN, limit=limit)
    return out.splitlines()


#: The footprint note in full, so "wrapped" can be told from "truncated".
FOOTPRINT = (
    "40,994 rows parsed, about 40.0 MiB held — a window ten times longer "
    "costs ten times that; narrow it with -S"
)


#: The tail summary a real 14-day history produced: 63 cells with its leader.
REAL_TAIL = "354 more workloads (8262 runs) holding 14.0% of the compute"


def _tail(text: str):
    """Force `tail_summary` to a given string, to drive the print site."""
    from unittest import mock

    return mock.patch.object(History, "tail_summary", lambda self, shown, ordered=None: text)


def _flat(lines: list[str]) -> str:
    """Every line joined, so a sentence can be found wherever the break fell."""
    return " ".join(ln.strip() for ln in lines)


def _hanging(lines: list[str], needle: str) -> list[str]:
    """A note found by `needle`, plus the lines hanging under it (4-space indent).

    Only the tail summary is indented that way; the table's rows and the other
    notes sit at two.
    """
    start = next(i for i, ln in enumerate(lines) if needle in ln)
    note = [lines[start]]
    for ln in lines[start + 1 :]:
        if not ln.startswith("    ") or not ln.strip():
            break
        note.append(ln)
    return note


class TestNoNoteOverrunsTheTerminal:
    @pytest.mark.parametrize("width", WIDTHS)
    def test_every_line_fits(self, width: int) -> None:
        """The reported symptom, at every width including the floor."""
        over = [ln for ln in _lines(width) if report._visible_len(ln) > width]
        assert over == [], (width, [(report._visible_len(ln), ln) for ln in over])

    @pytest.mark.parametrize("width", [60, 90, 100])
    def test_the_footprint_note_is_wrapped_not_truncated(self, width: int) -> None:
        # Wrapping may put the break anywhere; nothing may be lost to it.
        assert FOOTPRINT in _flat(_lines(width)), _flat(_lines(width))

    @pytest.mark.parametrize("width", [60, 90, 100])
    def test_the_footprint_note_really_did_have_to_break(self, width: int) -> None:
        # Vacuity guard: if it fitted on one line, the test above proves nothing.
        assert not [ln for ln in _lines(width) if FOOTPRINT in ln], width

    def test_the_tail_summary_wraps_with_a_hanging_indent(self) -> None:
        """Driven with the real cluster's tail, which is the one that overran.

        The demo's own tail is 54 cells and fits at 60 -- the control below pins
        that it still does -- so the overrun is reproduced with the string a
        14-day history on midway3 actually produced.
        """
        with _tail(REAL_TAIL):
            note = _hanging(_lines(60), "more workload")
        assert note[0].startswith("  … ") or note[0].startswith("  ... "), note[0]
        assert len(note) > 1, note  # 63 cells against a 60-cell floor
        for ln in note[1:]:
            assert ln.startswith("    "), ln
        assert REAL_TAIL in _flat([ln.lstrip("… ") for ln in note]), note

    def test_the_tail_summary_keeps_its_numbers(self) -> None:
        h = _history()
        expected = h.tail_summary(2, ordered=h.groups)
        assert expected in _flat(_lines(60)), (expected, _flat(_lines(60)))


class TestControls:
    """Behaviour that must not change. Each passes in BOTH states."""

    def test_a_wide_terminal_still_keeps_each_note_on_one_line(self) -> None:
        # Wrapping must not introduce a break where there is room.
        lines = _lines(150)
        assert [ln for ln in lines if FOOTPRINT in ln], lines
        assert len(_hanging(lines, "more workload")) == 1
        with _tail(REAL_TAIL):
            assert len(_hanging(_lines(150), "more workload")) == 1

    def test_the_demo_tail_still_fits_the_narrow_floor_on_one_line(self) -> None:
        # 54 cells plus its leader: it never needed wrapping and must not get it.
        assert len(_hanging(_lines(60), "more workload")) == 1

    def test_a_small_history_still_gets_no_footprint_note(self) -> None:
        # The note is deliberately conditional: on an ordinary window it is a
        # line in the way.
        lines = _lines(90, rows=174)
        assert not [ln for ln in lines if "rows parsed" in ln], lines

    def test_the_threshold_itself_still_prints_the_note(self) -> None:
        assert [ln for ln in _lines(120, rows=report._FOOTPRINT_NOTE_ROWS) if "rows parsed" in ln]
        assert not [
            ln for ln in _lines(120, rows=report._FOOTPRINT_NOTE_ROWS - 1) if "rows parsed" in ln
        ]

    def test_no_limit_still_prints_no_tail_summary(self) -> None:
        # `-n 0` is no limit, and nothing is below a fold that does not exist.
        h = _history()
        assert h.tail_summary(None) == ""

    def test_the_other_notes_are_untouched(self) -> None:
        lines = _lines(100)
        joined = "\n".join(lines)
        assert "window" in joined
        assert "ordered by compute used" in joined

    def test_the_table_still_renders_its_columns(self) -> None:
        joined = "\n".join(_lines(120, limit=8))
        for column in ("WORKLOAD", "RUNS"):
            assert column in joined.upper(), column
