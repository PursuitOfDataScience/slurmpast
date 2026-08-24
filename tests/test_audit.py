"""Findings from a full-codebase audit, each pinned so it cannot come back.

These are not hypotheticals. Every case below was found by probing the built
package rather than by reading it, and several were quietly wrong in shipped
output.
"""

import ast
import pathlib
import re
import shutil
import tarfile

import pytest

from slurmpast.demo import history
from slurmpast.index import build_groups
from slurmpast.report import Style, render_overview
from slurmpast.sacct import _FIELDS, parse

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "slurmpast"


def row(**kw):
    return "|".join(str(kw.get(name, "")) for name in _FIELDS)


def _screen_text(jobs, keys, size=(100, 60)):
    """What the dashboard actually paints, as plain lines.

    The cross-surface checks in this file compare a rendered screen against a
    rendered ``--plain``, because comparing two source literals is what missed the
    drift they exist to catch -- a fragment can agree in the source and still be
    assembled differently on the two sides. Driven through Textual's own harness,
    so this is the compositor's output rather than a reconstruction of it.
    """
    import asyncio

    pytest.importorskip("textual")
    from slurmpast import tui

    async def run():
        app = tui.SlurmpastApp(lambda: list(jobs), window="test", no_logs=True)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            for key in keys:
                await pilot.press(key)
                await pilot.pause()
            await pilot.pause()
            return "\n".join(
                "".join(segment.text for segment in strip).rstrip()
                for strip in app.screen._compositor.render_strips()
            )

    return asyncio.run(run())


def _patterns_screen_text(jobs):
    return _screen_text(jobs, ["p"])


def _nodes_screen_text(jobs):
    return _screen_text(jobs, ["n"])


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

    def test_every_captured_field_is_read_somewhere(self):
        """A field extracted and then never mentioned again is dead weight.

        A weak check, and it is labelled as one: it counts name mentions across
        the package, so it catches a field nothing reads at all and nothing more.
        `test_every_measurement_reaches_the_json_payload` below is the one that
        actually holds `--json` to its promise -- see the note there.
        """
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
        assert not orphans, "captured but never referenced: %s" % ", ".join(orphans)


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


def _uniform_placements(nodes=("node-a", "node-b", "node-c"), each=20, bad=4):
    """A fleet where every node fails at the same rate, so none is worse."""
    from slurmpast.model import Job

    jobs = []
    for node in nodes:
        for index in range(each):
            jobs.append(
                Job(
                    job_id="%d" % (len(jobs) + 1),
                    name="w",
                    partition="test",
                    user="me",
                    node_list=node,
                    elapsed=600.0,
                    timelimit=3600.0,
                    state="FAILED" if index < bad else "COMPLETED",
                )
            )
    return jobs


class TestTheTwoSurfacesCannotDriftApart:
    """`render.py` exists so the dashboard and `--plain` draw the same sentence.

    It only works for the sentences that were actually moved there, and seven were
    not -- so each front end carried its own copy of the wording and one pair had
    already come apart: `--plain` ended the exclude disclaimer at "trades
    availability for reliability." while the dashboard went on ", and that is your
    call.". One sentence, one block of one view, two texts, and nothing on either
    screen from which a reader could tell.

    A literal is the unit here rather than a rendered screen: the drift happened in
    the source, and by the time it reaches a screen only one of the two is on it.
    """

    @staticmethod
    def _prose_literals(path):
        """Every prose-shaped string constant in ``path`` that is not a docstring."""
        tree = ast.parse(path.read_text())
        docstrings = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and ast.get_docstring(node, clean=False) is not None
                and node.body
            ):
                docstrings.add(node.body[0].lineno)
        found = {}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if node.lineno in docstrings:
                continue
            value = node.value.strip()
            # Prose, not a format fragment or an identifier: several words, and
            # long enough that two files sharing it is a copy rather than a
            # coincidence.
            if len(value) >= 25 and " " in value and "\n" not in value:
                found.setdefault(value, []).append(node.lineno)
        return found

    def test_no_sentence_is_written_out_in_both_front_ends(self):
        report = self._prose_literals(SRC / "report.py")
        dashboard = self._prose_literals(SRC / "tui.py")
        shared = sorted(set(report) & set(dashboard))
        assert not shared, "duplicated between report.py and tui.py: %s" % "; ".join(
            "%r (report.py:%s, tui.py:%s)" % (s[:60], report[s], dashboard[s]) for s in shared
        )

    def test_the_disclaimer_that_drifted_is_now_one_string(self):
        """The control for the sweep above, naming the pair that came apart."""
        from slurmpast.render import nodes_exclude_disclaimer

        sentence = nodes_exclude_disclaimer()
        assert sentence.endswith("trades availability for reliability.")
        assert "that is your call" not in sentence
        for name in ("report.py", "tui.py"):
            assert "nodes_exclude_disclaimer" in (SRC / name).read_text()

    def test_the_plain_renderer_emits_the_shared_sentences_verbatim(self):
        """End to end, not merely at the source: what reaches the screen is the
        shared string, so a change to it moves both surfaces at once."""
        from slurmpast.index import History
        from slurmpast.render import (
            nodes_correction_note,
            nodes_exclude_disclaimer,
            nodes_nothing_to_exclude,
            nodes_workload_control,
            patterns_empty,
        )
        from slurmpast.report import Style, render_nodes, render_patterns

        # The demo's hang metric singles out one node, so the exclude branch runs.
        flagged = render_nodes(History(history()), metric="hang", style=Style(enabled=False))
        assert nodes_exclude_disclaimer() in flagged
        assert nodes_correction_note(1) in flagged
        assert nodes_workload_control("cot-exp") in flagged

        # A fleet where every node behaves alike takes the other branch.
        even = _uniform_placements()
        clean = render_nodes(History(even), metric="failure", style=Style(enabled=False))
        assert nodes_nothing_to_exclude() in clean

        assert patterns_empty() in render_patterns(History([]), style=Style(enabled=False))


class TestTheHelpExamplesLineUp:
    """One example's description started a column left of the other eight.

    `RawDescriptionHelpFormatter` prints the epilog verbatim, so the alignment is
    whatever the literal says -- and `-S now-30days` was one space short, which is
    invisible in the source and plain on screen.
    """

    def test_every_example_description_starts_at_one_column(self):
        from slurmpast.cli import EPILOG

        columns = set()
        for line in EPILOG.splitlines():
            if not line.startswith("  slurmpast"):
                continue
            gap = re.search(r"  +", line[2:])
            assert gap, "no separator in %r" % line
            columns.add(2 + gap.end())
        assert len(columns) == 1, "descriptions start at columns %s" % sorted(columns)


class TestTheStdOutBoundaryIsOneNumber:
    """`StdOut`/`StdErr` arrived in Slurm 24.05, not 21.08.

    `logs.py` says so at length and names the confusion explicitly -- "21.08 is the
    release that added SubmitLine ... not these fields" -- and three other places
    said 21.08 anyway. The claim is load-bearing rather than decorative: the whole
    point of that table is telling a reader what works on the Slurm they have, and
    21.08 through 23.11 is five releases told they have a field they do not.
    """

    @staticmethod
    def _comment_above(path, anchor):
        """The run of ``#`` lines immediately above the line holding ``anchor``.

        Anchored on the code rather than grepped for a version string: ``21.08``
        is the *right* answer three lines away in the same files, for
        ``SubmitLine``, so a sweep over the bare number cannot tell a copy of the
        wrong boundary from a correct statement of the other one.
        """
        lines = (SRC / path).read_text().splitlines()
        index = next(i for i, line in enumerate(lines) if anchor in line)
        block = []
        cursor = index - 1
        while cursor >= 0 and lines[cursor].strip().startswith("#"):
            block.append(lines[cursor].strip().lstrip("# "))
            cursor -= 1
        return " ".join(reversed(block))

    def test_the_model_field_names_the_release_that_added_it(self):
        note = self._comment_above("model.py", 'std_out: str = ""')
        assert "24.05" in note, note
        assert "present from Slurm 21.08" not in note

    def test_the_json_payload_comment_names_it_too(self):
        note = self._comment_above("cli.py", '"stdout_pattern"')
        assert "24.05" in note, note
        assert "Recorded from Slurm 21.08" not in note

    def test_the_submit_line_row_keeps_its_own_boundary(self):
        """The control. ``SubmitLine`` really did arrive in 21.08, and a fix that
        rewrote every 21.08 in the tree would have broken this one."""
        note = self._comment_above("render.py", '("submitted as", job.submit_line, None)')
        assert "21.08" in note, note

    def test_the_two_places_that_had_it_right_still_do(self):
        assert "**StdOut/StdErr, from Slurm 24.05.**" in (SRC / "logs.py").read_text()
        assert "StdOut/StdErr only from 24.05" in (SRC / "sacct.py").read_text()

    def test_the_documentation_table_agrees_with_the_code(self):
        docs = (SRC.parent.parent / "docs" / "details.md").read_text()
        assert "**`StdOut`/`StdErr`** exist from Slurm 24.05" in docs
        assert "**`StdOut`/`StdErr`** exist from Slurm 21.08" not in docs


class TestTheReadmeMatchesTheDependencyPin:
    """The floor CI actually installs, not one three releases above it."""

    def test_the_textual_range_is_the_pinned_one(self):
        root = SRC.parent.parent
        pin = re.search(r'"textual>=([\d.]+),<(\d+)"', (root / "pyproject.toml").read_text())
        assert pin, "textual pin not found in pyproject.toml"
        readme = (root / "README.md").read_text()
        assert "Textual %s–" % pin.group(1) in readme, (
            "README's Textual floor disagrees with pyproject's %s" % pin.group(1)
        )
        oldest = (root / ".github" / "workflows" / "ci.yml").read_text()
        assert "textual==%s.*" % pin.group(1) in oldest, (
            "the oldest-textual CI job does not install the pinned floor"
        )


class TestTheDemoClockAgreesWithItself:
    """`End` was a flat `23:59:00` on the job's own day, whatever the job did.

    So all 58 synthetic jobs carried an End their own `ElapsedRaw` contradicts, and
    on the job screen the two sat two rows apart:

        started  2026-07-19T03:54:00        ended  2026-07-19T23:59:00
        TIME  101.4%  ·  00:30:26 of the 00:30:00 limit

    Twenty hours against thirty minutes, in the demo whose stated purpose is that
    "nobody should be able to mistake a demo screenshot for a measurement" -- and
    the same wrong timestamp is baked into `assets/screenshot-job.svg`, which the
    README displays. Round five caught the sibling of this ("a number the demo only
    produced because its clock ran backwards") in `_time_of_day`; the End field was
    never looked at, and the whole suite passed with every record inconsistent.
    """

    @staticmethod
    def _parsed(job):
        from datetime import datetime

        return datetime.fromisoformat(job.start), datetime.fromisoformat(job.end)

    def test_end_is_start_plus_elapsed_on_every_record(self):
        wrong = []
        for job in history():
            assert job.start and job.end and job.elapsed is not None, job.job_id
            start, end = self._parsed(job)
            span = (end - start).total_seconds()
            if abs(span - job.elapsed) > 1.0:
                wrong.append((job.job_id, job.elapsed, span))
        assert not wrong, "elapsed disagrees with end-start on %d records: %s" % (
            len(wrong),
            wrong[:4],
        )

    def test_submit_is_before_start_by_the_queue_wait_it_reports(self):
        """`Reserved` says one second and the two timestamps said zero, so the job
        screen printed "submitted 03:54:00, started 03:54:00, queued for 1.0s"."""
        from datetime import datetime

        from slurmpast.demo import _QUEUE_WAIT_SECONDS

        for job in history():
            submit = datetime.fromisoformat(job.submit)
            start = datetime.fromisoformat(job.start)
            assert (start - submit).total_seconds() == _QUEUE_WAIT_SECONDS, job.job_id
            assert job.queue_wait == _QUEUE_WAIT_SECONDS, job.job_id

    def test_a_long_run_is_allowed_to_cross_midnight(self):
        """The control against a fix that just clamped everything into one day: the
        42-hour allocation has to end two days after it started."""
        longest = max(history(), key=lambda j: j.elapsed or 0)
        start, end = self._parsed(longest)
        assert longest.elapsed > 24 * 3600, "the fixture should hold a multi-day run"
        assert end.date() > start.date()

    def test_no_record_ends_before_it_starts(self):
        for job in history():
            start, end = self._parsed(job)
            assert end >= start, job.job_id


class TestOneBadRecordCannotPoisonTheRest:
    """A NaN does not stay in the record it came from.

    `Elapsed` that does not parse as a finite duration used to reach `Job.elapsed`
    as `nan`, and from there into `gpu_hours`, `core_hours` and the summed history
    totals -- so a single unreadable record turned every other job's figure into
    `nan`, and the job screen raised `ValueError` out of `format_duration`. Both
    are the opposite of what this codebase promises: "prints n/a rather than 0 for
    anything it cannot read", and "a one-line explanation and exit 2, never a
    traceback".
    """

    COMMON = {
        "JobName": "train",
        "Partition": "test",
        "User": "me",
        "State": "COMPLETED",
        "ExitCode": "0:0",
        "Start": "2026-07-01T00:00:00",
        "End": "2026-07-01T01:00:00",
        "Timelimit": "02:00:00",
        "AllocTRES": "cpu=8,mem=16G,gres/gpu=4,node=1",
        "NodeList": "n1",
        "ReqCPUS": "8",
    }

    def _history(self, *elapsed):
        from slurmpast.index import History

        text = "\n".join(
            row(JobID=str(i + 1), Elapsed=value, **self.COMMON) for i, value in enumerate(elapsed)
        )
        return History(parse(text))

    def test_the_healthy_totals_survive_an_unreadable_neighbour(self):
        clean = self._history("01:00:00")
        poisoned = self._history("01:00:00", "NaN")
        assert clean.stats["gpu_hours_total"] == 4.0
        assert poisoned.stats["gpu_hours_total"] == clean.stats["gpu_hours_total"]
        assert poisoned.stats["core_hours_total"] == clean.stats["core_hours_total"]

    def test_the_unreadable_record_reports_no_elapsed_rather_than_a_number(self):
        jobs = self._history("01:00:00", "NaN").jobs
        assert jobs[0].elapsed == 3600.0
        assert jobs[1].elapsed is None
        assert jobs[1].gpu_hours is None

    @pytest.mark.parametrize("elapsed", ["NaN", "inf", "1e999"])
    def test_the_job_screen_renders_instead_of_raising(self, elapsed):
        from slurmpast.report import Style, render_job

        job = self._history(elapsed).jobs[0]
        text, _verdict = render_job(job, style=Style(enabled=False))
        assert "n/a" in text

    def test_a_counted_field_that_overflows_does_not_kill_the_query(self):
        """`int(float("inf"))` raises OverflowError, which `except ValueError` in
        `sacct._int` did not catch, so the whole parse died on one bad column."""
        jobs = parse(row(JobID="1", Elapsed="01:00:00", Priority="1e999", **self.COMMON))
        assert len(jobs) == 1
        assert jobs[0].priority is None

    def test_a_finite_history_is_unchanged(self):
        """The control: the guards reject nothing a real record carries."""
        from slurmpast.index import History

        before = History(history())
        assert before.stats["gpu_hours_total"] > 0
        assert all(j.elapsed is not None for j in before.jobs)


class TestTheFragmentsBothSurfacesDrawComeFromOnePlace:
    """The sweep above has a floor: it calls a literal prose at 25 characters.

    Everything shorter is invisible to it, and that is where round fourteen's
    drift was. Three pieces of the same block were written out in both front ends
    and two had already come apart:

        the action arrow       report.py "-> "                tui.py "→ "
        the 95% CI cell        report.py "%.1f - %.1f%%"      tui.py "%.1f – %.1f%%"
        the severity tag       report.py {"critical": ("red", "FAIL"), ...}
                               render.py {"critical": "FAIL", ...}

    The arrow is the costly one, because it also silenced a flag. `ascii_fold`
    turns Unicode punctuation into an ASCII stand-in and `--ascii` exists to ask
    for that; the plain renderer had already hardcoded the ASCII form, so the flag
    had nothing to fold and the surface that CAN be piped somewhere with an
    opinion about encoding was the one whose arrow the flag could not reach.
    """

    @staticmethod
    def _source(name):
        return (SRC / name).read_text()

    @staticmethod
    def _literals(name):
        """Every string a module actually builds output from.

        Docstrings excluded: three of these fragments are quoted in the comment
        explaining why they were centralised, and a check that cannot tell the
        code from the note about the code fails on its own fix.
        """
        tree = ast.parse((SRC / name).read_text())
        skip = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.body
                and ast.get_docstring(node, clean=False) is not None
            ):
                skip.add(id(node.body[0].value))
        return [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in skip
        ]

    def test_the_action_arrow_is_declared_once(self):
        from slurmpast import render

        assert render.ACTION_ARROW == "→ "
        # Two cells, so `ascii_fold`'s one-cell-for-one-cell rule holds and the
        # hang under it stays square.
        assert len(render.ACTION_ARROW) == len(render.ACTION_HANG) == 2
        for name in ("report.py", "tui.py"):
            spelled = [v for v in self._literals(name) if v in ("-> ", "→ ")]
            assert not spelled, "%s still spells the arrow itself: %r" % (name, spelled)
            assert "ACTION_ARROW" in self._source(name), name

    def test_both_surfaces_draw_the_same_arrow(self):
        """End to end. Only one of the two is ever on screen, which is why this
        had to be checked from outside them."""
        from slurmpast.index import History
        from slurmpast.render import ACTION_ARROW
        from slurmpast.report import Style, render_patterns

        jobs = history()
        plain = render_patterns(History(jobs), style=Style(enabled=False))
        assert ("        %s" % ACTION_ARROW) in plain

        dashboard = _patterns_screen_text(jobs)
        assert ("        %s" % ACTION_ARROW) in dashboard

    def test_ascii_can_reach_the_arrow_now(self):
        """The control: `--ascii` folds it, and folding is what the flag is for.

        The old plain arrow was already ASCII, so `--ascii --patterns` and
        `--patterns` were byte-identical on this line -- a flag accepted and, on
        the one glyph it was pointed at, discarded.
        """
        from slurmpast.index import History
        from slurmpast.report import Style, render_patterns

        jobs = History(history())
        unicode_form = render_patterns(jobs, style=Style(enabled=False))
        folded = render_patterns(jobs, style=Style(enabled=False), ascii_mode=True)
        assert "        → " in unicode_form
        assert "        → " not in folded
        assert "        > " in folded
        assert folded.isascii()

    def test_the_ci_cell_is_declared_once(self):
        from slurmpast import render

        assert render.ci_range(0.757, 1.0) == "75.7 – 100.0%"
        for name in ("report.py", "tui.py"):
            spelled = [v for v in self._literals(name) if v.count("%.1f") >= 2]
            assert not spelled, "%s formats the interval itself: %r" % (name, spelled)
            assert "ci_range" in self._source(name), name

    def test_the_ci_cell_reads_the_same_on_both_surfaces(self):
        from slurmpast.index import History
        from slurmpast.nodes import dominant_workload, node_table
        from slurmpast.report import Style, render_nodes

        jobs = History(history())
        table = node_table(
            jobs.usable_jobs,
            workload=dominant_workload(jobs.usable_jobs, metric="hang"),
            metric="hang",
        )
        assert table["rows"], "the demo needs a scored node for this"
        from slurmpast.render import ci_range

        cell = ci_range(table["rows"][0]["ci_low"], table["rows"][0]["ci_high"])
        assert cell in render_nodes(jobs, metric="hang", style=Style(enabled=False))
        assert cell in _nodes_screen_text(history())

    def test_the_severity_tag_is_declared_once(self):
        from slurmpast import render

        assert render.severity_tag("critical") == "FAIL"
        assert render.severity_tag("warning") == "WARN"
        assert render.severity_tag("info") == "INFO"
        # An unknown severity still has to occupy four cells: the plain renderer
        # hangs a wrapped title by `len(tag) + 2`.
        assert len(render.severity_tag("whatever")) == 4
        assert "FAIL" not in self._literals("report.py")

    def test_the_nodes_heading_is_declared_once(self):
        """ "node reliability (hang rate)" against "node reliability — hang rate":
        the same heading over the same table, in two spellings."""
        from slurmpast.index import History
        from slurmpast.render import nodes_title
        from slurmpast.report import Style, render_nodes

        assert nodes_title("hang") == "node reliability — hang rate"
        assert nodes_title("failure") == "node reliability — failure rate"
        for name in ("report.py", "tui.py"):
            spelled = [v for v in self._literals(name) if "node reliability" in v]
            assert not spelled, "%s writes the heading itself: %r" % (name, spelled)
        plain = render_nodes(History(history()), metric="hang", style=Style(enabled=False))
        assert nodes_title("hang") in plain
        assert nodes_title("hang") in _nodes_screen_text(history())


class TestTheJsonPayloadKeepsItsPromise:
    """`_job_json` says "Deliberately exhaustive: if the tool read it, this emits
    it", and `docs/details.md` says "a test fails if a field is read but never
    surfaced". Neither was true, and the test the doc points at is not that test:
    `test_every_captured_field_is_read_somewhere` counts how many times a name
    appears in `src/slurmpast/*.py`, which a field mentioned three times in an
    internal helper passes without ever reaching a reader.

    `Job.live` is what fell through it. `cli._mark_open_records` asks squeue and
    writes a tri-state answer onto the job; both text surfaces spend it on the
    finding's action sentence; the payload carried only `open_ended_record`, which
    is `true` in all three cases:

        live=True    outcome.open_ended_record = True   "squeue confirms it is ..."
        live=False   outcome.open_ended_record = True   "squeue has never heard ..."
        live=None    outcome.open_ended_record = True   "Confirm against squeue."

    So a consumer of the one machine-readable surface could not tell a job running
    right now from one that died in March -- and `timing.elapsed_seconds` is
    measured to *now* for both, which is the artefact the distinction exists to
    flag.

    This one reads `_job_json` itself and holds every `Job`/`Step` value to it. The
    exemptions are listed by name rather than inferred, so the next value that is
    not emitted has to be argued for here instead of passing quietly.
    """

    # Raw sacct inputs whose *derived* value is what the payload emits, and two
    # deprecated aliases. Each is recoverable from something that is emitted, so
    # emitting it as well would be the same number under two names.
    JOB_EXEMPT = {
        # -> shape.cpus / shape.nodes / shape.tasks, via Job.cpu_count etc, which
        # fall back across these spellings in order.
        "alloc_cpus": "shape.cpus",
        "ncpus": "shape.cpus",
        "alloc_nodes": "shape.nodes",
        "nnodes": "shape.nodes",
        "ntasks": "shape.tasks",
        # -> cpu.total_seconds / user_seconds / system_seconds / allocated_core_
        # seconds: the `*_alloc` spellings are the allocation-row fallback the
        # properties read when no step recorded the figure.
        "total_cpu_alloc": "cpu.total_seconds",
        "user_cpu_alloc": "cpu.user_seconds",
        "system_cpu_alloc": "cpu.system_seconds",
        "cpu_time_alloc": "cpu.allocated_core_seconds",
        # -> memory.limit_bytes, with req_mem_raw beside it for the raw string.
        "req_mem_bytes": "memory.limit_bytes + memory.req_mem_raw",
        # Derived views of emitted numbers.
        "cores_busy": "cpu.utilization x shape.cpus",
        "fs_disk_bytes": "deprecated alias of filesystem.read_bytes",
        # `cpu_freq_hz` was here, justified as "cpu.frequency". It is not
        # recoverable from that string and never was -- see
        # TestTheResolvedClockIsMachineReadable below. An allow-list whose entries
        # are not checked is a way to make a finding pass quietly, which is the
        # one thing this class exists to prevent.
    }
    STEP_EXEMPT = {
        "cpu_time": "elapsed_seconds x the step's cpu count",
        "tres_in_tot": "read_bytes",
        "tres_out_tot": "write_bytes",
    }
    # Containers of values emitted in their own right, and predicates over them.
    STRUCTURAL = {
        "steps",
        "work_steps",
        "batch_step",
        "extern_step",
        "is_batch",
        "is_extern",
        "name",
    }

    @staticmethod
    def _reads():
        """``job.x`` and ``s.x`` attribute reads inside ``cli._job_json``."""
        tree = ast.parse((SRC / "cli.py").read_text())
        fn = next(
            n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_job_json"
        )
        job, step = set(), set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "job":
                    job.add(node.attr)
                elif node.value.id == "s":
                    step.add(node.attr)
        return job, step

    @staticmethod
    def _data_attributes(cls, sample):
        out = set()
        for name in dir(cls):
            if name.startswith("_") or name in ("count", "index"):
                continue
            try:
                value = getattr(sample, name)
            except Exception:
                continue
            if not callable(value):
                out.add(name)
        return out

    def _sample(self):
        return next(j for j in history() if j.steps)

    def test_every_job_value_is_emitted_or_exempt_by_name(self):
        job_reads, _ = self._reads()
        job = self._sample()
        missing = sorted(
            self._data_attributes(type(job), job)
            - job_reads
            - set(self.JOB_EXEMPT)
            - self.STRUCTURAL
        )
        assert not missing, (
            "read by the tool, absent from --json, and not listed as recoverable: %s" % missing
        )

    def test_every_step_value_is_emitted_or_exempt_by_name(self):
        _, step_reads = self._reads()
        step = self._sample().steps[0]
        missing = sorted(
            self._data_attributes(type(step), step)
            - step_reads
            - set(self.STEP_EXEMPT)
            - self.STRUCTURAL
        )
        assert not missing, "absent from --json and not listed as recoverable: %s" % missing

    def test_the_exemptions_are_real_attributes(self):
        """The control. An allow-list that can hold a name nothing has any more is
        an allow-list that silences the next real finding."""
        job = self._sample()
        for name in self.JOB_EXEMPT:
            assert hasattr(job, name), name
        for name in self.STEP_EXEMPT:
            assert hasattr(job.steps[0], name), name

    def test_squeues_answer_is_machine_readable(self):
        """The defect itself, end to end: three different answers, three different
        payloads, without reading a sentence."""
        from slurmpast.cli import _job_json
        from slurmpast.diagnose import diagnose

        base = self._sample()
        seen = {}
        for state in (True, False, None):
            job = base._replace(state="RUNNING", end=None, open_ended=True, live=state)
            doc = _job_json(job, None, diagnose(job))
            assert doc["outcome"]["open_ended_record"] is True
            assert doc["outcome"]["live"] is state
            seen[state] = doc["outcome"]["live"]
        assert len(set(map(repr, seen.values()))) == 3, seen

    def test_the_count_does_not_depend_on_which_job_it_is(self):
        """The documented figure is "N values per job", so it has to be a property
        of the payload rather than of one job.

        A conditional per-job key breaks that quietly: `log_expected` first shipped
        only when a recorded path had been tried and missed, which made the count
        97 or 99 depending on the job while this class's own sample -- which has no
        recorded path -- never saw the second. The audit passed and the README was
        wrong for anyone whose job had one.

        Three shapes here: no recorded path, a recorded path that missed, and a
        job whose log was found. Conditional root keys are a different matter and
        stay conditional -- `dropped_rows` is emitted only when non-zero, and
        nothing documents a root-key count.
        """
        from slurmpast.cli import _job_json
        from slurmpast.diagnose import diagnose

        def leaves(value):
            if isinstance(value, dict):
                return sum(leaves(v) for v in value.values())
            return 1

        def per_job(job, log_path):
            doc = _job_json(job, log_path, diagnose(job))
            return leaves({k: v for k, v in doc.items() if k not in ("steps", "findings")})

        job = self._sample()
        with_path = job._replace(std_out="/nonexistent-audit-path/j.out")
        # A requeued job too: `timing.earlier` is the other per-job field added
        # recently, and it is a *list*, which `leaves` counts as one however many
        # incarnations it holds. Stable by construction rather than by care --
        # asserted so that stays true if it is ever expanded into an object.
        requeued = job._replace(earlier=(job._replace(job_id=job.job_id + "_prev"),))
        counts = {
            per_job(job, None),
            per_job(with_path, None),
            per_job(job, "/tmp/found.out"),
            per_job(requeued, None),
        }
        assert len(counts) == 1, "the per-job count varies by job: %s" % sorted(counts)

    def test_the_documented_value_count_is_the_real_one(self):
        """`README.md` and `docs/details.md` both print a count of what `--json`
        emits, and nothing checked either. The README's test badge sat stale for
        two rounds once already; a number in prose needs the same guard.

        Per job and per step, not a single total: the total depends on how many
        steps and findings a job happens to have, so the one figure quoted before
        this (174) was the floor over the demo rather than a property of anything.
        """
        import re

        from slurmpast.cli import _job_json
        from slurmpast.diagnose import diagnose

        job = self._sample()
        doc = _job_json(job, None, diagnose(job))

        def leaves(value):
            if isinstance(value, dict):
                return sum(leaves(v) for v in value.values())
            return 1

        per_job = leaves({k: v for k, v in doc.items() if k not in ("steps", "findings")})
        per_step = len(doc["steps"][0])
        root = SRC.parent.parent
        for name in ("README.md", "docs/details.md"):
            text = (root / name).read_text()
            claim = re.search(r"(\d+) values per job, plus (\d+) for every step", text)
            assert claim, "%s no longer states the count" % name
            assert int(claim.group(1)) == per_job, "%s says %s, it is %d" % (
                name,
                claim.group(1),
                per_job,
            )
            assert int(claim.group(2)) == per_step, "%s says %s, it is %d" % (
                name,
                claim.group(2),
                per_step,
            )


class TestTheResolvedClockIsMachineReadable:
    """`--json` published the ambiguous string and withheld the number.

    `duration.parse_cpu_freq` exists because AveCPUFreq is not interpretable as
    printed: "Slurm's magnitude suffix is applied to a kHz base in some code paths
    and a Hz base in others, so the string alone is ambiguous by a factor of
    1000." It resolves that by trying both readings and keeping whichever lands in
    a plausible clock range, and returns None when neither does.

    Both text surfaces spend the resolved value -- `render.py` builds its "avg
    clock" row from `job.cpu_freq_hz`. The payload emitted `cpu.frequency`, the
    raw string, and nothing else. Measured over 20,550 real jobs on this machine
    that carry the field:

        string reads 1000x wrong          : 17503  (85%)
        tool drops it as uninterpretable  :  2061
        string and tool agree             :   986

    So the surface whose docstring promises "if the tool read it, this emits it"
    handed a consumer "3.00M" for a part the dashboard was calling 3.00 GHz, and
    handed it "385K" for a value the dashboard refused to display at all.

    `TestTheJsonPayloadKeepsItsPromise` did not catch it because its allow-list
    exempted `cpu_freq_hz` as a "derived view of an emitted number", recoverable
    from `cpu.frequency`. It is not recoverable from `cpu.frequency`; that is the
    entire point of `parse_cpu_freq`. The exemption was written to make the next
    unemitted value argue for itself, and instead it silenced one.
    """

    def _payload(self, ave_cpu_freq):
        from slurmpast.cli import _job_json
        from slurmpast.diagnose import diagnose

        job = next(j for j in history() if j.steps)
        steps = (job.steps[0]._replace(ave_cpu_freq=ave_cpu_freq),) + tuple(job.steps[1:])
        job = job._replace(steps=steps)
        return job, _job_json(job, None, diagnose(job))

    def test_the_number_the_dashboard_shows_is_in_the_payload(self):
        job, doc = self._payload("3.00M")
        assert job.cpu_freq_hz == 3.0e9, job.cpu_freq_hz
        assert doc["cpu"]["frequency_hz"] == 3.0e9, doc["cpu"]

    def test_the_raw_string_is_still_there(self):
        """The control on the fix: adding the number must not remove the string.
        A consumer reading `cpu.frequency` today keeps working."""
        _, doc = self._payload("3.00M")
        assert doc["cpu"]["frequency"] == "3.00M"

    def test_a_value_the_tool_will_not_trust_is_null_not_a_number(self):
        """ "Values that could not be read are null, never 0" -- the payload's own
        rule. `385K` appears on 69 real jobs here and resolves to neither a
        plausible kHz nor Hz reading, so the dashboard omits the row."""
        job, doc = self._payload("385K")
        assert job.cpu_freq_hz is None
        assert doc["cpu"]["frequency_hz"] is None
        assert doc["cpu"]["frequency"] == "385K"

    def test_no_frequency_at_all_is_null_on_both(self):
        _, doc = self._payload("")
        assert doc["cpu"]["frequency"] is None
        assert doc["cpu"]["frequency_hz"] is None

    def test_the_payload_and_the_dashboard_cannot_disagree(self):
        """The check that would have caught it: whatever the text surface renders
        as the clock, the machine surface must carry the same quantity. Run over
        every string real jobs here actually produce."""
        from slurmpast.duration import format_cpu_freq

        for raw in ("3.00M", "3M", "800K", "3.10M", "2.90G", "385K", "0", "196K"):
            job, doc = self._payload(raw)
            hz = doc["cpu"]["frequency_hz"]
            assert hz == job.cpu_freq_hz, raw
            if hz is None:
                continue
            # What render.py puts in the "avg clock" row, from the same number.
            assert format_cpu_freq(hz) == format_cpu_freq(doc["cpu"]["frequency_hz"]), raw
            # And it is never the naive reading of the string, which is the bug.
            assert not (raw.endswith("M") and hz == float(raw[:-1] or 0) * 1e6), (
                "%s resolved to the ambiguous reading" % raw
            )


class TestTheSdistShipsASuiteThatCanRun:
    """The released 0.7.0 sdist carried 18 of the 20 files in `tests/`.

    setuptools' default sdist file list includes `tests/test*.py` -- a distutils
    legacy rule -- and nothing else under that directory, and this project had no
    `MANIFEST.in`. `conftest.py` and `__init__.py` do not match `test*.py`, so
    every shipped module importing a fixture from `tests.conftest` failed at
    collection:

        $ pip download slurmpast==0.7.0 --no-deps --no-binary :all:
        $ tar xzf slurmpast-0.7.0.tar.gz && cd slurmpast-0.7.0 && pytest -q
        ERROR tests/test_extraction.py
        ERROR tests/test_patterns.py
        ERROR tests/test_portability.py
        ERROR tests/test_sacct.py
        ERROR tests/test_sizing.py
        E   ModuleNotFoundError: No module named 'tests.conftest'
        Interrupted: 5 errors during collection

    Not cosmetic for this package specifically: the way its portability claims
    get checked is somebody on another cluster downloading the *released*
    artefact and running it there, which is precisely what the midway2 report
    did. Shipping a suite that cannot be collected is worse than shipping none,
    because the failure reads as a broken package rather than a broken sdist.

    Checked against the manifest rather than by building an sdist: a build needs
    `build`/`wheel` in the test environment and several seconds, and the rule
    that was missing is a manifest rule.
    """

    def _rules(self):
        root = SRC.parent.parent
        manifest = root / "MANIFEST.in"
        assert manifest.exists(), "MANIFEST.in is gone; the sdist reverts to test*.py only"
        return root, [
            line.strip()
            for line in manifest.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    @staticmethod
    def _built_sdist(tmp_path):
        """The real tarball, built the way PyPI's is.

        This used to read `MANIFEST.in` and reason about what a build *would*
        include, on the stated grounds that a build needs `build` in the test
        environment. That was wrong twice over: `build>=1.0` is in this project's
        `[dev]` extra and CI installs it, and a manifest is a description of the
        artifact rather than the artifact. The report this class came from makes
        exactly that point about the whole suite -- that a green run is evidence
        about internal consistency, and the only two tests across four packages
        that caught real portability defects were the ones that touched the real
        environment or the real artifact. This is the artifact one.
        """
        try:
            from build import ProjectBuilder
        except ImportError:  # pragma: no cover - `build` is in [dev] and CI has it
            pytest.skip("`build` is not installed; cannot inspect the real sdist")

        # From a pristine copy, because setuptools reuses `src/*.egg-info/
        # SOURCES.txt` when it is present and a developer tree always has one.
        # Building in place made this test read a *cached description* of the
        # artifact instead of the artifact: with `MANIFEST.in` deleted outright,
        # both assertions below still passed. That is the same mistake the
        # manifest-reading version made, one layer down and harder to see.
        source = tmp_path / "src-copy"
        shutil.copytree(
            SRC.parent.parent,
            source,
            ignore=shutil.ignore_patterns(
                ".git",
                "*.egg-info",
                "__pycache__",
                ".pytest_cache",
                ".mypy_cache",
                ".ruff_cache",
                "dist",
                "build",
                ".claude",
            ),
        )
        path = ProjectBuilder(str(source)).build("sdist", str(tmp_path / "dist"))
        with tarfile.open(path) as tar:
            return {name.split("/", 1)[1] for name in tar.getnames() if "/" in name}

    def test_the_built_sdist_carries_every_file_under_tests(self, tmp_path):
        """Not just the two that were missing: a helper added later must not be
        left behind the same way, which is why the manifest grafts the directory
        rather than naming `conftest.py`. Compared against what is on disk, so the
        test cannot go stale as files are added."""
        root = SRC.parent.parent
        on_disk = {
            path.relative_to(root).as_posix()
            for path in (root / "tests").rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        missing = sorted(on_disk - self._built_sdist(tmp_path))
        assert missing == [], "in tests/ but not in the built sdist: %s" % ", ".join(missing)

    def test_the_built_sdist_carries_what_the_repo_audits_read(self, tmp_path):
        """Shipping a runnable suite is not enough on its own.

        Once `conftest.py` was added, eight tests still failed on a correct build,
        because this suite audits the *repository*: the dependency pin in
        `.github/workflows/ci.yml`, the prose in `docs/details.md`, the imports in
        `tools/`, and the images `README.md` points at. A suite that ships and
        then fails eight tests reads as a broken package rather than a broken
        sdist, which is the same confusion in a quieter form.
        """
        shipped = self._built_sdist(tmp_path)
        for needed in (
            ".github/workflows/ci.yml",
            "docs/details.md",
            "tools/demo_gif.py",
            "assets/demo.gif",
        ):
            assert needed in shipped, needed

    def test_the_two_files_that_were_actually_missing_are_named_in_the_repro(self):
        """The control on the claim, not on the fix: if `conftest.py` ever stops
        being importable as `tests.conftest`, the docstring above is describing a
        failure that can no longer happen and this class should be re-read rather
        than trusted."""
        root, _ = self._rules()
        assert (root / "tests" / "conftest.py").exists()
        assert (root / "tests" / "__init__.py").exists(), (
            "without this, `tests.conftest` is not an importable module path"
        )
        importers = [
            p.name
            for p in sorted((root / "tests").glob("test_*.py"))
            if "tests.conftest" in p.read_text()
        ]
        assert len(importers) >= 5, importers
