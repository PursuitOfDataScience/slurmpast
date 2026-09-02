"""When the node's note says how big the thing it was compared against is.

``_note_from_row`` was scrupulous about its own denominator -- "failed 32 of 33
placements there", a wording round forty-seven settled -- and then gave the
comparison as a bare "against 3.4% on every other node", with nothing to say
whether that rate came from thirteen thousand placements or from two.

Round fifty measured the reachable case and declined to close it statistically:
``node_table`` applies no ``MIN_HISTORY`` and ``--nodes`` calls it directly, so a
short window reaches a two-placement comparison, but a count floor on
``other_trials`` suppressed a p=0.000722 finding the demo exists to show while
the case worth worrying about was p=0.015152. The p-value already prices a thin
comparison arm. What was left open there is this: say how thin it is.

**The bar is derived, not picked.** Disclosed only when ``other_trials`` is below
``row["trials"]`` -- when the thing being compared against rests on fewer
placements than the node being accused, so the reader can see which half of the
sentence is thin. Above it the figure is never surprising (13,497 against a
node's 344 on this cluster's real 90-day history) and 25 characters of a
one-line job-screen note would buy nothing. The common case is therefore
byte-identical, which is what keeps round forty-seven's "only the noun moved"
control true.
"""

from slurmpast.model import Job
from slurmpast.nodes import _note_from_row, node_table, note_for_node


def _history(spec):
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
    return jobs


def _note(spec, node="nodeA"):
    jobs = _history(spec)
    table = node_table(jobs, workload="w")
    row = next(r for r in table["rows"] if r["node"] == node)
    return _note_from_row(row, None, table["trials"] - row["trials"])


def test_a_thin_comparison_names_its_population():
    """10 of 10 failed on nodeA, against two clean placements elsewhere.

    "against 0.0% on every other node" is true and unreadable: every other node
    is two placements. The reader gets the number and can weigh it.
    """
    note = _note([("nodeA", 10, "FAILED"), ("nodeB", 2, "COMPLETED")])
    assert "against 0.0% over 2 placements on every other node" in note, note
    # its own denominator is still there, unchanged
    assert "failed 10 of 10 placements there" in note, note


def test_the_bar_is_the_nodes_own_sample_size():
    """The boundary, both sides. Below ``trials`` it speaks; at or above, silent.

    Not a control -- the disclosing half fails without the change -- and both
    halves are needed, because a fix that always disclosed would satisfy the
    first and fail the second.
    """
    # 9 others against 10 of its own: thinner, so named
    below = _note([("nodeA", 10, "FAILED"), ("nodeB", 9, "COMPLETED")])
    assert "over 9 placements" in below, below

    # 10 against 10: not thinner, so the sentence stays as it was
    at = _note([("nodeA", 10, "FAILED"), ("nodeB", 10, "COMPLETED")])
    assert "over" not in at, at
    assert "against 0.0% on every other node" in at, at


def test_control_a_large_comparison_keeps_the_sentence_it_had():
    """CONTROL, passing with the change present or absent.

    The common case, and the one every real reader sees: a comparison far larger
    than the node's own sample adds nothing, so the wording is untouched. This is
    what makes the change invisible on a real history.
    """
    note = _note([("nodeA", 10, "FAILED"), ("nodeB", 200, "COMPLETED")])
    assert "against 0.0% on every other node" in note, note
    assert "placements on every other node" not in note, note
    assert "failed 10 of 10 placements there" in note, note


def test_control_b_every_figure_the_sentence_already_carried_is_unchanged():
    """CONTROL, passing in both states. Round forty-seven's control, restated.

    A wording fix that moved a number would be a different defect. The rate, the
    interval and both counts are asserted off the table rather than off the
    sentence, so agreeing with the implementation cannot make this pass.
    """
    jobs = _history([("nodeA", 10, "FAILED"), ("nodeB", 200, "COMPLETED")])
    table = node_table(jobs, workload="w")
    row = next(r for r in table["rows"] if r["node"] == "nodeA")
    assert (row["bad"], row["trials"]) == (10, 10)
    note = _note_from_row(row, None, table["trials"] - row["trials"])
    assert note.startswith("nodeA failed 10 of 10 placements there (100.0%,")
    assert "95% CI 72.2-100.0%" in note, note


def test_control_c_a_caller_without_the_table_keeps_the_old_wording():
    """CONTROL, passing in both states.

    ``other_trials=None`` is the fallback for a caller holding a row but not the
    table it came from. It must not invent a population, and must not warn.
    """
    jobs = _history([("nodeA", 10, "FAILED"), ("nodeB", 2, "COMPLETED")])
    table = node_table(jobs, workload="w")
    row = next(r for r in table["rows"] if r["node"] == "nodeA")
    note = _note_from_row(row, None)
    assert "against 0.0% on every other node" in note, note
    assert "over" not in note, note


def test_both_front_ends_get_the_population_from_one_builder():
    """``note_for_node`` goes through the same builder, so it says it too.

    Not a control -- it fails without the change, which is the point.

    ``render.py`` exists so the dashboard and ``--plain`` cannot drift; the note
    is built in ``nodes`` precisely so there is one spelling of it. A change that
    threaded the population into only one caller would pass everything above.
    """
    jobs = _history([("nodeA", 10, "FAILED"), ("nodeB", 2, "COMPLETED")])
    assert "over 2 placements" in note_for_node(jobs, "nodeA", workload="w")
