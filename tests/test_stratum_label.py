"""The note names the stratum it pooled, not one job inside it.

`Workload.matches` normalises before comparing, so the stratum a node comparison
holds fixed IS the fold. `dominant_workload` prints that fold, substituting a real
name only where the fold erased it -- `patterns.fold_erased_the_name` describes
itself as "only a *display* rule ... callers use this to decide whether the key is
fit to be read aloud". The note never applied it: `cli._node_note` and the
dashboard both build ``Workload(job.name, job.user)``, so the sentence carried one
job's RAW name over a finding pooled across every job in the fold.

Measured on this cluster's 90-day history (15,025 usable jobs): **92 of 1,258
folds hold more than one raw name**, and the largest, ``exp-n#``, spans **154
distinct names across 157 jobs**. So "for exp-n89" named one 157th of what the
sentence's own figures covered, while the nodes screen beside it said "only
exp-n# counted".

Round forty-eight recorded the two labels and declined, "because it could not be
reproduced as a wrong count, only as two labels". The count was never wrong. The
attribution was, and it reproduces.
"""

from slurmpast.model import Job
from slurmpast.nodes import Workload, _stratum_label, node_table, note_for_node
from slurmpast.patterns import fold_erased_the_name, normalize_name


def _fold_history(n_bad=30, n_good=200, name="exp-n%d"):
    """One fold, many raw names: nodeA fails every placement, nodeB none."""

    def nm(i):
        # `name` may be a constant (a one-name fold) or a template (a wide one).
        return name % i if "%" in name else name

    jobs = []
    for i in range(n_bad):
        jobs.append(
            Job(
                job_id="a%d" % i,
                name=nm(i),
                user="ada",
                node_list="nodeA",
                elapsed=600.0,
                timelimit=3600.0,
                state="FAILED",
            )
        )
    for i in range(n_bad, n_bad + n_good):
        jobs.append(
            Job(
                job_id="b%d" % i,
                name=nm(i),
                user="ada",
                node_list="nodeB",
                elapsed=600.0,
                timelimit=3600.0,
                state="COMPLETED",
            )
        )
    return jobs


def test_the_note_labels_the_fold_not_one_of_its_names():
    """230 names in one fold; the sentence must not pick one and imply it."""
    jobs = _fold_history()
    assert len({j.name for j in jobs}) == 230, "the fold has to be genuinely wide"
    assert normalize_name(jobs[0].name) == "exp-n#"

    note = note_for_node(jobs, "nodeA", workload=Workload("exp-n7", "ada"))
    assert note, "nodeA must earn a verdict for there to be a label at all"
    assert note.endswith("for exp-n#."), note
    assert "exp-n7" not in note, note


def test_control_a_single_name_fold_keeps_the_name_it_had():
    """CONTROL, passing with the change present or absent.

    The common case: a name with no digits folds to itself, so the label the
    reader sees is unchanged. A fix that always printed something else would
    pass the test above and fail this one.
    """
    jobs = _fold_history(name="sixdeg")
    assert normalize_name("sixdeg") == "sixdeg"
    note = note_for_node(jobs, "nodeA", workload=Workload("sixdeg", "ada"))
    assert note.endswith("for sixdeg."), note


def test_control_b_a_fold_with_no_name_left_keeps_the_raw_one():
    """CONTROL, in both states, and the fallback the display rule already has.

    An all-digit name folds to punctuation -- ``20260821`` to ``#`` -- which names
    nothing a reader can match to a job. The raw name is the better label there,
    which is exactly what `dominant_workload` does with `newest_name`.
    """
    jobs_2026 = _fold_history(name="2026082%d")
    assert fold_erased_the_name(normalize_name("20260821"))
    assert _stratum_label(Workload("20260821", "ada"), jobs_2026) == "20260821"
    note = note_for_node(jobs_2026, "nodeA", workload=Workload("20260821", "ada"))
    assert note.endswith("for 20260821."), note


def test_control_c_which_jobs_are_pooled_cannot_change():
    """CONTROL, in both states, and the premise that makes this label-only.

    `Workload.matches` normalises before comparing, so the raw name and the fold
    select the SAME stratum -- the reason `dominant_workload` gives for its own
    substitution. Asserted by running the table both ways and comparing the
    figures, not by trusting the docstring.
    """
    jobs = _fold_history()
    raw = node_table(jobs, workload=Workload("exp-n7", "ada"), metric="failure")
    folded = node_table(jobs, workload=Workload("exp-n#", "ada"), metric="failure")
    assert (raw["trials"], raw["hits"]) == (folded["trials"], folded["hits"]) == (230, 30)
    assert [r["node"] for r in raw["rows"]] == [r["node"] for r in folded["rows"]]
    for a, b in zip(raw["rows"], folded["rows"], strict=True):
        assert (a["bad"], a["trials"], a["verdict"]) == (b["bad"], b["trials"], b["verdict"])


def test_control_d_no_workload_still_means_no_suffix():
    """CONTROL, in both states. `--all-workloads` passes no stratum at all."""
    jobs = _fold_history()
    assert _stratum_label(None, jobs) is None
    assert _stratum_label("", jobs) == ""
    jobs = _fold_history()
    note = note_for_node(jobs, "nodeA", workload=None)
    assert note and " for " not in note, note


def test_control_e_a_single_name_stratum_keeps_its_digits():
    """CONTROL, passing with the change present or absent, and the one I got wrong.

    A name WITH digits whose fold pools only itself must keep the specific label:
    ``caai-p10b_scan`` is what the reader submitted, ``caai-p#b_scan`` is a
    pattern they never typed. Folding unconditionally traded a true, specific
    label for a true, vaguer one and broke two of `test_nodes.py`'s assertions --
    which were right to object.

    1,166 of this history's 1,258 folds are this shape, so it is the common case.
    """
    jobs = _fold_history(name="caai-p10b_scan")
    assert normalize_name("caai-p10b_scan") == "caai-p#b_scan", "the fold does differ"
    assert _stratum_label(Workload("caai-p10b_scan", "ada"), jobs) == "caai-p10b_scan"
    note = note_for_node(jobs, "nodeA", workload=Workload("caai-p10b_scan", "ada"))
    assert note.endswith("for caai-p10b_scan."), note
