"""The repeat-failure action said two things that were not true of an array.

`issues.md` recorded this as **B, "reported, not changed"**: "`Stop resubmitting`
is said to workloads that were submitted once." Every element of a job array is
its own sacct record with its own `JobID`, and `group_key` folds them into one
workload — rightly, since each element is an allocation that really ran and burned
resource, which `TestArraySiblingsAlreadyCountAsEvidence` pins on purpose. What
had drifted is the ACTION text, which assumed M submissions.

Re-measured on a live 30-day history before anything was touched, and it is worse
than the entry recorded — the determinism claim is false on a second workload the
entry never named::

    cpas_audit  n=11  distinct_masters=1  {FAILED: 8, COMPLETED: 3}
      action: Stop resubmitting; the failure is deterministic. Reproduce interactively.
    cpas_G1     n=100 distinct_masters=1  50 failed / 50 completed
      action: Stop resubmitting; the failure is deterministic. Reproduce interactively.

`cpas_audit` is ONE `sbatch --array`: there is nothing to stop resubmitting. And
three of its eleven tasks COMPLETED, so the failure is not deterministic either —
while `cpas_G1` completed half its runs and was told the same thing.

Both are now said only when they are true, from the two facts the record already
carries: the master id (everything before the `_`) and `Job.completed`. After::

    evidence: ... All 11 are tasks of one array (job 53410199).
    action  : One array submission, not repeated ones: reproduce a single task
              interactively rather than resubmitting the array. 3 of 11 tasks
              completed, so the failure is not deterministic — compare a failed
              one against a completed one.

**The counts are deliberately unchanged.** "8 of 11 runs failed" stays, because
the entry's own constraint is that this must not be fixed by exempting arrays from
the grouping: the eleven allocations happened. Only the advice moved, and the
severity is still `fraction > 0.8`, untouched — `TestControls` pins that no group
starts or stops firing and that no severity moves.

The `newest_name` docstring correction (**C** in the same entry) is pinned here too:
it claimed `index.build_groups` orders members with `numeric_job_id` breaking the
tie, and `build_groups` sorts on `_stamp` alone. The tie-break is real but it is
this function's own, and ties are the ordinary case for an array whose tasks share
a Submit.
"""

from __future__ import annotations

from typing import Any

from slurmpast.patterns import find_repeat_failures, newest_name
from slurmpast.sacct import parse

FIELDS = [
    "JobID",
    "JobName",
    "User",
    "Partition",
    "State",
    "ExitCode",
    "Submit",
    "Start",
    "End",
    "Elapsed",
    "ReqMem",
    "AllocTRES",
]


def _row(**kw: Any) -> str:
    base = {
        "JobID": "100",
        "JobName": "trainer",
        "User": "youzhi",
        "Partition": "test",
        "State": "FAILED",
        "ExitCode": "1:0",
        "Submit": "2026-06-01T01:00:00",
        "Start": "2026-06-01T01:00:01",
        "End": "2026-06-01T01:10:00",
        "Elapsed": "00:10:00",
        "ReqMem": "8G",
        "AllocTRES": "cpu=4,mem=8G",
    }
    base.update({k: str(v) for k, v in kw.items()})
    return "|".join(base[f] for f in FIELDS)


def _jobs(ids: list[str], states: list[str]) -> list[Any]:
    rows = []
    for offset, (job_id, state) in enumerate(zip(ids, states, strict=True)):
        day = "2026-06-%02d" % (offset + 1)
        rows.append(
            _row(
                JobID=job_id,
                State=state,
                Submit="%sT01:00:00" % day,
                Start="%sT01:00:01" % day,
                End="%sT01:10:00" % day,
            )
        )
    return parse("\n".join(rows), fields=FIELDS, delimiter="|")


def _finding(jobs: list[Any]) -> Any:
    found = [f for f in find_repeat_failures(jobs) if f.action]
    assert found, "the detector did not fire on this fixture"
    return found[0]


#: One `sbatch --array` of 8 tasks, 6 failed and 2 completed — the reported shape.
ONE_ARRAY = (
    ["53410199_%d" % i for i in range(1, 9)],
    ["FAILED"] * 6 + ["COMPLETED"] * 2,
)
#: Eight separate submissions, none of which completed — the classic case.
EIGHT_SUBMISSIONS = ([str(100 + i) for i in range(8)], ["FAILED"] * 8)


class TestAnArrayIsNotToldToStopResubmitting:
    def test_the_action_does_not_say_stop_resubmitting(self) -> None:
        action = _finding(_jobs(*ONE_ARRAY)).action
        assert "Stop resubmitting" not in action, action
        assert "one array submission" in action.lower(), action

    def test_the_evidence_names_the_array(self) -> None:
        evidence = _finding(_jobs(*ONE_ARRAY)).evidence
        assert "tasks of one array (job 53410199)" in evidence, evidence

    def test_the_counts_still_describe_every_task(self) -> None:
        # The entry's own constraint: siblings are evidence, so the numbers stay.
        evidence = _finding(_jobs(*ONE_ARRAY)).evidence
        assert "6 of 8 runs" in evidence, evidence


class TestDeterminismIsNotClaimedOverASuccess:
    def test_a_workload_with_completions_is_not_called_deterministic(self) -> None:
        action = _finding(_jobs(*ONE_ARRAY)).action
        assert "is not deterministic" in action, action
        assert "the failure is deterministic." not in action, action

    def test_it_names_how_many_completed(self) -> None:
        action = _finding(_jobs(*ONE_ARRAY)).action
        assert "2 of 8 tasks completed" in action, action

    def test_separate_submissions_with_completions_say_runs_not_tasks(self) -> None:
        ids = [str(200 + i) for i in range(8)]
        action = _finding(_jobs(ids, ["FAILED"] * 6 + ["COMPLETED"] * 2)).action
        assert "2 of 8 runs completed" in action, action
        assert "one array submission" not in action.lower(), action


class TestTheNewestNameTieBreakIsItsOwn:
    """C: the docstring claimed `build_groups` shares this tie-break. It does not."""

    def test_a_tie_is_broken_on_the_job_id(self) -> None:
        # Same Submit AND Start, as an array's tasks have, so only the id can order
        # them. Built by parsing, because `Job` is immutable.
        rows = [
            _row(JobID="77_1", JobName="first"),
            _row(JobID="77_2", JobName="second"),
        ]
        jobs = parse("\n".join(rows), fields=FIELDS, delimiter="|")
        assert {j.submit for j in jobs} == {jobs[0].submit}, "the fixture is not a tie"
        assert newest_name(jobs) == "second", [j.name for j in jobs]

    def test_build_groups_sorts_on_the_stamp_alone(self) -> None:
        import inspect

        from slurmpast import index

        src = inspect.getsource(index.build_groups)
        assert "members.sort(key=lambda j: _stamp(j), reverse=True)" in src, src
        assert "numeric_job_id" not in src, "build_groups has no second key"


class TestControls:
    """Behaviour that must not change. Each passes in BOTH states."""

    def test_the_classic_sentence_is_untouched(self) -> None:
        action = _finding(_jobs(*EIGHT_SUBMISSIONS)).action
        assert action == (
            "Stop resubmitting; the failure is deterministic. Reproduce interactively."
        ), action

    def test_the_finding_still_fires_on_both_shapes(self) -> None:
        for ids, states in (ONE_ARRAY, EIGHT_SUBMISSIONS):
            assert [f for f in find_repeat_failures(_jobs(ids, states)) if f.action]

    def test_the_severity_is_still_the_failure_fraction(self) -> None:
        # 6/8 = 0.75, not > 0.8, so WARNING on both shapes; the wording must not
        # have moved the grade.
        for ids, states in (ONE_ARRAY, ([str(300 + i) for i in range(8)], ONE_ARRAY[1])):
            finding = _finding(_jobs(ids, states))
            assert finding.severity == "warning", (finding.severity, ids[0])

    def test_a_full_array_wipeout_is_still_critical(self) -> None:
        ids = ["999_%d" % i for i in range(1, 9)]
        finding = _finding(_jobs(ids, ["FAILED"] * 8))
        assert finding.severity == "critical", finding.severity

    def test_a_timeout_group_keeps_its_own_action(self) -> None:
        ids = ["888_%d" % i for i in range(1, 9)]
        action = _finding(_jobs(ids, ["TIMEOUT"] * 8)).action
        assert "Raise --time" in action, action

    def test_an_oom_group_keeps_its_own_action(self) -> None:
        ids = [str(400 + i) for i in range(8)]
        action = _finding(_jobs(ids, ["OUT_OF_MEMORY"] * 8)).action
        assert "memory finding" in action, action

    def test_array_siblings_still_count_as_evidence(self) -> None:
        # The invariant the earlier round pinned deliberately: an array's tasks are
        # allocations that ran, so they are counted, not exempted.
        evidence = _finding(_jobs(*ONE_ARRAY)).evidence
        assert " of 8 runs" in evidence, evidence

    def test_a_group_of_one_master_but_one_member_is_not_called_an_array(self) -> None:
        # A single task is not fan-out; nothing should claim it is.
        ids = ["55_1"] + [str(500 + i) for i in range(7)]
        evidence = _finding(_jobs(ids, ["FAILED"] * 8)).evidence
        assert "one array" not in evidence, evidence
