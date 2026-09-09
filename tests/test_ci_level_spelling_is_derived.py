"""Every spelling of the confidence level answers to `Z`.

Round sixty-eight published the level in `--nodes --json` and left this on its
Still-open list: the level is literal text in **six** places while `Z` is what
decides the interval, so raising `Z` would leave five sentences lying.

The six split into two kinds, and they are treated differently on purpose:

* **The prose.** `_note_from_row` builds the allocation note in `nodes.py` --
  the one place both front ends share, because `render` imports this module and
  the analysis modules may not import `render`. It carried a hardcoded `95%% CI`
  and now takes `CONFIDENCE_PERCENT`.
* **The three layout-coupled spellings.** `render.NODE_COLUMNS`' label declares
  a WIDTH beside it (`Column("95% CI", 18, ...)`, and `render.table_floor`
  records that `NODE_COLUMNS` bottoms out at 41 cells), and `report.py` and
  `tui.py` key their row dicts BY that label, so all three must be one string.
  Rebuilding them is a layout change; they are pinned against the derived value
  instead, so raising `Z` fails here and names all three.

The two docstrings that quote `95% CI` as an example are prose about the format
and are left alone -- `duration.py:310` is explaining `ci_range`'s spelling and
`cli.py:503` is a worked example of the note.
"""

import math
import pathlib
import re

import pytest

from slurmpast import nodes as nodes_mod
from slurmpast.nodes import (
    CONFIDENCE_LEVEL,
    CONFIDENCE_PERCENT,
    Z,
    _note_from_row,
    format_rate_range,
    node_table,
)
from slurmpast.render import NODE_COLUMNS

from .test_nodes import _placements

#: The label as all three layout-coupled sites must spell it.
CI_LABEL = "%s%% CI" % CONFIDENCE_PERCENT


@pytest.fixture
def row():
    """The one row whose verdict is `worse`, which is what the note needs."""
    jobs = _placements("midway3-0385", 19, 36) + _placements(
        "midway3-0600", 12, 218, job_id_base=5000
    )
    rows = {r["node"]: r for r in node_table(jobs, workload="node-evaluation")["rows"]}
    return rows["midway3-0385"]


def _source(module):
    return pathlib.Path(str(module.__file__)).read_text()


class TestTheSpellingIsDerived:
    def test_the_percent_string_comes_from_z(self):
        """`%g` of the level to one decimal: 95.00042 -> "95", not a typed 95.

        Asserted through `Z` rather than through `CONFIDENCE_LEVEL` alone, so the
        whole chain from the critical value to the printed string is pinned.
        """
        assert math.erf(Z / math.sqrt(2.0)) == CONFIDENCE_LEVEL
        assert "%g" % round(CONFIDENCE_LEVEL * 100, 1) == CONFIDENCE_PERCENT
        assert CONFIDENCE_PERCENT == "95"

    def test_a_different_z_would_spell_a_different_level(self):
        """Vacuity guard. Without this every assertion below would hold against
        a hardcoded "95"."""
        other = math.erf(2.5758293035489004 / math.sqrt(2.0))
        assert "%g" % round(other * 100, 1) == "99"
        assert "%g" % round(other * 100, 1) != CONFIDENCE_PERCENT

    def test_the_prose_note_does_not_spell_the_level_itself(self):
        """The source pin -- and the only thing that catches this fix being
        undone, because restoring the hardcoded `95` renders identically today.
        A drift neuter is what the behavioural test below is for."""
        source = _source(nodes_mod)
        # ANY hardcoded level, not just the current one: a drift to `99%% CI`
        # left a check for the literal "95" silent, which is the whole failure
        # mode this pin exists for.
        typed = re.findall(r"\d+%% CI", source)
        assert typed == [], typed
        assert "CONFIDENCE_PERCENT" in source

    def test_the_note_carries_the_derived_level(self, row):
        """The behavioural half: whatever `Z` implies is what the reader sees."""
        note = _note_from_row(row, workload="node-evaluation")
        assert CI_LABEL in note, note

    def test_the_column_label_is_derived_not_typed(self):
        """Round sixty-nine PINNED these three sites against the derived value;
        round seventy makes them derive from it, so the pin inverts.

        The assertion that used to live here -- that `report.py` and `tui.py`
        each CONTAIN the literal, because they key their row dicts by the column
        label -- is now the thing that must not be true. They reference
        `render.CI_COLUMN` instead, and `render` builds it from
        `nodes.CONFIDENCE_PERCENT`.
        """
        from slurmpast.render import CI_COLUMN

        assert CI_COLUMN == CI_LABEL
        labels = [c.label for c in NODE_COLUMNS if "CI" in c.label]
        assert labels == [CI_COLUMN], labels

        import slurmpast.render as render_mod
        import slurmpast.report as report_mod
        import slurmpast.tui as tui_mod

        for module in (report_mod, tui_mod):
            source = _source(module)
            assert '"%s"' % CI_LABEL not in source, module.__name__
            assert "CI_COLUMN" in source, module.__name__
        # One spelling in the whole chain, and it is the derivation itself.
        render_source = _source(render_mod)
        assert '"%s"' % CI_LABEL not in render_source
        assert 'CI_COLUMN = "%s%% CI" % CONFIDENCE_PERCENT' in render_source


class TestControls:
    """Each passes with the hardcoded `95` restored in the sentence.

    They cover the figures and the layout the fix did not touch, so a neuter
    that reddens one of them means the change went further than the spelling.
    """

    def test_the_note_still_carries_its_other_figures(self, row):
        note = _note_from_row(row, workload="node-evaluation")
        assert "midway3-0385 failed 19 of 36 placements there" in note, note
        assert "52.8%" in note, note
        assert format_rate_range(row["ci_low"], row["ci_high"]) in note, note
        assert note.endswith("on every other node for node-evaluation."), note

    def test_a_healthy_node_still_gets_no_note(self):
        """The quiet branch: `verdict != "worse"` returns "" before any
        formatting happens, so the spelling never arises."""
        jobs = _placements("midway3-0385", 19, 36) + _placements(
            "midway3-0600", 12, 218, job_id_base=5000
        )
        rows = {r["node"]: r for r in node_table(jobs, workload="node-evaluation")["rows"]}
        assert _note_from_row(rows["midway3-0600"]) == ""

    def test_the_column_keeps_its_declared_width(self):
        """The reason the three coupled spellings are pinned and not rebuilt."""
        column = [c for c in NODE_COLUMNS if "CI" in c.label][0]
        assert column.width == 18
        assert column.align == "right"

    def test_the_other_trials_clause_is_unaffected(self, row):
        note = _note_from_row(row, workload=None, other_trials=7)
        assert "over 7 placements on every other node." in note, note
