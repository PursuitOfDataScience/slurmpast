"""Findings from a full-codebase audit, each pinned so it cannot come back.

These are not hypotheticals. Every case below was found by probing the built
package rather than by reading it, and several were quietly wrong in shipped
output.
"""

import ast
import pathlib
import re

import pytest

from slurmpast.demo import history
from slurmpast.index import build_groups
from slurmpast.report import Style, render_overview
from slurmpast.sacct import _FIELDS, parse

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "slurmpast"


def row(**kw):
    return "|".join(str(kw.get(name, "")) for name in _FIELDS)


class TestFailureCountAgreesWithRuns:
    """The table paired `RUNS 20` with `FAILED 20.0%`.

    The rate's denominator excludes cancellations (they are ambiguous) while RUNS
    counts everything, so a reader multiplying the two computed four failures
    where there were two. The column now shows a count.
    """

    def _group(self):
        rows = []
        for index in range(8):
            rows += self._job(100 + index, "COMPLETED")
        for index in range(2):
            rows += self._job(200 + index, "FAILED", ExitCode="1:0")
        for index in range(10):
            rows += self._job(300 + index, "CANCELLED by 1")
        return build_groups(parse("\n".join(rows)))[0]

    def _job(self, jid, state, **kw):
        fields = {
            "JobID": str(jid),
            "JobName": "w",
            "State": state,
            "ElapsedRaw": "600",
            "End": "2026-01-01T00:10:00",
            "TimelimitRaw": "60",
            "AllocTRES": "cpu=8,mem=64G,node=1",
            "AllocCPUS": "8",
        }
        fields.update(kw)
        return [
            row(**fields),
            row(
                JobID="%s.batch" % jid,
                JobName="batch",
                State=state.split()[0],
                ElapsedRaw="600",
                CPUTimeRAW="4800",
                TotalCPU="00:40:00",
                MaxRSS="1000000K",
            ),
        ]

    def test_rate_still_excludes_cancellations(self):
        group = self._group()
        assert group.failure_rate == pytest.approx(2 / 10)

    def test_problems_is_a_union_not_a_sum(self):
        """A hung TIMEOUT is both failed and never-ran. Summing the two columns
        reported 36 problems out of 20 runs on a real workload, which is what made
        showing them side by side a trap."""
        from slurmpast.demo import history as demo
        from slurmpast.index import History

        group = [g for g in History(demo()).groups if g.name == "cot-exp"][0]
        # 14 of the demo's 20 cot-exp runs hang now, not 18: the hang was
        # redistributed onto midway3-0385 so the demo actually contains the bad
        # node it advertises. The invariant under test is the overlap, not the
        # count, so it is asserted as one rather than as three literals.
        assert group.failed == group.noop, (group.failed, group.noop)
        assert group.problems == group.failed  # NOT failed + noop
        assert group.problems < group.failed + group.noop
        assert group.problems <= group.total

    def test_problems_excludes_deliberate_cancellations(self):
        """ "total minus completed" is the obvious single number and it is wrong:
        it brands every run you stopped on purpose. This workload has 10 runs, 1
        completed, 8 failed and 1 cancelled -- 8 problems, not 9."""
        from slurmpast.demo import history as demo
        from slurmpast.index import History

        group = [g for g in History(demo()).groups if g.name == "rc-tok-github_code"][0]
        assert (group.total, group.completed, group.cancelled) == (10, 1, 1)
        assert group.problems == 8
        assert group.problems < group.total - group.completed

    def test_a_clean_workload_reports_no_problems(self):
        from slurmpast.demo import history as demo
        from slurmpast.index import History

        group = [g for g in History(demo()).groups if g.name == "midtrain"][0]
        assert group.completed == group.total
        assert group.problems == 0

    def test_a_cancelled_hang_still_counts(self):
        """Cancelled is not a free pass: a run that held GPUs for two days and
        computed nothing is a problem however it ended."""
        from slurmpast.demo import history as demo
        from slurmpast.index import History

        group = [g for g in History(demo()).groups if g.name == "node-evaluation"][0]
        assert group.cancelled == 1
        assert group.failed == 0
        assert group.problems == 1

    def test_table_shows_a_count_not_that_rate(self):
        group = self._group()
        assert group.failed == 2

    def test_plain_overview_prints_the_count(self):
        from slurmpast.index import History

        text = render_overview(
            History(
                parse(
                    "\n".join(
                        sum((self._job(400 + i, "FAILED", ExitCode="1:0") for i in range(3)), [])
                    )
                )
            ),
            style=Style(enabled=False),
        )
        header = [ln for ln in text.splitlines() if "JOB NAME" in ln][0]
        body = [ln for ln in text.splitlines() if ln.strip().startswith("1 ")][0]
        # One outcome column now: FAILED and NEVER RAN overlapped, so two adjacent
        # integers invited adding them into more problems than there were runs.
        assert "FLAGGED" in header
        assert "FAILED" not in header and "NEVER RAN" not in header
        # Still a count, not a rate -- no percentage anywhere in the data row.
        assert "%" not in body


class TestNoDeadCode:
    """Three render helpers survived past the redesigns that orphaned them."""

    def _module_names(self):
        names = {}
        for path in sorted(SRC.glob("*.py")):
            for node in ast.parse(path.read_text()).body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    names[node.name] = path.name
        return names

    def test_no_unreferenced_module_level_definitions(self):
        text = "\n".join(p.read_text() for p in SRC.glob("*.py"))
        # conftest.py counts: a helper the fixtures use is referenced, and leaving
        # it out of this sweep reported a live function as dead code.
        tests = SRC.parent.parent / "tests"
        text += "\n".join(
            p.read_text() for p in list(tests.glob("test_*.py")) + [tests / "conftest.py"]
        )
        orphans = [
            "%s (%s)" % (name, where)
            for name, where in self._module_names().items()
            if not name.startswith("_") and len(re.findall(r"\b%s\b" % re.escape(name), text)) <= 1
        ]
        assert not orphans, "unreferenced: %s" % ", ".join(orphans)

    def test_every_captured_field_is_exposed_somewhere(self):
        """A field extracted but never surfaced is dead weight -- the whole point
        of the wide query was that nobody re-runs sacct for a missing number."""
        text = "\n".join(p.read_text() for p in SRC.glob("*.py"))
        tree = ast.parse((SRC / "model.py").read_text())
        orphans = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in ("Step", "Job"):
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        name = item.target.id
                        # declaration + the sacct assignment == never read
                        if len(re.findall(r"\b%s\b" % re.escape(name), text)) <= 2:
                            orphans.append("%s.%s" % (node.name, name))
        assert not orphans, "captured but never surfaced: %s" % ", ".join(orphans)


class TestEdgeCasesDoNotCrashOrLie:
    def test_empty_history_renders(self):
        from slurmpast.index import History

        h = History([])
        assert h.groups == []
        assert h.span_hours is None
        assert h.gpu_concurrency is None
        assert render_overview(h, style=Style(enabled=False))

    def test_zero_elapsed_job_yields_none_not_zero(self):
        job = parse(
            "\n".join(
                [
                    row(
                        JobID="4",
                        JobName="w",
                        State="COMPLETED",
                        ElapsedRaw="0",
                        TimelimitRaw="0",
                        End="2026-01-01T00:00:00",
                        AllocTRES="cpu=4,mem=8G,node=1",
                        AllocCPUS="4",
                    ),
                    row(
                        JobID="4.batch",
                        JobName="batch",
                        State="COMPLETED",
                        ElapsedRaw="0",
                        TotalCPU="00:00:00",
                        CPUTimeRAW="0",
                        MaxRSS="1000K",
                    ),
                ]
            )
        )[0]
        assert job.walltime_used is None
        assert job.cpu_utilization is None
        assert job.io_rate is None

    def test_job_with_no_batch_step_still_measured(self):
        """Work launched by srun lands in a numbered step, not `.batch`."""
        job = parse(
            "\n".join(
                [
                    row(
                        JobID="500",
                        JobName="w",
                        State="COMPLETED",
                        ElapsedRaw="600",
                        End="2026-01-01T00:10:00",
                        AllocTRES="cpu=8,mem=64G,node=1",
                        AllocCPUS="8",
                    ),
                    row(
                        JobID="500.0",
                        JobName="srun",
                        State="COMPLETED",
                        ElapsedRaw="600",
                        TotalCPU="00:40:00",
                        CPUTimeRAW="4800",
                        MaxRSS="900000K",
                    ),
                ]
            )
        )[0]
        assert job.total_cpu == 2400.0
        assert job.cpu_utilization == pytest.approx(0.5)

    def test_job_with_no_steps_at_all(self):
        from slurmpast.diagnose import diagnose
        from slurmpast.render import job_sections, resource_rows

        job = parse(
            row(
                JobID="9",
                JobName="w",
                State="FAILED",
                ExitCode="1:0",
                ElapsedRaw="600",
                End="2026-01-01T00:10:00",
            )
        )[0]
        assert diagnose(job).findings
        assert resource_rows(job)
        assert job_sections(job)

    def test_missing_timestamps_render_as_a_dash(self):
        from slurmpast.report import render_list

        job = parse(row(JobID="2", JobName="w", State="COMPLETED", ElapsedRaw="60"))[0]
        text = render_list([job], style=Style(enabled=False))
        assert " - " in text or text.rstrip().endswith("-")


class TestNodelistWithSuffix:
    """Some site naming puts a suffix after the bracket; the whole string used to
    be treated as one node name."""

    def test_suffix_after_the_range_expands(self):
        from slurmpast.nodes import expand_nodelist

        assert expand_nodelist("node[1-2]-ib") == ["node1-ib", "node2-ib"]

    def test_plain_ranges_unaffected(self):
        from slurmpast.nodes import expand_nodelist

        assert expand_nodelist("midway3-[0600-0602]") == [
            "midway3-0600",
            "midway3-0601",
            "midway3-0602",
        ]


class TestWindowKeywords:
    @pytest.mark.parametrize(
        "spec,expected",
        [("today", "today"), ("midnight", "since midnight"), ("noon", "since noon")],
    )
    def test_bare_keywords_read_naturally(self, spec, expected):
        """sacct accepts these; "since today" read worse than "today"."""
        from slurmpast.duration import humanize_window

        assert humanize_window(spec) == expected


class TestHourColumnsFit:
    def _rows_and_header(self, jobs):
        """Data rows only -- taken from below the header line.

        A bare "starts with a number" match also catches the summary line above
        the table ("  58 jobs · ..."), which silently made this assert nothing.
        """
        from slurmpast.index import History

        lines = render_overview(History(jobs), style=Style(enabled=False)).splitlines()
        at = next(i for i, ln in enumerate(lines) if "JOB NAME" in ln)
        rows = [ln for ln in lines[at + 1 :] if re.match(r"^  \d", ln)]
        assert rows, "expected data rows in the fixture"
        return lines[at], rows

    def test_wide_core_hour_values_do_not_bleed(self):
        """A five-figure core-hour total overran a narrower column, shifting
        every column to its right."""
        cpu_heavy = [
            j._replace(alloc_tres="billing=90,cpu=90,mem=50G,node=1", req_tres="")
            for j in history()
        ]
        header, rows = self._rows_and_header(cpu_heavy)
        # The date is the last column. If an hour value overran its field, the
        # date would no longer begin where the header says the column begins.
        at = header.index("LAST RUN")
        for line in rows:
            assert re.match(r"\d{4}-\d{2}-\d{2}", line[at : at + 10]), (line[at:], line)

    def test_the_header_carries_the_unit_and_the_cells_do_not_abbreviate(self):
        """ "497 gpu-h" made a reader ask what "gpu-h" was. The header names both
        units once and the cells are plain numbers."""
        from slurmpast.render import HOURS_PAIR_LABEL

        header, rows = self._rows_and_header(history())
        assert HOURS_PAIR_LABEL in header
        for line in rows:
            for abbreviation in ("gpu-h ", "core-h ", "GPU-h "):
                assert abbreviation not in line, line

    def test_cpu_comes_before_gpu_in_the_paired_cell(self):
        """Every job consumes CPU; only some hold a GPU, so CPU leads. The order
        is what makes the cell readable with no colour at all."""
        from slurmpast.render import HOURS_PAIR_LABEL

        assert HOURS_PAIR_LABEL.index("CPU") < HOURS_PAIR_LABEL.index("GPU")
        header, rows = self._rows_and_header(history())
        assert HOURS_PAIR_LABEL in header
        for line in rows:
            assert "/" in line, line

    def test_the_pair_is_readable_without_colour(self):
        """Colour reinforces which side is which but is never the only signal --
        this output gets piped, and --no-color exists."""
        from slurmpast.index import History
        from slurmpast.render import hours_pair_text

        for group in History(history()).groups:
            cell = hours_pair_text(group)
            cpu, _, gpu = cell.partition("/")
            assert cpu.strip(), cell
            assert gpu.strip(), cell

    def test_a_gpu_workload_has_cpu_hours_too(self):
        """A GPU job burns CPU-hours as well; the single merged column hid them.

        Asserted on the rolled-up data and the formatted cell rather than by
        slicing the rendered row: the labels sit inside wider fields, so a label
        offset is not a field offset and any such slice is brittle.
        """
        from slurmpast.index import History
        from slurmpast.render import hours_pair_text

        with_gpu = [g for g in History(history()).groups if g.gpu_hours]
        assert with_gpu, "expected GPU workloads in the fixture"
        for group in with_gpu:
            assert group.core_hours > 0, group.name
            cpu, _, gpu = hours_pair_text(group).partition("/")
            assert cpu.strip() != "-", group.name
            assert gpu.strip() != "-", group.name
