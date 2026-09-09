"""The second `sacct` query is skipped when no target job has an allocation.

`cli._node_history` widens the population a node note is computed from, because on
the `-j` branch `_load` returns only the record asked for and no node can reach
`nodes.MIN_SAMPLES` in a history of one. On that branch the widening IS a second
`sacct` query, and the docstring prices it and promises the guard:

    Cost, measured rather than assumed (90-day history, 50,604 sacct rows):
    `sacct` for the default `now-7days` window is 0.26 s against the 0.20 s the id
    query already costs, and `-S now-30days` is 9.3 s for 13,075 rows [...] So it
    is loaded lazily and once: nothing is queried unless some target job actually
    has an allocation to say something about.

`TestWhetherTheNodeNoteExistsAtAll` covers the widening thoroughly, but every one of
its four cases has an allocation, so none of them can see the guard. Delete
`if not any(expand_nodelist(job.node_list) for job in targets): return None` and all
four still pass -- they simply get a population they already wanted -- while every
`slurmpast <id>` silently pays a second query it can do nothing with. Verified by
neuter, not assumed.

A job with no allocation is ordinary: cancelled or rejected before it ever started,
where Slurm reports `NodeList=None assigned`.
"""

from slurmpast.sacct import _FIELDS, SAFE_DELIMITER


def _row(**kw):
    """One sacct line. Mirrors `test_audit.row`, kept local so this file stands alone."""
    values = {name: kw.get(name, "") for name in _FIELDS}
    return "|".join(str(values[name]) for name in _FIELDS)


def _placements(node, bad, total, job_id_base=1000):
    return [
        _row(
            JobID=str(job_id_base + i),
            JobName="node-evaluation",
            User="youzhi",
            Partition="test",
            State="FAILED" if i < bad else "COMPLETED",
            ExitCode="9:0" if i < bad else "0:0",
            Submit="2026-01-01T00:00:00",
            Start="2026-01-01T00:00:00",
            End="2026-01-01T00:10:00",
            Elapsed="00:10:00",
            Timelimit="01:00:00",
            ReqMem="40Gn",
            ReqCPUS="8",
            AllocTRES="billing=8,cpu=8,mem=40G,node=1",
            NodeList=node,
        )
        for i in range(total)
    ]


#: A job that never started: Slurm's own spelling for "no nodes were assigned".
NEVER_RAN = _row(
    JobID="9001",
    JobName="node-evaluation",
    User="youzhi",
    Partition="test",
    State="CANCELLED",
    ExitCode="0:0",
    Submit="2026-01-01T00:00:00",
    Start="None",
    End="2026-01-01T00:00:05",
    Elapsed="00:00:00",
    Timelimit="01:00:00",
    ReqMem="40Gn",
    ReqCPUS="8",
    AllocTRES="",
    NodeList="None assigned",
)
#: Two nodes, because the note is a COMPARISON -- "against 0.0% on every other
#: node". A single-node fleet yields no note at all, which cost a first draft of
#: this file its control.
FLEET = (
    _placements("midway3-0600", 0, 40, job_id_base=1000)
    + _placements("midway3-0607", 30, 40, job_id_base=5000)
    + [NEVER_RAN]
)
ALLOCATED_JOB = "5000"
UNALLOCATED_JOB = "9001"


def _run_counting(job_id, counter):
    """A fake Slurm that answers `-j` with one row and counts WINDOW queries."""

    def encode(rows):
        return "\n".join(rows).replace("|", SAFE_DELIMITER)

    one = encode([r for r in FLEET if r.split("|")[0] == job_id])
    window = encode(FLEET)

    def run(args):
        if "--helpformat" in args:
            return " ".join(_FIELDS)
        if args and args[0] in ("squeue", "scontrol", "sstat"):
            return ""
        if "-j" in args:
            return one
        counter.append(tuple(args))
        return window

    return run


def _plain(monkeypatch, capsys, job_id):
    from slurmpast import cli

    calls: list[tuple] = []
    monkeypatch.setattr("slurmpast.sacct._run", _run_counting(job_id, calls))
    code = cli.main([job_id, "--plain", "--no-color", "--no-logs"])
    return code, capsys.readouterr().out, calls


class TestTheWideningQueryIsNotPaidForNothing:
    def test_a_job_that_never_ran_costs_no_window_query(self, monkeypatch, capsys) -> None:
        _code, out, calls = _plain(monkeypatch, capsys, UNALLOCATED_JOB)
        assert calls == [], calls
        # And it still produced a post-mortem -- the guard skips a query, not the report.
        assert UNALLOCATED_JOB in out, out

    def test_the_note_is_absent_there_because_there_is_no_node_to_judge(
        self, monkeypatch, capsys
    ) -> None:
        _code, out, _calls = _plain(monkeypatch, capsys, UNALLOCATED_JOB)
        assert "placements there" not in out, out


class TestControls:
    """Unaffected by the guard: an allocated job takes the widening either way."""

    def test_an_allocated_job_does_pay_the_window_query(self, monkeypatch, capsys) -> None:
        _code, _out, calls = _plain(monkeypatch, capsys, ALLOCATED_JOB)
        assert len(calls) == 1, calls

    def test_and_gets_the_note_the_widening_exists_for(self, monkeypatch, capsys) -> None:
        _code, out, _calls = _plain(monkeypatch, capsys, ALLOCATED_JOB)
        flat = " ".join(out.split())
        assert "failed 30 of 40 placements" in flat, flat

    def test_the_fixture_really_holds_both_shapes(self) -> None:
        # If both jobs had allocations, the first class would pass vacuously.
        from slurmpast.nodes import expand_nodelist
        from slurmpast.sacct import parse

        # `parse` reads raw `|`; only the fake runner's OUTPUT carries
        # SAFE_DELIMITER, because that is what real sacct is invoked with.
        jobs = {j.job_id: j for j in parse("\n".join(FLEET))}
        assert expand_nodelist(jobs[ALLOCATED_JOB].node_list) == ["midway3-0607"]
        assert expand_nodelist(jobs[UNALLOCATED_JOB].node_list) == []
