"""Wording the UI got wrong, reported from real use.

Three separate complaints, all the same failure: printing a number or a glyph
that the reader has no way to interpret.

* "⭘" appeared top-left on every screen. It is Textual's command-palette button,
  which cannot even be clicked here because mouse capture is off.
* "BURNED" was a column name I invented for resource-time consumed.
* "778 GPU-h (96.7% goodput)" used two pieces of insider shorthand and gave no
  reference frame -- a GPU-hour total means nothing without the period it covers.
"""

import os
import re

import pytest

pytest.importorskip("textual")

from slurmpast import render, tui
from slurmpast.demo import history
from slurmpast.index import History, sort_label


def make_app(jobs, **kw):
    return tui.SlurmpastApp(lambda: list(jobs), window="test", **kw)


class TestNoMysteryGlyph:
    def test_header_icon_is_blank(self):
        header = tui._header()
        assert getattr(header, "icon", "") == ""

    @pytest.mark.asyncio
    async def test_the_circle_is_gone_from_the_header(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import Header

            for header in app.screen.query(Header):
                assert getattr(header, "icon", "") == ""


class TestColumnNames:
    @pytest.mark.asyncio
    async def test_no_invented_jargon_in_the_overview_columns(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import DataTable

            labels = [str(c.label) for c in app.screen.query_one(DataTable).columns.values()]
            assert "BURNED" not in labels
            # "WORKLOAD" was this tool's own vocabulary ("what does workload
            # mean?"); "NAMES" was a bare count with nothing saying what it
            # counted; "USED" did not say used of what.
            assert "WORKLOAD" not in labels
            assert "NAMES" not in labels
            assert "JOB NAME" in labels
            # One unit per column. A single resource column printed GPU-hours for
            # GPU rows and core-hours for the rest, which hid the core-hours a
            # GPU job also burns and left no two rows comparable.
            for merged in ("USED", "RESOURCE USED", "TOTAL USED"):
                assert merged not in labels
            # FAILED and NEVER RAN overlapped, so side by side they invited being
            # added into more problems than there were runs. One column now; which
            # kind of wrong it was is a drill-down question.
            assert "FAILED" not in labels
            assert "NEVER RAN" not in labels
            assert "FLAGGED" in labels
            # CPU-hours and GPU-hours share one cell: they are the same quantity
            # in two units, and two adjacent columns read as more separate.
            assert tui.render.HOURS_PAIR_LABEL in labels

    @pytest.mark.asyncio
    async def test_a_gpu_workload_reports_its_core_hours_too(self):
        """The complaint: "if it's a gpu job it only outputs gpu hours, but gpu
        jobs also have core hours"."""
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(150, 24)) as pilot:
            await pilot.pause()
            from textual.widgets import DataTable

            table = app.screen.query_one(DataTable)
            labels = [str(c.label) for c in table.columns.values()]
            at = labels.index(tui.render.HOURS_PAIR_LABEL)
            cells = [str(table.get_row_at(r)[at]) for r in range(table.row_count)]
            pairs = [c.partition("/") for c in cells]
            with_gpu = [(cpu, gpu) for cpu, _, gpu in pairs if gpu.strip() != "-"]
            assert with_gpu, "the fixture should contain GPU workloads"
            for cpu, gpu in with_gpu:
                assert cpu.strip() != "-", (cpu, gpu)

    @pytest.mark.asyncio
    async def test_a_cpu_only_history_has_no_column_of_dashes(self):
        cpu_only = [
            j._replace(alloc_tres="billing=8,cpu=8,mem=64G,node=1", req_tres="") for j in history()
        ]
        app = make_app(cpu_only, no_logs=True)
        async with app.run_test(size=(150, 24)) as pilot:
            await pilot.pause()
            from textual.widgets import DataTable

            labels = [str(c.label) for c in app.screen.query_one(DataTable).columns.values()]
            assert "GPU-HOURS" not in labels
            assert "CPU-HOURS" in labels

    @pytest.mark.asyncio
    async def test_the_name_column_carries_only_the_name(self):
        """A "(2 names)" suffix hung off the identifier and read as clutter; the
        count is in the JSON payload and the real names are one keypress away."""
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(150, 24)) as pilot:
            await pilot.pause()
            from textual.widgets import DataTable

            table = app.screen.query_one(DataTable)
            column = [str(c.label) for c in table.columns.values()].index("JOB NAME")
            values = [str(table.get_row_at(r)[column]) for r in range(table.row_count)]
            assert values
            assert not any("names" in v for v in values), values
            assert any("#" in v for v in values), "the fixture should fold some names"

    def test_sort_label_is_plain(self):
        assert sort_label("cost") == "resource use"

    def test_plain_report_explains_the_ranking_without_the_jargon(self):
        """With both hour columns visible, a row of fewer CPU-hours outranking one
        with more looks arbitrary until you know a GPU-hour is weighted -- so the
        exchange rate has to be on screen. What went was the phrase carrying it:
        "ranked by resource use" was vocabulary only this tool used, and it named
        the sort without saying what it meant."""
        from slurmpast.index import GPU_CORE_EQUIVALENT
        from slurmpast.report import Style, render_overview

        text = render_overview(History(history()), style=Style(enabled=False))
        head = text.split("#    JOB NAME")[0]
        assert "resource use" not in head
        assert "BURNED" not in head
        assert "compute used" in head
        assert "GPU-hour = %d CPU-hours" % GPU_CORE_EQUIVALENT in head

    def test_a_cpu_only_history_is_not_told_the_exchange_rate(self):
        """With no GPU column on screen there is no ordering to explain: one hours
        column sorted descending explains itself."""
        from slurmpast.report import Style, render_overview

        cpu_only = [
            j._replace(alloc_tres="billing=8,cpu=8,mem=64G,node=1", req_tres="") for j in history()
        ]
        head = render_overview(History(cpu_only), style=Style(enabled=False)).split("#    JOB")[0]
        assert "GPU-hour" not in head
        assert "compute used" not in head

    def test_the_hash_is_explained_only_when_a_name_carries_one(self):
        from slurmpast.report import Style, render_overview

        text = render_overview(History(history()), style=Style(enabled=False))
        assert '"#" stands for' in text

        plain_names = [j._replace(name="steady-run") for j in history()]
        assert '"#"' not in render_overview(History(plain_names), style=Style(enabled=False))


class TestGpuHoursAreInterpretable:
    """A GPU-hour total is meaningless alone; concurrency is what makes it land."""

    def test_span_derived_from_the_records(self):
        h = History(history())
        assert h.span_hours is not None
        assert h.span_hours > 0

    def test_concurrency_is_hours_over_span(self):
        h = History(history())
        assert h.gpu_concurrency == pytest.approx(
            h.stats["gpu_hours_total"] / h.span_hours, rel=1e-6
        )

    def test_no_span_no_concurrency(self):
        """Rather than divide by a guess, report nothing."""
        jobs = [j._replace(start=None, end=None) for j in history()]
        h = History(jobs)
        assert h.span_hours is None
        assert h.gpu_concurrency is None

    def test_unparseable_timestamps_do_not_crash(self):
        jobs = [j._replace(start="not-a-date", end="also-not") for j in history()]
        assert History(jobs).span_hours is None

    def test_no_gpus_means_no_concurrency(self):
        cpu_only = [
            j._replace(alloc_tres="billing=8,cpu=8,mem=64G,node=1", req_tres="") for j in history()
        ]
        assert History(cpu_only).gpu_concurrency is None

    def test_the_idle_figure_qualifies_the_total_it_follows(self):
        """Written as "18 of 783 GPU-hours never computed" the ratio arrived with
        no antecedent, two units after a job count. The total leads, says it is a
        total -- "is it in total or individual jobs?" was the actual question --
        and the loss hangs off it with "of them" naming what it is 93 of."""
        from slurmpast.report import Style, render_overview

        text = render_overview(History(history()), style=Style(enabled=False))
        line = [ln for ln in text.splitlines() if "GPU-hours" in ln and "jobs" in ln][0]
        assert "GPU-hours total" in line
        assert "of them never used" in line
        assert line.index("GPU-hours") < line.index("never used")
        assert "GPU-h (" not in text  # the old abbreviated form

    def test_a_trivial_loss_is_not_worth_the_reader_s_attention(self):
        """Reported as "it says 234 jobs, then 18 GPU-hours never computed -- why
        do users need to know this?". At 2.3% they do not; the metric is the
        tool's headline finding and printing it at every magnitude is how a
        headline becomes noise."""
        from slurmpast.diagnose import looks_like_noop
        from slurmpast.report import Style, render_overview

        jobs = history()
        assert History(jobs).idle_gpu_hours is not None, "the fixture should be a loud case"

        # Same history with the idle allocations removed from the GPU pool.
        quiet = [j for j in jobs if not (j.gpu_count and looks_like_noop(j))]
        assert History(quiet).idle_gpu_hours is None
        assert "never used" not in render_overview(History(quiet), style=Style(enabled=False))

    def test_a_material_loss_still_speaks_up(self):
        h = History(history())
        idle, total = h.idle_gpu_hours
        assert idle / total >= 0.10
        assert "never computed" in h.headline()

    def test_no_jargon_survives(self):
        from slurmpast.report import Style, render_overview

        text = render_overview(History(history()), style=Style(enabled=False))
        for word in ("goodput", "BURNED", "GPU-h ("):
            assert word not in text

    @pytest.mark.parametrize("window", ["", "last 7 days"])
    def test_the_summary_is_brief(self, window):
        """It was four lines of derivable detail. Everything above the table
        should fit in a couple of lines.

        Parameterised over the window because the CLI always passes one, so the
        no-window case this used to check alone is the one configuration real
        output never has -- and it is a line shorter.
        """
        from slurmpast.report import Style, render_overview

        text = render_overview(History(history(), window=window), style=Style(enabled=False))
        head = text.split("#    JOB NAME")[0].strip().splitlines()
        body = [ln for ln in head if ln.strip() and not set(ln.strip()) <= {"-"}]
        assert len(body) <= 4, body

    def test_concurrency_still_available_to_callers(self):
        """Trimmed from the display, not deleted -- it is in the JSON payload."""
        h = History(history())
        assert h.gpu_concurrency is not None

    @pytest.mark.asyncio
    async def test_dashboard_summary_says_it_in_words(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            text = app.screen.summary_text.plain
            assert "goodput" not in text
            assert "GPU-hours total" in text
            assert "of them never used" in text


class TestNoWidgetInternalsInTests:
    """Guard against a mistake made twice already.

    A Static widget's rendered-content attribute exists in textual 0.89 and not
    in 8.x, so a test that reads it passes locally and fails in CI. That was
    fixed once, then reintroduced in a new file two commits later -- exactly the
    kind of regression a rule catches and vigilance does not. Assert on data the
    code composed (``summary_text``, ``extra_summary()``, ``clipboard_view()``)
    instead.
    """

    def test_no_test_reads_a_widget_renderable(self):
        import pathlib

        # Assembled so this file does not trip its own check.
        needle = "." + "render" + "able"
        offenders = []
        for path in sorted(pathlib.Path(__file__).parent.glob("test_*.py")):
            for number, line in enumerate(path.read_text().splitlines(), start=1):
                stripped = line.strip()
                if needle in stripped and not stripped.startswith("#"):
                    offenders.append("%s:%d" % (path.name, number))
        assert not offenders, (
            "these tests read widget internals, which differ across Textual "
            "versions: %s" % ", ".join(offenders)
        )


class TestWindowInEnglish:
    """The title bar read "now-7days → now" -- the tool's own arguments showing
    through. A reader should not have to parse a sacct time spec back out of it."""

    @pytest.mark.parametrize(
        "since,expected",
        [
            ("now-7days", "last 7 days"),
            ("now-30days", "last 30 days"),
            ("now-1day", "last 24 hours"),
            ("now-1week", "last week"),
            ("now-6months", "last 6 months"),
            ("2026-01-01", "since 2026-01-01"),
        ],
    )
    def test_relative_and_absolute(self, since, expected):
        from slurmpast.duration import humanize_window

        assert humanize_window(since) == expected

    def test_closed_range(self):
        from slurmpast.duration import humanize_window

        assert humanize_window("2026-01-01", "2026-07-15") == "2026-01-01 to 2026-07-15"

    def test_no_arrow_glyph_leaks_through(self):
        from slurmpast.duration import humanize_window

        for spec in ("now-7days", "2026-01-01", "now-1day"):
            assert "→" not in humanize_window(spec)
            assert "now-" not in humanize_window(spec)

    @pytest.mark.parametrize(
        "since,until,expected",
        [
            ("now-30days", "2026-07-15", "30 days ago to 2026-07-15"),
            ("now-1day", "2026-07-15", "24 hours ago to 2026-07-15"),
            ("now-1week", "2026-07-15", "1 week ago to 2026-07-15"),
            ("now-7days", "2026-07-20T08:00:00", "7 days ago to 2026-07-20"),
        ],
    )
    def test_a_relative_start_with_an_explicit_end_is_still_english(self, since, until, expected):
        """The relative branch was gated on there being no end time, so `-E`
        dropped the raw "now-30days" straight onto the screen -- the tool's own
        argument syntax, which is the one thing this function exists to hide.
        "last 30 days" would also be wrong: an explicit end means the range does
        not reach now."""
        from slurmpast.duration import humanize_window

        assert humanize_window(since, until) == expected

    def test_no_machine_syntax_survives_any_combination(self):
        from slurmpast.duration import humanize_window

        for since in ("now-7days", "now-1day", "now-6months", "2026-01-01", "today"):
            for until in (None, "now", "2026-07-15", "2026-07-15T09:00:00"):
                assert "now-" not in humanize_window(since, until), (since, until)

    def test_timestamps_are_trimmed_to_the_date(self):
        from slurmpast.duration import humanize_window

        assert humanize_window("2026-01-01T08:00:00") == "since 2026-01-01"


class TestColumnNamesAreUnambiguous:
    @pytest.mark.asyncio
    async def test_cpu_columns_say_which_is_which(self):
        """A bare "UTIL" beside a "CPU" column does not say whether it is CPU or
        GPU utilization -- and GPU utilization is not even recorded here.

        "CPU%" had the same fault one level down: reported as "is it memory usage
        or cpu core usage?". A percentage with no named denominator does not say.
        CPUS BUSY names both numbers ("3.0 of 4").
        """
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(160, 24)) as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            from textual.widgets import DataTable

            labels = [str(c.label) for c in app.screen.query_one(DataTable).columns.values()]
            assert "UTIL" not in labels
            assert "CPU%" not in labels
            assert "CPUS BUSY" in labels
            assert "CPU TIME" in labels
            # Wall clock and CPU time sat side by side as "ELAPSED"/"CPU TIME",
            # which did not say which was which.
            assert "WALL TIME" in labels
            assert "ELAPSED" not in labels

    @pytest.mark.asyncio
    async def test_peak_memory_is_on_the_job_list(self):
        """Reported as "why don't we have peaked memory included?" -- it is the
        figure most post-mortems start from and the list omitted it entirely."""
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(160, 24)) as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            from textual.widgets import DataTable

            table = app.screen.query_one(DataTable)
            labels = [str(c.label) for c in table.columns.values()]
            assert "PEAK MEM" in labels
            assert "MEM%" in labels
            column = labels.index("PEAK MEM")
            values = [str(table.get_row_at(r)[column]) for r in range(min(6, table.row_count))]
            assert any("iB" in v for v in values), values

    @pytest.mark.asyncio
    async def test_overview_fits_a_narrow_terminal(self):
        """It required sideways scrolling; the ribbon and a redundant column went."""
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(84, 20)) as pilot:
            await pilot.pause()
            from textual.widgets import DataTable

            columns = list(app.screen.query_one(DataTable).columns.values())
            assert "OUTCOMES" not in [str(c.label) for c in columns]
            assert "NEVER RAN" not in [str(c.label) for c in columns]
            assert sum(c.width for c in columns) <= 80


class TestCursorDoesNotRepaintCells:
    @pytest.mark.asyncio
    async def test_renderable_keeps_priority_over_the_cursor(self):
        """With the CSS default the cursor's foreground wins and every coloured
        glyph in the highlighted row turns solid white."""
        app = make_app(history(), no_logs=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import DataTable

            table = app.screen.query_one(DataTable)
            assert table.cursor_foreground_priority == "renderable"


class TestResourceRowsMatchSlurmwatch:
    def test_rows_use_the_marker_label_bar_idiom(self):
        from slurmpast.render import resource_rows

        job = [j for j in history() if j.name == "midtrain"][0]
        rows = [r.plain for r in resource_rows(job)]
        assert any(r.lstrip().startswith("●") for r in rows)
        labels = " ".join(rows)
        for expected in ("TIME", "CPU", "MEM"):
            assert expected in labels

    def test_every_gauge_row_actually_has_a_gauge(self):
        """Reported as "for gpu and disk, they are just numbers, why do they go
        with these bars? i think they are placed at the wrong place".

        They had no ceiling to be a fraction of, so they sat in the bar block with
        blank space where a bar belongs. Nothing without a gauge is in this block
        now -- GPU and DISK are ordinary detail rows.
        """
        from slurmpast.render import resource_rows

        for job in history():
            labels = [row.plain.split()[1] for row in resource_rows(job)]
            assert set(labels) <= {"TIME", "CPU", "MEM"}, labels
            assert "GPU" not in labels and "DISK" not in labels, labels
            # Each of the three is a real fraction of something the reader asked
            # for, so each draws a gauge -- the one documented exception being a
            # MaxRSS above its own limit, covered by its own test below.
            for row in resource_rows(job):
                gauged = "█" in row.plain or "░" in row.plain or "no percentage" in row.plain
                over_limit = "not a real footprint" in row.plain
                assert gauged or over_limit, row.plain

    def test_the_gpu_and_disk_facts_moved_to_the_sections(self):
        """Moved, not dropped: the numbers are still on screen."""
        from slurmpast.render import job_sections

        job = [j for j in history() if j.gpu_count and j.io_bytes][0]
        sections = dict(job_sections(job, summarized=True))
        assert "gpu" in sections and "filesystem" in sections
        gpu = {label: value for label, value, _bar in sections["gpu"]}
        assert "devices" in gpu and "gpu-hours" in gpu
        disk = {label: value for label, value, _bar in sections["filesystem"]}
        assert "read" in disk and "written" in disk

    @pytest.mark.asyncio
    async def test_a_missing_log_is_one_line(self, tmp_path, monkeypatch):
        """Slurm keeps StdOut/StdErr only in slurmctld and MinJobAge is 120s, so a
        post-mortem can never retrieve the path -- `scontrol show job` answers
        "Invalid job id" and sacct has no such field. Three lines explaining a
        limitation nobody can act on is worse than one line saying the flag.

        Exercised with logs ENABLED: every other dashboard test passes
        ``no_logs=True``, so this branch had no coverage at all and a stale import
        in it was caught by mypy rather than by a test.
        """
        # A workdir with no logs in it, and cwd moved there, so the timing-based
        # matcher cannot pick up an unrelated file from the real filesystem.
        empty = tmp_path / "run"
        empty.mkdir()
        monkeypatch.chdir(empty)
        jobs = [j._replace(work_dir=str(empty)) for j in history()]
        app = make_app(jobs, no_logs=False)
        async with app.run_test(size=(112, 40)) as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            body = "\n".join(
                "".join(s.text for s in strip) for strip in app.screen._compositor.render_strips()
            )
            log_lines = [ln.strip() for ln in body.splitlines() if ln.strip().startswith("log")]
            assert len(log_lines) == 1, log_lines
            assert "--log-dir" in log_lines[0]

    @pytest.mark.asyncio
    async def test_the_detail_sections_use_the_width(self):
        """Reported as "there is ample amount of empty space on the right side"."""
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(118, 44)) as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            body = "\n".join(
                "".join(s.text for s in strip) for strip in app.screen._compositor.render_strips()
            )
            paired = [
                ln for ln in body.splitlines() if ln.startswith("    ") and "  " in ln.strip()
            ]
            assert paired, "expected detail rows"
            # At least some lines carry two label/value pairs.
            assert any(len(ln.rstrip()) > 60 for ln in paired), paired[:4]

    @pytest.mark.asyncio
    async def test_each_section_colours_its_own_values(self):
        """The palette already spreads per-resource hues across the wheel so no two
        read alike under red-green colour blindness; every value was printed in one
        ink, which threw that away and left the eye nothing to group by."""
        from slurmpast import theme

        jobs = history()
        # A job with a kernel split AND disk traffic, so all three hues appear.
        job = [j for j in jobs if j.system_cpu_fraction is not None and j.io_bytes][0]
        app = make_app(jobs, no_logs=True)
        async with app.run_test(size=(118, 44)) as pilot:
            await pilot.pause()
            app.push_screen(tui.JobScreen(job))
            await pilot.pause()
            await pilot.pause()
            hues = {}
            for strip in app.screen._compositor.render_strips():
                text = "".join(x.text for x in strip).strip()
                for want in ("submitted", "kernel share", "read "):
                    if text.startswith(want):
                        hues[want] = {
                            x.style.color.triplet.hex
                            for x in strip
                            if x.text.strip()
                            and x.style
                            and x.style.color
                            and x.style.color.triplet
                        }
            assert theme.ACCENT in hues.get("submitted", set()), hues
            assert theme.CPU_COLOR in hues.get("kernel share", set()), hues
            assert theme.DISK_COLOR in hues.get("read ", set()), hues

    def test_no_row_divides_a_duration_by_a_duration(self):
        """Reported as "'2h54m17s of 3h52m32s over 4 cores' ... make no sense to me
        or any other user at all". The denominator was cores x elapsed -- a
        synthetic quantity the reader has to reconstruct before the row says
        anything. Every row now reads in the unit that was requested.
        """
        from slurmpast.render import resource_rows

        for job in history():
            rows = {r.plain.split()[1]: r.plain for r in resource_rows(job)}
            assert "cores busy" in rows["CPU"], rows["CPU"]
            # The CPU row names cores, not a core-time total.
            assert "over 4 cores" not in rows["CPU"]
            assert "limit" in rows["TIME"], rows["TIME"]
            assert "MEM" in rows and "limit" in rows["MEM"], rows.get("MEM")

    def test_no_gauge_row_inverts_the_meaning_of_a_full_bar(self):
        """KERNEL was a gauge among gauges where filling up meant "worse", while a
        full TIME/CPU/MEM bar means "more of what you asked for". It is a
        diagnostic, not something you request, so it moved to the cpu section."""
        from slurmpast.render import job_sections, resource_rows

        job = [j for j in history() if j.system_cpu_fraction is not None][0]
        assert not any("KERNEL" in r.plain for r in resource_rows(job))
        labels = [label for _t, rows in job_sections(job) for label, _v, _b in rows]
        assert "kernel share" in labels

    def _over_limit_mem_row(self):
        from slurmpast.render import resource_rows

        over = [
            j
            for j in history()
            if j.mem_limit_bytes and j.max_rss and j.max_rss > j.mem_limit_bytes
        ]
        assert over, "the fixture should contain an over-limit MaxRSS"
        return [r.plain for r in resource_rows(over[0]) if " MEM " in r.plain][0]

    def test_an_unusable_peak_claims_no_magnitude(self):
        """MaxRSS above the cgroup limit is not a working set -- the findings say so
        -- and drawing it as a 101%-full bar had the summary contradicting the
        diagnosis on the same screen. So: no fill."""
        row = self._over_limit_mem_row()
        assert "█" not in row, row
        assert "upper bound" in row and "limit" in row

    def test_an_unusable_peak_says_so_where_the_gauge_would_be(self):
        """Three renderings were tried and two of them lie. Blank cells left a hole
        where the rows above had bars -- "why does mem sometimes have the progress
        bar and sometimes not?". An empty track was worse, because a track IS the
        picture of 0% and the row then read as no memory used beside 58.5 GiB --
        "which one should users trust?". Neither: the column says it has nothing."""
        row = self._over_limit_mem_row()
        assert "no percentage" in row, row
        assert "░" not in row and "█" not in row, row

    def test_it_says_what_the_number_is_rather_than_what_it_is_not(self):
        """ "so not a real footprint" was asked what it meant. What it means is that
        the figure bounds the truth from above instead of measuring it."""
        row = self._over_limit_mem_row()
        assert "upper bound" in row, row

    def test_the_row_keeps_its_shape(self):
        """Which is the point of a phrase rather than blank cells: the value column
        has to stay in line with every row above it."""
        from slurmpast.render import resource_rows

        job = [
            j
            for j in history()
            if j.mem_limit_bytes and j.max_rss and j.max_rss > j.mem_limit_bytes
        ][0]
        rows = [r.plain for r in resource_rows(job)]
        ends = {r.index("   " + ("·" if "·" in r else "-")) for r in rows if len(r) > 40}
        assert len(ends) == 1, [r[:48] for r in rows]

    def test_no_row_overflows_a_normal_terminal(self):
        """Two rows wrapped in practice -- the memory limit's provenance note and
        the GPU explanation -- and a wrapped gauge row loses its alignment and its
        marker, so it stops reading as part of the block."""
        from slurmpast.render import resource_rows

        for job in history():
            for row in resource_rows(job):
                assert len(row.plain) <= 100, (job.name, row.plain)

    def test_every_value_cell_is_aligned(self):
        """The "·" separators have to land in one column or the block reads as
        ragged text. The DISK rate is the widest cell and overran a narrower field.
        """
        from slurmpast.render import resource_rows

        for job in history():
            columns = {r.plain.index("·") for r in resource_rows(job) if "·" in r.plain}
            assert len(columns) <= 1, (job.name, columns)


class TestJobDetailSaysOnlyWhatItCan:
    """Four reported faults, all the same shape: a field printed because it was
    captured, not because a reader could use it."""

    def _rows(self, job):
        from slurmpast.render import job_sections

        return {
            label: value
            for _title, rows in job_sections(job, summarized=True)
            for label, value, _bar in rows
        }

    def test_partition_qos_and_account_are_labelled_separately(self):
        """They were joined as "test / test / rcc-staff" under a label reading
        "account", so three different things looked like one value repeated and
        nothing said which slash-separated field was which."""
        job = history()[0]
        rows = self._rows(job)
        assert rows.get("partition") == job.partition
        assert rows.get("account") == job.account
        assert " / " not in rows.get("account", "")

    def test_cluster_is_not_printed(self):
        """Constant on a single-cluster site, so it is noise on every job. Still
        in the JSON for anyone federating."""
        job = history()[0]
        assert job.cluster, "the fixture does record a cluster"
        assert "cluster" not in self._rows(job)

    def test_priority_is_not_printed(self):
        """A raw site-weighted integer with no relative context is not something a
        reader can act on or even interpret."""
        job = history()[0]
        assert job.priority is not None, "the fixture does record a priority"
        assert "priority" not in self._rows(job)

    def test_the_ordinary_scheduling_pass_is_not_named(self):
        """ "scheduled by main" told the reader nothing."""
        job = [j for j in history() if j.scheduled_by == "main"][0]
        assert "scheduled" not in self._rows(job)

    def test_backfill_is_named_in_english(self):
        """The one case worth a word: it is invisible in every other tool, and it
        means a tighter --time got the job in early."""
        job = [j for j in history() if j.scheduled_by == "backfill"][0]
        value = self._rows(job).get("scheduled", "")
        assert "backfill" in value
        assert "gap" in value

    def test_the_dropped_fields_are_still_in_the_json(self):
        """Off the screen, not out of the payload."""
        from slurmpast.cli import _job_json
        from slurmpast.diagnose import diagnose

        job = history()[0]
        payload = _job_json(job, None, diagnose(job))
        assert payload["identity"]["cluster"] == job.cluster
        assert payload["timing"]["priority"] == job.priority


class TestARatioNeedsADenominatorWorthDividingBy:
    """Both of these printed a confident figure derived from a fiction.

    Found by rendering 120 real job details and reading every line, which is the
    only way this class of defect surfaces: each number is individually
    well-formed, and only the magnitude gives it away.
    """

    def test_a_hundredth_of_a_second_yields_no_kernel_share(self, healthy_job):
        """Observed on a real record: TotalCPU 0.01s, all of it system, rendered as
        "kernel share 100.0%" beside "user / system 0.00s / 0.01s" -- which reads
        as a syscall-bound job when it is a job that barely ran."""
        from slurmpast.render import job_sections

        barely = healthy_job._replace(
            steps=tuple(
                s._replace(total_cpu=0.01, user_cpu=0.0, system_cpu=0.01) for s in healthy_job.steps
            )
        )
        assert barely.system_cpu_fraction is None
        rows = {label: value for _, section in job_sections(barely) for label, value, _ in section}
        assert "kernel share" not in rows
        # The raw split still shows: it is a measurement, not a derived claim.
        assert "user / system" in rows

    def test_a_real_split_is_still_reported(self, healthy_job):
        busy = healthy_job._replace(
            steps=tuple(
                s._replace(total_cpu=4000.0, user_cpu=1000.0, system_cpu=3000.0)
                for s in healthy_job.steps
            )
        )
        assert busy.system_cpu_fraction == pytest.approx(0.75)

    def test_an_unterminated_record_reports_no_gpu_hours(self, healthy_job):
        """gpu-hours is devices x elapsed, and on an open record elapsed is
        `now - start`: a RUNNING record 64 days old rendered "gpu-hours 4615.9".
        Every other consumer already suppresses elapsed-derived claims for these."""
        from slurmpast.render import job_sections

        assert healthy_job.gpu_count, "the fixture should hold GPUs"
        open_record = healthy_job._replace(open_ended=True, end=None, elapsed=64 * 86400.0)
        labels = [
            label
            for title, section in job_sections(open_record)
            for label, _, _ in section
            if title == "gpu"
        ]
        assert "devices" in labels
        assert "gpu-hours" not in labels

    def test_a_finished_record_still_reports_them(self, healthy_job):
        from slurmpast.render import job_sections

        labels = [
            label
            for title, section in job_sections(healthy_job)
            for label, _, _ in section
            if title == "gpu"
        ]
        assert "gpu-hours" in labels


class TestNothingIsShownTwiceOnOneScreen:
    def test_average_memory_is_dropped_when_it_equals_the_peak(self, healthy_job):
        """AveRSS equals MaxRSS on 1,318 of 1,341 real records -- single-task jobs,
        where there is nothing to average over -- so on 98% of job screens this row
        was a second copy of the figure the MEM gauge shows three lines above."""
        from slurmpast.render import job_sections

        flat = healthy_job._replace(
            steps=tuple(s._replace(ave_rss=s.max_rss) for s in healthy_job.steps)
        )
        assert flat.ave_rss == flat.max_rss
        labels = [label for _, section in job_sections(flat) for label, _, _ in section]
        assert "average" not in labels

    def test_it_survives_when_the_footprint_actually_grew(self, healthy_job):
        """The 2% where it is the thing you came to find."""
        from slurmpast.render import job_sections

        grew = healthy_job._replace(
            steps=tuple(s._replace(ave_rss=(s.max_rss or 0) / 4.0) for s in healthy_job.steps)
        )
        labels = [label for _, section in job_sections(grew) for label, _, _ in section]
        assert "average" in labels


class TestNothingWrapsAtEightyColumns:
    """80 columns is the canonical minimum -- an unresized login-node terminal, a
    pasted snippet, a CI log. A single over-long line wraps and reads as a
    rendering fault, especially sitting above a table that lines up perfectly.
    """

    def _at_eighty(self, monkeypatch, render):
        import shutil

        monkeypatch.setattr(shutil, "get_terminal_size", lambda *a: os.terminal_size((80, 24)))
        return render()

    def test_the_overview_fits(self, monkeypatch):
        from slurmpast.report import Style, render_overview

        text = self._at_eighty(
            monkeypatch, lambda: render_overview(History(history()), style=Style(enabled=False))
        )
        too_long = [line for line in text.splitlines() if len(line) > 80]
        assert not too_long, too_long

    def test_the_ranking_caption_splits_rather_than_wrapping(self, monkeypatch):
        """Joined with " · " the two clauses came to 86 characters."""
        from slurmpast.report import Style, render_overview

        text = self._at_eighty(
            monkeypatch, lambda: render_overview(History(history()), style=Style(enabled=False))
        )
        head = text.split("#   JOB NAME")[0]
        assert "compute used" in head and '"#" stands for' in head
        assert "CPU-hours) · " not in head, "should have broken onto its own line"

    def test_the_job_list_fits(self, monkeypatch):
        from slurmpast.report import Style, render_list

        jobs = History(history()).usable_jobs[:10]
        text = self._at_eighty(
            monkeypatch, lambda: render_list(jobs, style=Style(enabled=False), limit=10)
        )
        too_long = [line for line in text.splitlines() if len(line) > 80]
        assert not too_long, too_long

    def test_the_node_screen_fits_including_the_correction_note(self, monkeypatch):
        """The note explaining a withheld verdict is a whole sentence of prose under
        a table that lines up exactly, so it is the line most likely to overrun."""
        import random

        from slurmpast.model import Job
        from slurmpast.nodes import node_table
        from slurmpast.report import Style, render_nodes

        rng = random.Random(4242)
        jobs = []
        for node in range(20):
            for _ in range(30):
                jobs.append(
                    Job(
                        job_id="%d" % len(jobs),
                        name="w",
                        node_list="node%03d" % node,
                        elapsed=600.0,
                        timelimit=3600.0,
                        state="FAILED" if rng.random() < 0.20 else "COMPLETED",
                    )
                )
        assert node_table(jobs, workload="w")["held_back"], "seed no longer exercises the note"
        text = self._at_eighty(
            monkeypatch,
            lambda: render_nodes(History(jobs), metric="failure", style=Style(enabled=False)),
        )
        too_long = [line for line in text.splitlines() if len(line) > 80]
        assert not too_long, too_long


class TestTheMemorySectionOnlySaysThingsWorthSaying:
    """Reported of "peak on midway3-0372 task 0" and "virtual 1.9 TiB (38x resident
    - address space, not memory used)": "it makes no sense".

    Both were measured against the real 6,440-job history and both earned the
    complaint.
    """

    def _labels(self, job):
        from slurmpast.render import job_sections

        return [
            label
            for title, rows in job_sections(job, summarized=True)
            if title == "memory"
            for label, _value, _gauge in rows
        ]

    def _job(self, **alloc):
        from slurmpast.sacct import parse

        from .conftest import row

        base = {
            "JobID": "950",
            "JobName": "w",
            "State": "COMPLETED",
            "ElapsedRaw": "3600",
            "AllocTRES": "cpu=4,mem=64G,node=1",
            "NNodes": "1",
            "NTasks": "1",
            "ReqMem": "64Gn",
        }
        base.update(alloc)
        return parse(
            "\n".join(
                [
                    row(**base),
                    row(
                        JobID="950.batch",
                        JobName="batch",
                        State="COMPLETED",
                        MaxRSS="1048576K",
                        MaxVMSize="2068502792K",
                        MaxRSSNode="midway3-0372",
                        MaxRSSTask="0",
                        NTasks=base.get("NTasks", "1"),
                    ),
                ]
            )
        )[0]

    def test_where_the_peak_was_is_dropped_when_there_is_one_place_it_could_be(self):
        """6,416 of 6,440 real jobs -- 99.6% -- had one node and one task, so the row
        named the only possible answer."""
        assert "peak on" not in self._labels(self._job())

    def test_it_is_kept_where_which_rank_peaked_is_a_real_question(self):
        job = self._job(AllocTRES="cpu=16,mem=64G,node=4", NNodes="4", NTasks="4", ReqMem="16Gn")
        assert "peak on" in self._labels(job)

    def test_virtual_size_is_not_on_screen_at_all(self):
        """It ran at a median of 44x the resident figure on this history, reached
        5,449,406x, and printed 43.2 TiB -- an enormous number whose own text argued
        that it meant nothing. Nothing consumes it: no finding, no sizing rule."""
        for job in list(history()) + [self._job()]:
            assert "virtual" not in self._labels(job)

    def test_but_it_is_still_in_the_json(self):
        """Removed from the summary, not from the tool."""
        from slurmpast.cli import _job_json
        from slurmpast.diagnose import diagnose

        job = self._job()
        payload = _job_json(job, None, diagnose(job))
        assert payload["memory"]["virtual_bytes"] == 2068502792 * 1024
        assert payload["memory"]["virtual_to_resident"] is not None
        assert payload["memory"]["peak_node"] == "midway3-0372"


class TestTheDashboardWrapsToTheTerminalItIsOn:
    """`report._prose_width` fixed this for the plain output and said why -- "These
    were hardcoded at 72, 82 and 84, so a finding hard-broke mid-sentence two thirds
    of the way across a wide terminal and overran a narrow one." The dashboard kept
    the constants: findings at 86, actions at 82, under an 8-cell indent, so below
    ~96 columns Textual re-wrapped the already-wrapped text and dropped the orphan
    to column 0 with no indent at all.
    """

    @staticmethod
    async def _open_cot_exp(pilot, app):
        index = [g.label for g in app.screen._rows].index("cot-exp") + 1
        await pilot.press(str(index))
        await pilot.pause()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("width", [70, 80, 120])
    async def test_findings_fit_the_screen(self, width, monkeypatch):
        from textual.widgets import Static

        seen = {}
        original = Static.update

        def spy(self, renderable="", *args, **kwargs):
            if getattr(self, "id", None) == "body":
                seen["body"] = getattr(renderable, "plain", str(renderable))
            return original(self, renderable, *args, **kwargs)

        monkeypatch.setattr(Static, "update", spy)
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(width, 44)) as pilot:
            await pilot.pause()
            await self._open_cot_exp(pilot, app)
            for keys in (("p",), ("escape", "enter")):
                for key in keys:
                    await pilot.press(key)
                    await pilot.pause()
                widest = max(len(line) for line in seen["body"].splitlines())
                assert widest <= width, "%d cells on a %d-cell screen" % (widest, width)

    @pytest.mark.asyncio
    async def test_a_wide_terminal_is_actually_used(self, monkeypatch):
        """The other half: a fixed 86 also refused the room a wide terminal has."""
        from textual.widgets import Static

        seen = {}
        original = Static.update

        def spy(self, renderable="", *args, **kwargs):
            if getattr(self, "id", None) == "body":
                seen["body"] = getattr(renderable, "plain", str(renderable))
            return original(self, renderable, *args, **kwargs)

        monkeypatch.setattr(Static, "update", spy)
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(150, 44)) as pilot:
            await pilot.pause()
            await self._open_cot_exp(pilot, app)
            await pilot.press("p")
            await pilot.pause()
            assert max(len(line) for line in seen["body"].splitlines()) > 100


class TestTheWorkloadBannerWrapsAtAll:
    """`" ".join(render.wrap(evidence, 100))` puts the wrapped lines straight back
    together, so the width argument did nothing whatever: the evidence went out as
    one 138-cell line at every terminal size, and only the first of Textual's
    soft-wrapped lines kept the two-space indent the `"\\n  "` prefix intends. The
    advice block nineteen lines below has wrapped to the real width since the last
    audit; this half was missed.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("width", [70, 80, 120])
    async def test_no_line_exceeds_the_terminal(self, width):
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(width, 44)) as pilot:
            await pilot.pause()
            index = [g.label for g in app.screen._rows].index("cot-exp") + 1
            await pilot.press(str(index))
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            lines = app.screen.summary_text.plain.splitlines()
            assert len(lines) > 2, "no finding banner to check"
            for line in lines:
                assert len(line) <= width, "%d cells on a %d-cell screen: %r" % (
                    len(line),
                    width,
                    line,
                )

    @pytest.mark.asyncio
    async def test_every_continuation_keeps_the_indent(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(80, 44)) as pilot:
            await pilot.pause()
            index = [g.label for g in app.screen._rows].index("cot-exp") + 1
            await pilot.press(str(index))
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            evidence = [
                line
                for line in app.screen.summary_text.plain.splitlines()
                if line.startswith("  ") and "runs of cot-exp" not in line and line.strip()
            ]
            assert evidence, "the evidence did not wrap, so there is nothing to check"
            assert all(line.startswith("  ") for line in evidence)


class TestCountsAreSpelledForTheirNumber:
    """The two counts that were not. Everything else in this codebase carries the
    `"" if n == 1 else "s"` idiom -- including, in `render_nodes`, twenty-four lines
    below the offender."""

    @staticmethod
    def _nodes_line(text):
        for line in text.splitlines():
            if "below" in line and "omitted" in line:
                return line
        return ""

    def test_the_plain_node_screen(self):
        from slurmpast.report import Style, render_nodes

        line = self._nodes_line(render_nodes(History(history()), style=Style(enabled=False)))
        assert "1 node below" in line, line
        assert "1 nodes" not in line

    @pytest.mark.asyncio
    async def test_the_dashboard_node_screen(self):
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(120, 44)) as pilot:
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            # From the screen, not the widget: `Static.renderable` exists in
            # textual 0.89 and not in 8.x, and CI runs both.
            text = app.screen.summary_text.plain
        line = self._nodes_line(text)
        assert "1 node below" in line, line
        assert "1 nodes" not in line


class TestEveryCountIsSpelledForItsNumber:
    """The ten the class above missed.

    `TestCountsAreSpelledForTheirNumber` pinned the two counts on the node screen
    and stopped there, so the same `"" if n == 1 else "s"` idiom stayed missing
    from nine other sentences across five modules -- every one of them reachable,
    and each reproduced here by running the code that emits it rather than by
    reading the format string.

    Each case carries its control: the plural spelling has to be untouched, or a
    fix that simply deleted the "s" would pass.
    """

    @staticmethod
    def _job(jid, state, name="w", elapsed=3600.0, cpu=1e5, node="n1", tl=1800.0, mem="16G"):
        from slurmpast.model import Job, Step

        return Job(
            job_id=str(jid),
            name=name,
            user="me",
            partition="test",
            state=state,
            elapsed=elapsed,
            timelimit=tl,
            node_list=node,
            alloc_tres="cpu=8,mem=" + mem,
            nnodes=1,
            ntasks=1,
            alloc_cpus=8,
            start="2026-07-01T0%d:00:00" % (jid % 10),
            end="2026-07-01T09:00:00",
            steps=(Step(step_id="%d.0" % jid, total_cpu=cpu, cpu_time=elapsed, max_rss=10**9),),
        )

    def _noop(self, jid, elapsed):
        # Over NOOP_MIN_ELAPSED with under NOOP_CPU_SECONDS of CPU: an allocation
        # that held resources and computed nothing.
        return self._job(jid, "COMPLETED", elapsed=elapsed, cpu=0.5)

    def test_one_idle_allocation_is_not_one_allocations(self):
        from slurmpast.patterns import summarize

        one = " ".join(f.evidence for f in summarize([self._noop(1, 4000.0)]))
        assert "1 allocation ran over" in one, one
        assert "1 allocations" not in one
        two = " ".join(
            f.evidence for f in summarize([self._noop(1, 4000.0), self._noop(2, 5000.0)])
        )
        assert "2 allocations ran over" in two, two

    def test_one_quick_kill_is_not_one_were_killed(self):
        from slurmpast.patterns import summarize

        # One long idle allocation and one killed inside the 15-minute window.
        jobs = [self._noop(1, 4000.0), self._noop(2, 800.0)]
        one = " ".join(f.evidence for f in summarize(jobs))
        assert "1 was killed within 15 minutes" in one, one
        assert "1 were killed" not in one
        assert "that one was already noticed" in one, one
        two = " ".join(f.evidence for f in summarize(jobs + [self._noop(3, 700.0)]))
        assert "2 were killed within 15 minutes" in two, two
        assert "those were already noticed" in two

    def test_a_dominant_state_of_one_is_not_one_were(self):
        """Five failures across five distinct states leave every state on a count
        of one, and the dominant one is still named."""
        from slurmpast.patterns import find_repeat_failures

        states = ["FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL", "BOOT_FAIL"]
        spread = [self._job(i, s) for i, s in enumerate(states, start=1)]
        text = " ".join(f.evidence for f in find_repeat_failures(spread))
        assert "1 was " in text, text
        assert "1 were " not in text
        same = [self._job(i, "FAILED") for i in range(1, 6)]
        assert "5 were FAILED" in " ".join(f.evidence for f in find_repeat_failures(same))

    def test_one_hidden_repeat_group_is_not_one_groups(self):
        from slurmpast.patterns import find_repeat_failures

        jobs, jid = [], 100
        for name in ("alpha", "beta", "gamma", "delta", "epsilon"):
            for _ in range(5):
                jid += 1
                jobs.append(self._job(jid, "FAILED", name=name))
        titles = " ".join(f.title for f in find_repeat_failures(jobs))
        assert "1 further group shows" in titles, titles
        assert "1 further groups" not in titles
        # Control: two hidden groups keep the plural, and the verb agrees.
        jobs += [self._job(jid + n, "FAILED", name="zeta") for n in range(1, 6)]
        assert "2 further groups show" in " ".join(f.title for f in find_repeat_failures(jobs))

    def test_one_computing_timeout_is_not_were_cut_off(self):
        from slurmpast.sizing import walltime_advice

        hung = [self._job(i, "TIMEOUT", elapsed=1800.0, cpu=0.5) for i in range(1, 5)]
        one = walltime_advice([*hung, self._job(9, "TIMEOUT", elapsed=1800.0, cpu=1e4)])
        assert "The other 1 did compute, and was cut off" in one.caution, one.caution
        two = walltime_advice(
            [
                *hung,
                self._job(9, "TIMEOUT", elapsed=1800.0, cpu=1e4),
                self._job(10, "TIMEOUT", elapsed=1800.0, cpu=1e4),
            ]
        )
        assert "The other 2 did compute, and were cut off" in two.caution, two.caution

    def test_one_placement_is_not_one_placements(self):
        from slurmpast.nodes import node_table
        from slurmpast.render import nodes_baseline

        one = nodes_baseline(node_table([self._job(1, "FAILED")]))
        assert "over 1 placement;" in one, one
        assert "1 placements" not in one
        three = nodes_baseline(node_table([self._job(i, "FAILED") for i in range(1, 4)]))
        assert "over 3 placements" in three, three

    def test_one_node_below_the_threshold_reads_as_one(self):
        from slurmpast.nodes import node_table
        from slurmpast.render import nodes_empty_reason

        table = node_table([self._job(1, "FAILED")])
        one = nodes_empty_reason(table, "failure", None)
        assert "1 seen, and it is below it" in one, one
        assert "1 seen, all below it" not in one
        two = node_table([self._job(1, "FAILED"), self._job(2, "FAILED", node="n2")])
        assert "2 seen, all below it" in nodes_empty_reason(two, "failure", None)

    def test_a_single_run_workload_is_not_one_runs(self):
        from slurmpast.index import History
        from slurmpast.report import Style, render_sizing

        text = render_sizing(History([self._job(1, "OUT_OF_MEMORY")]), style=Style(enabled=False))
        assert "· 1 run" in text, text
        assert "· 1 runs" not in text
        pair = History([self._job(1, "OUT_OF_MEMORY"), self._job(2, "OUT_OF_MEMORY")])
        assert "· 2 runs" in render_sizing(pair, style=Style(enabled=False))

    def test_the_headline_counts_one_job_as_one_job(self):
        from slurmpast.index import History

        assert History([self._job(1, "FAILED")]).headline() == "1 of 1 job failed"
        assert History([self._job(1, "COMPLETED")]).headline() == "1 job, nothing flagged"
        two = History([self._job(1, "FAILED"), self._job(2, "COMPLETED")])
        assert two.headline() == "1 of 2 jobs failed"

    def test_one_hidden_workload_is_not_one_workloads(self):
        from slurmpast.index import History

        pair = History(
            [self._job(1, "COMPLETED", name="alpha"), self._job(2, "COMPLETED", name="beta")]
        )
        one = pair.tail_summary(shown=1)
        assert one.startswith("1 more workload (1 run)"), one
        assert "workloads" not in one
        # The control. `gamma` runs twice so it sorts first and is the one shown;
        # the two single-run workloads behind it are the tail.
        trio = History(
            [
                self._job(1, "COMPLETED", name="alpha"),
                self._job(2, "COMPLETED", name="beta"),
                self._job(3, "COMPLETED", name="gamma"),
                self._job(4, "COMPLETED", name="gamma"),
            ]
        )
        assert trio.tail_summary(shown=1).startswith("2 more workloads (2 runs)")


class TestALongValueIsCutTheSameWayOnBothSurfaces:
    """`wrap` breaks at spaces, and a job name has none.

    So the plain job screen's per-row budget did nothing for the one value most
    likely to blow it: a 68-character name came out of the wrapper as one token and
    the row went to 89 cells on an 80-column terminal. The dashboard had always
    clipped it -- `JobScreen.cell` calls `_clip` for anything `render.PATH_ROWS`
    does not declare a path -- so the two surfaces disagreed about the same row of
    the same screen, and only the pasted one was wrong.
    """

    LONG = "nemotron-batch-h200-tokenize-shards-stage3-retry-17-experimental-arm"

    def _job(self, name=None, work_dir=""):
        from slurmpast.model import Job, Step

        return Job(
            job_id="1",
            name=name or self.LONG,
            user="me",
            partition="test",
            state="FAILED",
            elapsed=3600.0,
            timelimit=1800.0,
            node_list="n1",
            alloc_tres="cpu=8,mem=16G",
            nnodes=1,
            ntasks=1,
            alloc_cpus=8,
            work_dir=work_dir,
            start="2026-07-01T01:00:00",
            end="2026-07-01T02:00:00",
            steps=(Step(step_id="1.0", total_cpu=1e4, cpu_time=3600.0, max_rss=10**9),),
        )

    @staticmethod
    def _row(text, label):
        return next(line for line in text.splitlines() if line.strip().startswith(label + " "))

    def test_the_plain_name_row_fits_an_eighty_column_terminal(self, monkeypatch):
        import shutil

        from slurmpast.report import Style, render_job

        monkeypatch.setattr(shutil, "get_terminal_size", lambda *a: os.terminal_size((80, 24)))
        text, _ = render_job(self._job(), style=Style(enabled=False))
        row = self._row(text, "name")
        assert len(row.rstrip()) <= 80, "%d cells: %r" % (len(row.rstrip()), row)
        assert "…" in row, "a cut cell has to say it was cut: %r" % row

    def test_a_name_that_fits_is_untouched(self, monkeypatch):
        """The control. Every ordinary name renders byte for byte as before."""
        import shutil

        from slurmpast.report import Style, render_job

        monkeypatch.setattr(shutil, "get_terminal_size", lambda *a: os.terminal_size((80, 24)))
        text, _ = render_job(self._job(name="cot-exp"), style=Style(enabled=False))
        row = self._row(text, "name")
        assert row.strip().endswith("cot-exp")
        assert "…" not in row

    def test_a_workdir_still_overruns_on_purpose(self, monkeypatch):
        """`PATH_ROWS` keeps its exemption: "--plain exists to be pasted, and a path
        you cannot copy whole is no use in a ticket"."""
        import shutil

        from slurmpast.render import PATH_ROWS
        from slurmpast.report import Style, render_job

        assert "workdir" in PATH_ROWS
        deep = "/scratch/midway3/a-long-login/projects/very/deep/tree/goes/on/and/on/here"
        monkeypatch.setattr(shutil, "get_terminal_size", lambda *a: os.terminal_size((80, 24)))
        text, _ = render_job(self._job(work_dir=deep), style=Style(enabled=False))
        row = self._row(text, "workdir")
        assert deep in row, "the path must survive whole: %r" % row
        assert "…" not in row

    @pytest.mark.asyncio
    async def test_the_dashboard_cuts_it_the_same_way(self):
        job = self._job()
        app = make_app([job], no_logs=True)
        async with app.run_test(size=(80, 44)) as pilot:
            await pilot.pause()
            app.push_screen(tui.JobScreen(job))
            await pilot.pause()
            body = "\n".join(
                "".join(segment.text for segment in strip)
                for strip in app.screen._compositor.render_strips()
            )
        assert self.LONG not in body, "the dashboard should have cut it"
        assert "…" in body
        assert not [line for line in body.splitlines() if len(line.rstrip()) > 80]


class TestAGaugedDetailRowIsDrawnOnBothSurfaces:
    """`job_sections` gives a detail row three values -- label, value, gauge -- and
    the plain renderer read the first two and stopped.

    `row[2]` was consumed nowhere in `report.py`, so `slowest task` came out as a
    bar in the app and a bare percentage in a paste:

        dashboard : slowest task   ███████████▎░░  80.0% below average (task 3 …)
        --plain   : slowest task   80.0% below average (task 3 …)

    `pair_rows` already gives a gauged row a line of its own -- "rows which carry a
    gauge still take a line to themselves" -- so the plain layout was reserving the
    room for a bar it then declined to draw. Exactly one row type carries a gauge
    and the demo has exactly one job that exercises it, which is why three rounds
    of width and drift sweeps went past it: round six's "the demo's own values are
    short", in its narrowest form yet.
    """

    JOB_ID = "5100056"  # the one multi-task run in the synthetic history

    @staticmethod
    def _row(text, label="slowest task"):
        matches = [ln for ln in text.splitlines() if label in ln and "consumed" not in ln]
        assert matches, "no %r row in:\n%s" % (label, text)
        return matches[0]

    def _job(self):
        return next(j for j in history() if j.job_id == self.JOB_ID)

    def test_the_fixture_still_has_a_gauged_detail_row(self):
        """If the demo ever loses its multi-task job this whole class goes vacuous,
        so it says so rather than passing quietly."""
        gauged = [
            (title, row[0])
            for title, rows in render.job_sections(self._job(), summarized=True)
            for row in rows
            if row[2] is not None
        ]
        assert gauged, "no detail row carries a gauge any more"

    def test_the_plain_report_draws_it(self):
        from slurmpast.report import Style, render_job

        text, _ = render_job(self._job(), style=Style(enabled=False), no_logs=True)
        row = self._row(text)
        assert "█" in row, row
        assert "80.0% below average" in row

    @pytest.mark.asyncio
    async def test_the_dashboard_draws_the_same_width_of_bar(self):
        job = self._job()
        app = make_app([job], no_logs=True)
        async with app.run_test(size=(150, 60)) as pilot:
            await pilot.pause()
            app.push_screen(tui.JobScreen(job))
            await pilot.pause()
            await pilot.pause()
            dash = "\n".join(
                "".join(seg.text for seg in strip)
                for strip in app.screen._compositor.render_strips()
            )
        from slurmpast.report import Style, render_job

        plain, _ = render_job(job, style=Style(enabled=False), no_logs=True)

        def bar_cells(line):
            return sum(1 for ch in line if ch in "█░▏▎▍▌▋▊▉")

        assert bar_cells(self._row(dash)) == render.DETAIL_BAR_WIDTH
        assert bar_cells(self._row(plain)) == render.DETAIL_BAR_WIDTH

    def test_ascii_mode_reaches_this_bar_too(self):
        """A bar is the thing `--ascii` was built for, and the first version of this
        fix left the argument off -- putting block glyphs back into output that had
        just been made pure ASCII."""
        from slurmpast.report import Style, render_job

        text, _ = render_job(self._job(), style=Style(enabled=False), no_logs=True, ascii_mode=True)
        row = self._row(text)
        assert "#" in row, row
        assert not any(ord(ch) > 127 for ch in text)

    def test_an_ungauged_row_gains_no_bar(self):
        """The control: only the row that carries a gauge gets one."""
        from slurmpast.report import Style, render_job

        text, _ = render_job(self._job(), style=Style(enabled=False), no_logs=True)
        assert "█" not in self._row(text, "peak on")


class TestTheDashboardWrapsEveryLineOfAFinding:
    """The title was the one line of the three that nothing wrapped.

    `report` learned to wrap it -- "A title is a sentence ... and this was the one
    line of the three going out at whatever length it happened to be" -- and the
    dashboard did not, so Textual soft-wrapped it and dropped the tail to column 1,
    out from under the tag that introduces it:

           WARN  Peak memory reads above the limit, yet nothing was
         OOM-killed
                 32.5 GiB against a 32.0 GiB per-node limit, so it is not ...

    `TestTheDashboardWrapsToTheTerminalItIsOn` above measures the same widget and
    was green throughout, because it opens `cot-exp`, whose longest finding title
    is 47 cells. The one that breaks is 61, and it is on the OOM jobs.
    """

    # 61 cells, the longest title `diagnose` produces, and 8 cells of chrome in
    # front of it -- so it needs a 69-cell screen to fit on one line.
    LONG_TITLE = "Peak memory reads above the limit, yet nothing was OOM-killed"

    @staticmethod
    def _body_spy(monkeypatch, seen):
        from textual.widgets import Static

        original = Static.update

        def spy(self, renderable="", *args, **kwargs):
            if getattr(self, "id", None) == "body":
                seen["body"] = getattr(renderable, "plain", str(renderable))
            return original(self, renderable, *args, **kwargs)

        monkeypatch.setattr(Static, "update", spy)

    def _jobs_with_a_long_title(self):
        from slurmpast.diagnose import diagnose

        jobs = [
            job
            for job in history()
            if any(f.title == self.LONG_TITLE for f in diagnose(job).findings)
        ]
        assert jobs, "the demo no longer produces the %d-cell title" % len(self.LONG_TITLE)
        return jobs

    def test_the_fixture_still_carries_the_long_title(self):
        """If `diagnose` ever shortens it this class goes vacuous, so it says so."""
        assert len(self.LONG_TITLE) == 61
        self._jobs_with_a_long_title()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("width", [60, 68, 74, 100])
    async def test_no_line_of_the_job_screen_overruns(self, width, monkeypatch):
        seen = {}
        self._body_spy(monkeypatch, seen)
        job = self._jobs_with_a_long_title()[0]
        app = make_app([job], no_logs=True)
        async with app.run_test(size=(width, 60)) as pilot:
            await pilot.pause()
            app.push_screen(tui.JobScreen(job))
            await pilot.pause()
            await pilot.pause()
        over = [ln for ln in seen["body"].splitlines() if len(ln) > width]
        assert not over, "%d cells on a %d-cell screen: %r" % (
            max(len(ln) for ln in over),
            width,
            over[0],
        )

    @pytest.mark.asyncio
    async def test_a_wrapped_title_hangs_under_itself(self, monkeypatch):
        """The point of wrapping it here rather than leaving it to Textual: a soft
        wrap restarts at column 0, which is what took the block apart."""
        seen = {}
        self._body_spy(monkeypatch, seen)
        job = self._jobs_with_a_long_title()[0]
        app = make_app([job], no_logs=True)
        async with app.run_test(size=(60, 60)) as pilot:
            await pilot.pause()
            app.push_screen(tui.JobScreen(job))
            await pilot.pause()
            await pilot.pause()
        lines = seen["body"].splitlines()
        head = next(i for i, ln in enumerate(lines) if "Peak memory reads" in ln)
        tail = lines[head + 1]
        assert "OOM-killed" in tail, tail
        # Under the title, not under the tag and not at column 0.
        assert tail.startswith(" " * tui._FINDING_TITLE_INDENT), repr(tail)
        assert tail[tui._FINDING_TITLE_INDENT] != " ", repr(tail)

    @pytest.mark.asyncio
    async def test_a_wide_screen_still_gets_it_on_one_line(self):
        """The control. Wrapping must not break a title that already fitted."""
        job = self._jobs_with_a_long_title()[0]
        app = make_app([job], no_logs=True)
        async with app.run_test(size=(120, 60)) as pilot:
            await pilot.pause()
            app.push_screen(tui.JobScreen(job))
            await pilot.pause()
            await pilot.pause()
            text = "\n".join(
                "".join(seg.text for seg in strip)
                for strip in app.screen._compositor.render_strips()
            )
        assert self.LONG_TITLE in text


class TestAGaugedRowCountsItsOwnBar:
    """The dashboard's budget for a detail value was
    ``4 + PAIR_LABEL_WIDTH + 1`` -- the indent and the label column.

    The row then drew a 14-cell bar and a 2-cell gap in front of the value, and
    those 16 cells were in no sum anywhere, so a gauged row went 16 past the edge
    and Textual dropped the tail to column 1. At 80 columns, not merely a narrow
    one:

        slowest task     ███████████▎░░  80.0% below average (task 3 on
    midway3-0372)

    The same row under `--plain` had counted the bar since round five ("Continuation
    hangs past the bar as well as the label"). Both go through
    `render.pair_value_budget` now.
    """

    JOB_ID = "5100056"  # the one multi-task run: the only gauged detail row

    def _job(self):
        return next(j for j in history() if j.job_id == self.JOB_ID)

    def test_the_budget_subtracts_the_bar(self):
        without = render.pair_value_budget(100, 0)
        with_bar = render.pair_value_budget(100, render.DETAIL_BAR_WIDTH + render.DETAIL_BAR_GAP)
        assert without - with_bar == render.DETAIL_BAR_WIDTH + render.DETAIL_BAR_GAP

    @pytest.mark.asyncio
    @pytest.mark.parametrize("width", [68, 74, 80, 100])
    async def test_the_gauged_row_fits(self, width, monkeypatch):
        from textual.widgets import Static

        seen = {}
        original = Static.update

        def spy(self, renderable="", *args, **kwargs):
            if getattr(self, "id", None) == "body":
                seen["body"] = getattr(renderable, "plain", str(renderable))
            return original(self, renderable, *args, **kwargs)

        monkeypatch.setattr(Static, "update", spy)
        job = self._job()
        app = make_app([job], no_logs=True)
        async with app.run_test(size=(width, 60)) as pilot:
            await pilot.pause()
            app.push_screen(tui.JobScreen(job))
            await pilot.pause()
            await pilot.pause()
        rows = [ln for ln in seen["body"].splitlines() if "slowest task" in ln]
        assert rows, seen["body"]
        assert len(rows[0]) <= width, "%d cells on a %d-cell screen: %r" % (
            len(rows[0]),
            width,
            rows[0],
        )

    @pytest.mark.asyncio
    async def test_the_node_name_survives_rather_than_being_cut(self, monkeypatch):
        """Fitting it by clipping would be no fix: which task on which node is the
        entire content of the row. It wraps, and hangs past the bar -- the shape
        `--plain` has always drawn."""
        from textual.widgets import Static

        seen = {}
        original = Static.update

        def spy(self, renderable="", *args, **kwargs):
            if getattr(self, "id", None) == "body":
                seen["body"] = getattr(renderable, "plain", str(renderable))
            return original(self, renderable, *args, **kwargs)

        monkeypatch.setattr(Static, "update", spy)
        job = self._job()
        app = make_app([job], no_logs=True)
        async with app.run_test(size=(74, 60)) as pilot:
            await pilot.pause()
            app.push_screen(tui.JobScreen(job))
            await pilot.pause()
            await pilot.pause()
        lines = seen["body"].splitlines()
        index = next(i for i, ln in enumerate(lines) if "slowest task" in ln)
        block = lines[index] + lines[index + 1].strip()
        assert "midway3-0372" in block, lines[index : index + 2]
        hang = 4 + render.PAIR_LABEL_WIDTH + 1 + render.DETAIL_BAR_WIDTH + render.DETAIL_BAR_GAP
        assert lines[index + 1].startswith(" " * hang), repr(lines[index + 1])
        assert lines[index + 1][hang] != " ", repr(lines[index + 1])

    @pytest.mark.asyncio
    async def test_a_sentence_value_keeps_its_second_half(self, monkeypatch):
        """The same budget clipped rather than wrapped, so the row that explains
        why a GPU figure is missing lost the half naming the fix:

            utilization  not gathered by this cluster (needs AutoDetect=nvml in g…

        `--plain` wrapped it and kept `gres.conf`.
        """
        from textual.widgets import Static

        seen = {}
        original = Static.update

        def spy(self, renderable="", *args, **kwargs):
            if getattr(self, "id", None) == "body":
                seen["body"] = getattr(renderable, "plain", str(renderable))
            return original(self, renderable, *args, **kwargs)

        monkeypatch.setattr(Static, "update", spy)
        job = self._job()
        app = make_app([job], no_logs=True)
        async with app.run_test(size=(80, 60)) as pilot:
            await pilot.pause()
            app.push_screen(tui.JobScreen(job))
            await pilot.pause()
            await pilot.pause()
        body = seen["body"]
        assert "gres.conf" in body, body
        assert "…" not in body.split("utilization")[1].splitlines()[0]


class TestTheSizingCaveatReachesEverySurface:
    """`Advice.caution` is commented "what would make this advice wrong".

    `--sizing` has printed it since it was added and `--sizing --json` carries it
    in `_asdict()`. `WorkloadScreen` never read the field at all, so the dashboard
    was the one surface of three handing over a directive with the caveat removed
    -- six of the demo's ten actionable lines have one:

        --mem=3G           MaxRSS sums RSS across the process tree ... upper bound
        --cpus-per-task=2  This is a GPU workload: cores may be there to feed
                           dataloader workers, and cutting them can starve the GPU

    The second is the one that matters: the app told you to cut a GPU job from six
    cores to two and dropped the sentence saying that can starve the card.

    Not solved by pointing at `slurmpast --sizing for why` -- this block already
    rejected that once, in its own comment: "a bare number with no basis, and for
    the reason a different command in a different program. The reason belongs
    where the number is."
    """

    @staticmethod
    def _cautioned():
        """(group, advice) pairs the dashboard shows that carry a caveat."""
        from slurmpast.sizing import recommend

        h = History(history())
        out = []
        for group in h.groups:
            for advice in recommend(group.jobs):
                if advice.actionable and advice.caution:
                    out.append((group, advice))
        assert out, "the demo no longer produces a cautioned recommendation"
        return out

    def test_the_fixture_still_has_the_gpu_core_caveat(self):
        """The sharpest instance, named so it cannot quietly leave the fixture."""
        cautions = [a.caution for _, a in self._cautioned()]
        assert any("starve the GPU" in c for c in cautions), cautions

    @pytest.mark.asyncio
    @pytest.mark.parametrize("width", [60, 74, 100, 140])
    async def test_the_workload_banner_carries_it(self, width, monkeypatch):
        from textual.widgets import Static

        seen = {}
        original = Static.update

        def spy(self, renderable="", *args, **kwargs):
            if getattr(self, "id", None) == "summary":
                seen["summary"] = getattr(renderable, "plain", str(renderable))
            return original(self, renderable, *args, **kwargs)

        monkeypatch.setattr(Static, "update", spy)
        group, advice = self._cautioned()[0]
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(width, 44)) as pilot:
            await pilot.pause()
            index = [g.label for g in app.screen._rows].index(group.label) + 1
            await pilot.press(str(index))
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
        banner = seen["summary"]
        assert advice.suggestion in banner, banner
        # Wrapped, so match on words rather than on the whole sentence.
        head = advice.caution.split()[0:4]
        assert " ".join(head) in " ".join(banner.split()), banner

    @pytest.mark.asyncio
    @pytest.mark.parametrize("width", [60, 70, 74, 80, 100, 140])
    async def test_it_does_not_overrun_the_screen(self, width, monkeypatch):
        """The caveat is three lines of prose landing in a banner that had none, at
        an indent of 32. Held to the same rule as everything else on the screen."""
        from textual.widgets import Static

        seen = {}
        original = Static.update

        def spy(self, renderable="", *args, **kwargs):
            if getattr(self, "id", None) == "summary":
                seen["summary"] = getattr(renderable, "plain", str(renderable))
            return original(self, renderable, *args, **kwargs)

        monkeypatch.setattr(Static, "update", spy)
        group, _ = self._cautioned()[0]
        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(width, 44)) as pilot:
            await pilot.pause()
            index = [g.label for g in app.screen._rows].index(group.label) + 1
            await pilot.press(str(index))
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
        over = [ln for ln in seen["summary"].splitlines() if len(ln) > width]
        assert not over, "%d cells on a %d-cell screen: %r" % (
            max(len(ln) for ln in over),
            width,
            over[0],
        )

    def test_the_plain_view_still_has_it_and_uses_the_shared_mark(self):
        """The control, and the drift guard: one marker, both surfaces."""
        from slurmpast.report import Style, render_sizing

        text = render_sizing(History(history()), style=Style(enabled=False))
        _, advice = self._cautioned()[0]
        assert ("        %s" % render.CAUTION_MARK) in text
        assert advice.caution.split(".")[0][:40] in " ".join(text.split())

    def test_json_has_carried_it_all_along(self):
        """The third surface, asserted so the pair above is a trio rather than a
        coincidence."""
        from slurmpast.sizing import recommend

        h = History(history())
        payloads = [a._asdict() for g in h.groups for a in recommend(g.jobs)]
        assert any(p["caution"] for p in payloads), payloads[:2]


class TestAWorkloadNameWithNoSpacesInIt:
    """`wrap` breaks at spaces, and a folded workload name need not have any.

    `report` documents this exact failure for a *detail value* -- "a 68-character
    job name is one word, so it came out of the wrapper unchanged and the row went
    to 89 cells on an 80-column terminal" -- and fixed it there with a clip. Two
    other places do the same wrap without the clip, and a real cluster has the name
    to prove it: over two days of cluster-wide history the longest job name is 123
    characters and contains no space at all.

        --sizing header, every width from 60 to 120:  125 cells
        workload screen title:                        123 cells, soft-wrapped
                                                      mid-name to column 0

    Neither could show up on the demo, whose folded names are `att-speed-#`.
    """

    # The real one, from `sacct --allusers`. Kept verbatim: an invented name would
    # not have the shape -- underscores throughout and a parenthesised tail.
    LONG = (
        "nf-NFCORE_RNASEQ_RNASEQ_FASTQ_QC_TRIM_FILTER_SETSTRANDEDNESS_FASTQ_"
        "SUBSAMPLE_FQ_SALMON_SALMON_INDEX_(genome.transcripts.fa)"
    )

    def test_the_fixture_is_one_word(self):
        assert len(self.LONG) == 123, len(self.LONG)
        assert " " not in self.LONG

    def test_wrap_alone_cannot_break_it(self):
        """The premise. If `wrap` ever learns to split a long word this class is
        testing something that no longer happens, and should say so."""
        assert render.wrap(self.LONG, 40) == [self.LONG]

    def test_wrap_or_clip_does(self):
        for width in (20, 40, 78, 98):
            lines = render.wrap_or_clip(self.LONG, width)
            assert all(len(line) <= width for line in lines), (width, lines)
            assert lines[0].endswith("…"), lines[0]

    def test_wrap_or_clip_leaves_ordinary_prose_alone(self):
        """The control: a sentence that wraps must not be clipped as well."""
        prose = "the most any run used was 1.9 GiB, which is well under the limit"
        assert render.wrap_or_clip(prose, 30) == render.wrap(prose, 30)
        assert not any(line.endswith("…") for line in render.wrap_or_clip(prose, 30))

    def _jobs(self):
        base = next(j for j in history() if j.completed and j.steps)
        return [base._replace(job_id="99%04d" % i, name=self.LONG) for i in range(6)]

    @pytest.mark.parametrize("columns", ["60", "80", "100", "120"])
    def test_the_sizing_header_fits(self, columns, monkeypatch):
        from slurmpast.report import Style, render_sizing

        monkeypatch.setenv("COLUMNS", columns)
        text = render_sizing(History(self._jobs()), style=Style(enabled=False))
        over = [line for line in text.splitlines() if len(line) > int(columns)]
        assert not over, "%d cells: %r" % (len(over[0]), over[0][:80])
        assert "nf-NFCORE" in text, "the name is clipped, not dropped"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("width", [80, 100, 160])
    async def test_the_workload_title_fits(self, width, monkeypatch):
        from textual.widgets import Static

        seen = {}
        original = Static.update

        def spy(self, renderable="", *args, **kwargs):
            if getattr(self, "id", None) == "summary":
                seen["t"] = getattr(renderable, "plain", str(renderable))
            return original(self, renderable, *args, **kwargs)

        monkeypatch.setattr(Static, "update", spy)
        app = make_app(self._jobs(), no_logs=True)
        async with app.run_test(size=(width, 26)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            composited = [
                "".join(segment.text for segment in strip).rstrip()
                for strip in app.screen._compositor.render_strips()
            ]
        # The *title*, which is what was 123 cells. The counts appended after it can
        # still take the line past the width and soft-wrap, exactly as the overview's
        # own summary does with a long window string -- that is accepted behaviour
        # on these screens and is not what this class is about.
        title = seen["t"].splitlines()[0].split("  ·  ")[0]
        assert len(title) <= width, "%d cells: %r" % (len(title), title[:80])
        assert title.startswith("nf-NFCORE"), title[:40]
        # And nothing reaches the screen wider than the screen.
        over = [line for line in composited if len(line) > width]
        assert not over, "%d cells: %r" % (len(over[0]), over[0][:80])

    @pytest.mark.asyncio
    async def test_an_ordinary_name_is_not_clipped(self):
        """The control on the dashboard side: the demo's own titles are untouched."""

        app = make_app(history(), no_logs=True)
        async with app.run_test(size=(100, 26)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            title = app.screen.summary_text.plain.splitlines()[0]
        assert "…" not in title, title


# The exchange rate as (number, unit, number, unit) -- the facts a reader takes off
# whichever surface drew it, rather than the sentence that carried them. Compared
# this way a rate that moved, or that changed unit, fails on either surface.
_RATE = re.compile(r"(\d+(?:\.\d+)?)\s+(GPU-hours?)\s*=\s*(\d+(?:\.\d+)?)\s+(CPU-hours?)")


def _rate_facts(text):
    """The one exchange rate `text` quotes, or `None` if it quotes none."""
    found = {(m[1], m[2], m[3], m[4]) for m in _RATE.finditer(text)}
    # A surface that says it twice has to say it the same way both times.
    assert len(found) <= 1, "one surface quoted two rates: %r" % (sorted(found),)
    return found.pop() if found else None


class TestOneExchangeRateAcrossBothSurfaces:
    """`render.py` exists so "the dashboard and `--plain` cannot drift", and the
    GPU/CPU-hour exchange rate is the fact that proved the rule: the dashboard
    ranked every workload it listed by a weighting it named nowhere, while a paste
    of the same table explained itself. `render.gpu_hours_equivalence` fixed that
    by giving both front ends one string to place.

    Only the `--plain` half of it was pinned --
    `TestColumnNames.test_plain_report_explains_the_ranking_without_the_jargon`
    above -- so the dashboard could lose the note again, or quote a different
    number or unit, with nothing failing.

    So these compare the two surfaces against each other, and both against
    `render.gpu_hours_equivalence()` itself, rather than asserting a literal on
    each. What that does and does not settle, said plainly: a rate missing from
    one surface, or one quoting 8 where the other quotes 16, or "CPU-hour" against
    "core-hour", all fail. A `tui.py` that happened to spell the same sentence out
    by hand would still pass, because its note is built once at import and cannot
    be re-rendered against a changed constant -- so its side is pinned by being
    character-identical to the shared string, and `--plain`'s side, which does
    re-render, is pinned to the constant directly by the second control below.
    """

    @staticmethod
    async def _dashboard_facts(jobs):
        """What the dashboard tells a reader about the rate, rendered headlessly.

        The overview is where both hour columns are on screen, and `?` is where
        the dashboard explains that table -- the same position the `--plain`
        caption occupies above it.
        """
        app = make_app(jobs, no_logs=True)
        async with app.run_test(size=(150, 60)) as pilot:
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            assert isinstance(app.screen, tui.HelpScreen)
            return _rate_facts(app.screen.help_text.plain)

    @staticmethod
    def _plain_facts(jobs):
        from slurmpast.report import Style, render_overview

        return _rate_facts(render_overview(History(jobs), style=Style(enabled=False)))

    @pytest.mark.asyncio
    async def test_the_dashboard_quotes_the_rate_the_plain_caption_does(self):
        """`--demo`'s history, so the comparison is over fixed content."""
        from slurmpast.index import GPU_CORE_EQUIVALENT

        jobs = history()
        plain = self._plain_facts(jobs)
        dashboard = await self._dashboard_facts(jobs)
        assert plain is not None, "the --plain caption names no exchange rate"
        assert dashboard is not None, "the dashboard names no exchange rate"
        assert plain == dashboard, "the two surfaces quote different rates: %r vs %r" % (
            plain,
            dashboard,
        )
        # And what they agree on is the shared string, not a coincidence: same
        # number, same units, sourced from `render`.
        assert plain == _rate_facts(render.gpu_hours_equivalence())
        assert plain == ("1", "GPU-hour", "%d" % GPU_CORE_EQUIVALENT, "CPU-hours"), plain

    @pytest.mark.asyncio
    async def test_they_still_agree_with_a_real_record_in_the_history(self, healthy_job):
        """Realism over the demo: job 51170455 as `sacct` reported it -- 3 GPUs for
        1h52m, so it moves both of the hour columns the rate is there to explain.
        """
        assert healthy_job.gpu_count, "the fixture should carry GPU hours"
        jobs = [*history(), healthy_job]
        plain = self._plain_facts(jobs)
        dashboard = await self._dashboard_facts(jobs)
        assert plain is not None
        assert plain == dashboard, (plain, dashboard)

    @pytest.mark.asyncio
    async def test_the_comparison_can_see_the_two_surfaces_drift(self, monkeypatch):
        """The control, and the reason the tests above are a comparison rather than
        two independent literals: move one surface off the shared string and the
        comparison must fail.

        `report` calls `render.gpu_hours_equivalence` on every render, so patching
        the name it imported moves `--plain` alone; the dashboard's note is built
        once at import from that same function, which is what keeps the two
        together when nobody is patching anything. Without this, the assertion
        `plain == dashboard` would pass just as happily on two `None`s.
        """
        from slurmpast import report

        monkeypatch.setattr(report, "gpu_hours_equivalence", lambda: "1 GPU-hour = 3 CPU-hours")
        jobs = history()
        plain = self._plain_facts(jobs)
        dashboard = await self._dashboard_facts(jobs)
        assert plain == ("1", "GPU-hour", "3", "CPU-hours"), plain
        assert dashboard is not None, "nothing was compared against"
        assert plain != dashboard, "a rate that drifted on one surface went unnoticed"

    def test_the_plain_caption_follows_the_constant_rather_than_a_literal(self, monkeypatch):
        """The second control, on the surface that can carry one: `report` builds
        its caption per render, so if the number there were a literal instead of
        `GPU_CORE_EQUIVALENT` every assertion above would still pass.

        Patching `render`'s copy of the constant -- the one
        `gpu_hours_equivalence` reads -- is the whole chain from the weight the
        ranking is actually computed at through to the sentence on screen.
        """
        monkeypatch.setattr(render, "GPU_CORE_EQUIVALENT", 3.0)
        assert _rate_facts(render.gpu_hours_equivalence()) == ("1", "GPU-hour", "3", "CPU-hours")
        assert self._plain_facts(history()) == ("1", "GPU-hour", "3", "CPU-hours")
