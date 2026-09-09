"""One interval, one spelling, on every surface that prints it.

`render.ci_range` exists because `report` wrote ``"%.1f - %.1f%%"`` and `tui`
wrote ``"%.1f – %.1f%%"``, so a hyphen and an en dash stood in the same table
cell depending on which screen you were looking at. The node note then spelled it
a **third** way -- ``95% CI 84.7-99.5%``, hyphenated and unspaced.

Round forty-eight recorded that and left it open, reading the options as
"duplicate the format, re-creating exactly the drift `ci_range` prevents" or
"move the sentence out, which is the four-file change described above". There is a
third, which is what this closes: put the rule where **both** can reach it.
``duration`` imports nothing but ``math``, ``render`` already imports from it, and
``nodes`` may import it too -- so ``duration.format_rate_range`` owns the format
and both callers ask it.

The en dash is safe in the note for the reason it is safe in the table:
``render.ascii_fold`` maps it to a hyphen and ``report._fold`` applies that once
per view over the finished text. Rendered on job 53363721_35, the note reads
``95% CI 84.7 – 99.5%`` normally and ``95% CI 84.7 - 99.5%`` under ``--ascii``,
matching the table's cell in both.
"""

from slurmpast.duration import format_rate_range
from slurmpast.model import Job
from slurmpast.nodes import _note_from_row, node_table
from slurmpast.render import ascii_fold, ci_range


def _rows(spec):
    jobs = []
    for node, count, state in spec:
        for i in range(count):
            jobs.append(
                Job(
                    job_id="%s%d" % (node, i),
                    name="w",
                    node_list=node,
                    elapsed=600.0,
                    timelimit=3600.0,
                    state=state,
                )
            )
    return node_table(jobs, workload="w")


def test_the_note_and_the_table_spell_the_interval_identically():
    """The two surfaces, asked for the same two numbers."""
    table = _rows([("nodeA", 10, "FAILED"), ("nodeB", 200, "COMPLETED")])
    row = next(r for r in table["rows"] if r["node"] == "nodeA")
    cell = ci_range(row["ci_low"], row["ci_high"])
    note = _note_from_row(row, None, table["trials"] - row["trials"])
    assert cell in note, (cell, note)


def test_render_delegates_rather_than_keeping_its_own_copy():
    """``ci_range`` must not re-derive the format, or the two can drift again."""
    assert ci_range(0.722, 1.0) == format_rate_range(0.722, 1.0)
    assert format_rate_range(0.246, 0.577) == "24.6 – 57.7%"


def test_control_the_ascii_fold_still_yields_the_old_bytes():
    """CONTROL, passing with the change present or absent.

    An en dash that did not fold would put a non-ASCII byte into piped output.
    ``--ascii`` must give exactly the hyphenated form the note used to print.
    """
    assert ascii_fold(format_rate_range(0.847, 0.995)) == "84.7 - 99.5%"
    assert ascii_fold(ci_range(0.246, 0.577)) == "24.6 - 57.7%"


def test_control_the_numbers_are_untouched():
    """CONTROL, in both states. A spelling fix must not move a figure.

    Asserted off ``node_table``'s own interval rather than off the sentence, so
    agreeing with the renderer cannot make this pass.
    """
    table = _rows([("nodeA", 10, "FAILED"), ("nodeB", 200, "COMPLETED")])
    row = next(r for r in table["rows"] if r["node"] == "nodeA")
    note = _note_from_row(row, None, table["trials"] - row["trials"])
    assert "%.1f" % (100 * row["ci_low"]) in note
    assert "%.1f" % (100 * row["ci_high"]) in note
    assert "failed 10 of 10 placements there" in note


def test_control_duration_stays_free_of_third_party_imports():
    """CONTROL, in both states, and the architectural rule that makes this work.

    The format could only move to ``duration`` because ``nodes`` may import it.
    That holds only while ``duration`` imports no third-party package -- if it
    ever grows a ``rich`` import, this fix becomes an architecture violation.
    """
    import ast
    import pathlib
    import sys

    src = pathlib.Path(__file__).resolve().parent.parent / "src" / "slurmpast" / "duration.py"
    roots = set()
    for node in ast.walk(ast.parse(src.read_text())):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    # Against the stdlib rather than a hardcoded name: the rule is "no THIRD-PARTY
    # import", and pinning the exact set would fail the next stdlib helper someone
    # legitimately reaches for. (`stdlib_module_names` is 3.10+, which is this
    # package's floor -- rapidu, whose floor is 3.6, has to guard the same call.)
    third_party = roots - set(sys.stdlib_module_names) - {"slurmpast"}
    assert not third_party, third_party
