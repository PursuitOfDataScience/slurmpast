"""SP-27, SP-28 and SP-29 — the findings still open after the 0.8.2 round.

* **SP-28** is the severe one and it is on the headline gauge: for a job that is
  still running, ``sacct`` has flushed nothing, so the peak was taken over
  whatever short-lived steps had already *finished*.  A job holding 462 MiB
  against ``--mem=512M`` reported **2.2 MiB, 0.4%** — a 210x understatement, with
  ``peak_trustworthy: true`` beside it.  Reproduced independently on a second
  cluster while fixing it, in the other direction: ``sacct`` offered a finished
  step's 358 MiB for a job whose live steps held 12.7 MiB.
* **SP-27** — history is fully materialised, and 19.4 MB of the string payload
  over 13,321 real jobs was *duplication*: ``uid`` and ``account`` each had one
  distinct value held as 13,321 separate string objects.
* **SP-29** — ``--sizing`` rendered an empty result set as a green "every
  workload is already about right", which is the least-informed state in the most
  reassuring colour.
"""

import json

import pytest

from slurmpast import sacct as sacctmod
from slurmpast.index import History
from slurmpast.model import Job, Step
from slurmpast.report import render_sizing
from slurmpast.sacct import (
    SacctError,
    _apply_live_metrics,
    _parse_live_metrics,
    merge_live_metrics,
    read_live_metrics,
)


# --------------------------------------------------------------------------
# SP-28 -- a running job's counters come from sstat, or from nowhere
# --------------------------------------------------------------------------
#: `sacct -j <id> -n -P -o JobID,State,MaxRSS,TotalCPU,Elapsed`, verbatim shape.
#: The `.0` and `.1` steps are not the workload: they are `srun --overlap`
#: monitor steps that watching the job created -- slurmwatch's own node hop, or
#: an interactive probe -- and their ~2 MiB became the reported peak.
def _running_job(mem_limit=512 * 1024 * 1024, with_straggler=True):
    steps = [
        Step(step_id="1.batch", state="RUNNING", elapsed=292.0, total_cpu=0.0),
        Step(step_id="1.extern", state="RUNNING", elapsed=292.0, total_cpu=0.0),
    ]
    if with_straggler:
        steps += [
            Step(
                step_id="1.0", state="COMPLETED", elapsed=1.0, max_rss=2228 * 1024, total_cpu=0.227
            ),
            Step(
                step_id="1.1", state="COMPLETED", elapsed=1.0, max_rss=2232 * 1024, total_cpu=0.225
            ),
        ]
    return Job(
        job_id="1",
        state="RUNNING",
        elapsed=292.0,
        alloc_cpus=1,
        ncpus=1,
        req_mem_raw="512Mn",
        req_mem_bytes=mem_limit,
        req_cpus=1,
        cpu_time_alloc=292.0,
        total_cpu_alloc=0.452,
        steps=tuple(steps),
    )


def _finished_job():
    """The same job, ended -- enough for ``History`` to form one group from it."""
    return _running_job()._replace(
        state="COMPLETED",
        steps=tuple(s._replace(state="COMPLETED") for s in _running_job().steps),
    )


class TestARunningJobsPeakIsNotAStragglersPeak:
    def test_a_finished_step_of_a_running_job_is_not_its_peak(self):
        job = _running_job()
        # 2228K was the answer, from a one-second monitoring step.
        assert job.max_rss is None
        assert job.mem_utilization is None

    def test_the_same_steps_are_read_once_the_job_ends(self):
        """The step-selection logic was never the bug.

        Once the job ends the same code takes the max over steps and picks
        correctly -- which is why the COMPLETED reading was right all along and
        the RUNNING one was not.
        """
        job = _running_job()._replace(
            state="COMPLETED",
            steps=tuple(
                s._replace(
                    state="COMPLETED",
                    max_rss=473084 * 1024 if s.step_id == "1.batch" else s.max_rss,
                )
                for s in _running_job().steps
            ),
        )
        assert job.max_rss == 473084 * 1024
        assert job.mem_utilization == pytest.approx(0.902, abs=0.002)

    def test_an_unflushed_cpu_counter_is_not_zero_cpu(self):
        # `TotalCPU=00:00:00` on a live step is no reading. Rendered as a
        # confident `0.0%` / `0.0 of 1 cores busy`, it reported a job spinning at
        # 100% of a core as having done nothing.
        job = _running_job()
        assert job.total_cpu is None
        assert job.cpu_utilization is None
        assert job.cores_busy is None

    def test_the_allocation_row_is_not_a_fallback_while_running(self):
        """Two clusters disagree about whether that field is even updated live.

        One showed ``16:58`` for a job whose steps summed to five seconds, the
        other ``00:00.452`` for a job at 100% of a core -- and a ratio built from
        an unflushed numerator over an elapsed-to-*now* denominator is exactly the
        confident-wrong answer this module exists to avoid.
        """
        job = _running_job()
        assert job.total_cpu_alloc == 0.452, "the field is there"
        assert job.total_cpu is None, "and is not used while the job runs"
        # It IS the fallback once the job has ended and no step recorded a figure.
        ended = job._replace(
            state="COMPLETED",
            steps=tuple(s._replace(state="COMPLETED", total_cpu=None) for s in job.steps),
        )
        assert ended.total_cpu == 0.452

    def test_the_whole_memory_block_reads_one_population(self):
        """The peak was routed through the live steps and its siblings were not.

        `ave_rss` kept reading `work_steps` and `max_vmsize`/`max_pages` kept
        reading `steps`, so adjacent lines of one report described different sets
        of processes. Measured on job 53834744 on midway3, running:

            ● MEM  0.0%  · 12.7 MiB of the 50.0 GiB limit so far
            memory
              average          2.2 GiB

        -- an average 181x the peak. In `--json`, `peak_bytes 13271040` beside
        `average_bytes 2409766912`, `virtual_to_resident 5852.9` and
        `step_spread 1142.4`, every one of the last three taken from a finished
        straggler.
        """
        job = _running_job(with_straggler=False)._replace(
            steps=(
                Step(
                    step_id="1.batch",
                    state="RUNNING",
                    elapsed=292.0,
                    max_rss=12 * 1024**2,
                    ave_rss=8 * 1024**2,
                    max_vmsize=458 * 1024**2,
                    max_pages=3,
                ),
                # The straggler: an `srun --overlap` monitor that has already
                # exited, holding figures an order of magnitude away in every
                # column.
                Step(
                    step_id="1.0",
                    state="COMPLETED",
                    elapsed=1.0,
                    max_rss=358 * 1024**2,
                    ave_rss=2298 * 1024**2,
                    max_vmsize=74000 * 1024**2,
                    max_pages=9999,
                ),
            ),
        )
        assert job.max_rss == 12 * 1024**2
        assert job.ave_rss == 8 * 1024**2, "not the straggler's 2298 MiB"
        assert job.max_vmsize == 458 * 1024**2
        assert job.max_pages == 3
        # And the ratios built from them are now ratios of one population.
        assert job.rss_task_imbalance == pytest.approx(1.5, abs=0.01)
        assert job.vmsize_to_rss == pytest.approx(38.17, abs=0.01)
        assert job.rss_step_spread is None, "one live step is not a spread"

    def test_a_finished_jobs_memory_block_is_unchanged(self):
        """The control. `measured_steps` is every step once the job has ended, so
        routing the siblings through it must be a no-op there -- and `.extern`
        must stay excluded from the average and included in the virtual size,
        exactly as before."""
        job = _finished_job()._replace(
            steps=(
                Step(step_id="1.batch", state="COMPLETED", max_rss=100, ave_rss=50, max_vmsize=900),
                Step(step_id="1.0", state="COMPLETED", max_rss=400, ave_rss=200, max_vmsize=800),
                Step(
                    step_id="1.extern",
                    state="COMPLETED",
                    max_rss=7,
                    ave_rss=9999,
                    max_vmsize=5000,
                    max_pages=42,
                ),
            ),
        )
        assert job.ave_rss == 200, "extern still excluded"
        assert job.max_vmsize == 5000, "extern still included"
        assert job.max_pages == 42
        assert job.rss_step_spread == pytest.approx(4.0)

    def test_a_job_nobody_watched_was_only_honest_by_luck(self):
        # With no finished straggler the old code reported `n/a` -- correct, and
        # only because nothing had attached to the job. Same answer now, for a
        # reason rather than by accident.
        assert _running_job(with_straggler=False).max_rss is None

    def test_sstat_figures_reach_the_gauge(self):
        job = _running_job()
        merged = _apply_live_metrics(
            job,
            {
                "1.batch": {
                    "max_rss": 473084 * 1024,
                    "ave_cpu": 291.0,
                    "ntasks": 1,
                    "max_rss_node": "n01",
                    "max_rss_task": "0",
                    "ave_rss": None,
                    "max_vmsize": None,
                    "max_pages": None,
                },
                "1.extern": {
                    "max_rss": 2004 * 1024,
                    "ave_cpu": 0.0,
                    "ntasks": 1,
                    "max_rss_node": "n01",
                    "max_rss_task": "0",
                    "ave_rss": None,
                    "max_vmsize": None,
                    "max_pages": None,
                },
            },
        )
        assert merged.max_rss == 473084 * 1024
        assert merged.mem_utilization == pytest.approx(0.902, abs=0.002)
        assert merged.total_cpu == pytest.approx(291.0)
        assert merged.cpu_utilization == pytest.approx(0.996, abs=0.01)
        assert merged.live_metrics is True
        assert merged.peak_is_live_reading is True

    def test_a_finished_step_is_never_overwritten_by_sstat(self):
        # A step that has ended has real accounting; `sstat` has nothing to say
        # about it and must not be allowed to.
        job = _running_job()
        merged = _apply_live_metrics(
            job,
            {
                "1.0": {
                    "max_rss": 999 * 1024 * 1024,
                    "ave_cpu": 500.0,
                    "ntasks": 1,
                    "max_rss_node": "",
                    "max_rss_task": "",
                    "ave_rss": None,
                    "max_vmsize": None,
                    "max_pages": None,
                },
            },
        )
        straggler = next(s for s in merged.steps if s.step_id == "1.0")
        assert straggler.max_rss == 2228 * 1024

    def test_a_terminal_job_is_not_asked_about(self):
        asked = []

        def _runner(args):
            asked.append(args)
            return ""

        done = _running_job()._replace(state="COMPLETED")
        assert merge_live_metrics([done], runner=_runner) == [done]
        assert asked == [], "one sstat call per history is one too many when nothing runs"

    def test_one_call_covers_every_live_job(self):
        asked = []

        def _runner(args):
            asked.append(args)
            return ""

        jobs = [_running_job()._replace(job_id=str(i)) for i in range(1, 6)]
        merge_live_metrics(jobs, runner=_runner)
        assert len(asked) == 1, asked
        joined = " ".join(asked[0])
        assert "--jobs=1,2,3,4,5" in joined
        assert "sstat" in asked[0][0]

    def test_a_failing_sstat_leaves_the_records_alone(self):
        # Another user's job, a job that just ended, a site with no
        # jobacct_gather. The caller's fallback is `n/a`, which is the correct
        # answer and not a degradation.
        def _runner(args):
            raise SacctError("sstat: error: no steps running for job 1")

        job = _running_job()
        assert merge_live_metrics([job], runner=_runner) == [job]
        assert read_live_metrics(["1"], runner=_runner) == {}


class TestAStaleOpenRecordIsNotInProgress:
    """`in_progress` keyed purely on state, and a stale open record is not a state.

    `sacct` reports ``State=RUNNING`` with ``End=Unknown`` for jobs that died long
    ago -- the case `cli._mark_open_records` exists to reconcile -- and four such
    records are in this cluster's history. Treating one as in progress made
    `measured_steps` drop every step it has, because they have all ended, so a
    record whose steps DID flush a real MaxRSS reported ``None`` and lost a final
    measurement that exists. `live is False` is a measurement (squeue was asked and
    answered); the state is not, so the measurement wins.
    """

    def _stale(self):
        return _running_job(with_straggler=False)._replace(
            open_ended=True,
            live=False,
            # The steps of a dead-but-open record have ENDED and flushed -- that is
            # the shape of the thing. Only the job row was left saying RUNNING.
            steps=(
                Step(step_id="1.batch", state="COMPLETED", elapsed=292.0, max_rss=473084 * 1024),
            ),
        )

    def test_a_record_squeue_has_never_heard_of_is_not_in_progress(self):
        assert self._stale().in_progress is False

    def test_its_flushed_measurement_is_reported_rather_than_lost(self):
        assert self._stale().max_rss == 473084 * 1024

    def test_an_unanswered_query_is_not_evidence_the_job_is_gone(self):
        """``live is None`` -- not asked, or squeue unreachable.

        Three values, not two. Reading "no answer" as "no such job" would turn
        every run with squeue offline into a claim about jobs that are running.
        """
        job = self._stale()._replace(live=None)
        assert job.in_progress is True
        assert job.max_rss is None, "no live step, so nothing this job's figures"

    def test_a_job_squeue_confirms_is_running_is_still_in_progress(self):
        # The control: the whole SP-28 fix depends on this staying True, and on a
        # finished straggler still being refused as the peak.
        job = self._stale()._replace(live=True)
        assert job.in_progress is True
        assert job.max_rss is None


class TestTheSstatParser:
    #: Real output from a live job, reordered into `_SSTAT_FIELDS`:
    #: JobID, MaxRSS, MaxRSSNode, MaxRSSTask, AveRSS, MaxVMSize, MaxPages,
    #: AveCPU, MinCPU, NTasks.  The `.extern` row's AveCPU is verbatim, and is an
    #: overflowed counter rather than a time.
    OUT = (
        "53834744.extern|||||||213503982334-14:25:51||0\n"
        "53834744.batch|4208K|midway3-0200|0|4208K|439748K|0|00:00.000|00:00.000|1\n"
        "53834744.49|12960K|midway3-0200|0|8348K|469384K|0|00:01.500|00:01.000|2\n"
    )

    def test_it_reads_the_rows(self):
        found = _parse_live_metrics(self.OUT)
        assert set(found) == {"53834744"}
        steps = found["53834744"]
        assert steps["53834744.batch"]["max_rss"] == 4208 * 1024
        assert steps["53834744.49"]["max_rss"] == 12960 * 1024
        assert steps["53834744.49"]["ntasks"] == 2

    def test_an_overflowed_cpu_counter_is_discarded(self):
        # 213503982334 days is 585 million years. `parse_duration` will happily
        # return it, and a CPU time longer than any job can run is not a
        # measurement. Asserted on a row that carries a real reading beside it, so
        # the row survives the "nothing measured" guard and the discard is what is
        # being tested rather than the drop.
        found = _parse_live_metrics(
            "53834744.49|12960K|midway3-0200|0|8348K|469384K|0|213503982334-14:25:51|00:01.000|2\n"
        )
        step = found["53834744"]["53834744.49"]
        assert step["ave_cpu"] is None
        assert step["max_rss"] == 12960 * 1024

    def test_a_row_carrying_only_a_task_count_is_not_a_measurement(self):
        """The `.extern` row of `OUT`, which used to be stored.

        `all(v in (None, "") for v in measured.values())` reads as "nothing was
        measured", but `NTasks=0` is neither `None` nor `""`, so a row whose only
        content was a zero task count survived with every useful field empty. A
        task count is a description of the step's shape, not a reading off it.
        """
        assert "53834744.extern" not in _parse_live_metrics(self.OUT)["53834744"]
        # And a bare `NTasks` on its own is not enough either.
        assert _parse_live_metrics("53834744.extern|||||||||4\n") == {}

    def test_a_measured_zero_is_still_a_measurement(self):
        # The control for the guard above: `MaxRSS=0` is a reading of zero, not an
        # absence of one, and narrowing the guard must not start discarding it.
        found = _parse_live_metrics("53834744.batch|0|midway3-0200|0|||||00:00.000|1\n")
        assert found["53834744"]["53834744.batch"]["max_rss"] == 0

    def test_ave_cpu_is_scaled_by_the_task_count(self):
        # `sstat` reports AveCPU *per task*; `TotalCPU` is the whole step.
        job = Job(
            job_id="53834744",
            state="RUNNING",
            elapsed=10.0,
            steps=(Step(step_id="53834744.49", state="RUNNING", ntasks=2),),
        )
        merged = _apply_live_metrics(job, _parse_live_metrics(self.OUT)["53834744"])
        step = merged.steps[0]
        assert step.ave_cpu == pytest.approx(1.5)
        assert step.total_cpu == pytest.approx(3.0)

    @pytest.mark.parametrize("text", ["", "\n", "garbage", "a|b|c"])
    def test_unusable_output_yields_nothing(self, text):
        assert _parse_live_metrics(text) == {}

    def test_an_allocation_row_is_not_a_step(self):
        # sstat should not emit one, and a row with no `.` is not a step id.
        assert _parse_live_metrics("53834744|4208K|n|0|4208K|1|1|1|1|0\n") == {}


class TestTheJsonSaysWhereTheFigureCameFrom:
    def _payload(self, job):
        from slurmpast.cli import _job_json
        from slurmpast.diagnose import diagnose

        return json.loads(json.dumps(_job_json(job, None, diagnose(job), no_logs=True)))

    def test_a_running_job_is_never_called_trustworthy(self):
        # It used to read `true` on a figure that was 0.5% of the truth -- and a
        # job that is still going has not reached its peak in any case.
        payload = self._payload(_running_job())
        assert payload["memory"]["peak_trustworthy"] is False
        assert payload["memory"]["job_in_progress"] is True

    def test_the_source_is_named(self):
        job = _running_job()
        assert self._payload(job)["memory"]["peak_source"] is None
        merged = _apply_live_metrics(
            job,
            {
                "1.batch": {
                    "max_rss": 473084 * 1024,
                    "ave_cpu": 291.0,
                    "ntasks": 1,
                    "max_rss_node": "",
                    "max_rss_task": "",
                    "ave_rss": None,
                    "max_vmsize": None,
                    "max_pages": None,
                },
            },
        )
        assert self._payload(merged)["memory"]["peak_source"] == "sstat (live)"

    def test_a_finished_job_reads_as_final(self):
        done = _running_job()._replace(
            state="COMPLETED",
            steps=tuple(s._replace(state="COMPLETED") for s in _running_job().steps),
        )
        payload = self._payload(done)
        assert payload["memory"]["peak_source"] == "sacct (final)"
        assert payload["memory"]["job_in_progress"] is False


# --------------------------------------------------------------------------
# SP-27 -- one object per distinct string
# --------------------------------------------------------------------------
class TestTheParserSharesRepeatedStrings:
    """A history is fully materialised and the records are mostly repeated text.

    Over 13,321 real jobs: ``uid`` and ``account`` each had **one** distinct
    value held as 13,321 separate string objects, ``state`` seven, ``flags``
    three, ``work_dir`` 35, ``req_tres`` 205 — 19.4 MB of string payload of which
    ~10 MB in the top fourteen fields alone was exact duplication, before the
    30,339 step rows repeated the same states and node names again.
    """

    @staticmethod
    def _rows(count):
        head = "|".join(sacctmod._FIELDS)
        lines = []
        for i in range(count):
            row = dict.fromkeys(sacctmod._FIELDS, "")
            row["JobID"] = str(1000 + i)
            row["State"] = "COMPLETED"
            row["User"] = "youzhi"
            row["Account"] = "rcc-staff"
            row["Partition"] = "caslake"
            row["WorkDir"] = "/home/youzhi/some/long/working/directory/path"
            row["ReqTRES"] = "billing=1,cpu=1,mem=2000M,node=1"
            row["Elapsed"] = "00:10:00"
            lines.append("|".join(row[f] for f in sacctmod._FIELDS))
        return head + "\n" + "\n".join(lines) + "\n"

    def test_a_repeated_value_is_one_object(self):
        jobs = sacctmod.parse(self._rows(200), delimiter="|")
        assert len(jobs) == 200
        for field in ("state", "user", "account", "partition", "work_dir", "req_tres"):
            objects = {id(getattr(j, field)) for j in jobs}
            assert len(objects) == 1, "%s: %d objects for one value" % (field, len(objects))

    def test_the_values_are_still_correct(self):
        jobs = sacctmod.parse(self._rows(5), delimiter="|")
        assert [j.job_id for j in jobs] == ["1000", "1001", "1002", "1003", "1004"]
        assert {j.account for j in jobs} == {"rcc-staff"}
        assert {j.work_dir for j in jobs} == {"/home/youzhi/some/long/working/directory/path"}

    def test_a_unique_value_is_not_shared_away(self):
        jobs = sacctmod.parse(self._rows(50), delimiter="|")
        assert len({j.job_id for j in jobs}) == 50, "distinct ids stay distinct"

    def test_the_cache_does_not_outlive_the_parse(self):
        """`sys.intern` would do this in one call and is the wrong tool.

        Its table is global and never freed, so a long-lived process -- the TUI
        reloading, or a library caller -- would accumulate every job id and
        timestamp it ever saw. A dict scoped to one parse is dropped when the
        parse ends, and the strings it shared stay shared for exactly as long as
        the records holding them.
        """
        first = sacctmod.parse(self._rows(10), delimiter="|")
        second = sacctmod.parse(self._rows(10), delimiter="|")
        # Same value, different parses: no sharing across them, which is the
        # property that makes the cache safe to drop.
        assert id(first[0].account) != id(second[0].account)

    def test_the_footprint_is_disclosed_on_a_large_window(self):
        from slurmpast import report as reportmod

        jobs = sacctmod.parse(self._rows(reportmod._FOOTPRINT_NOTE_ROWS + 10), delimiter="|")
        history = History(jobs, window="last 30 days")
        text = reportmod.render_overview(history, limit=1)
        # Nothing bounded this and nothing said so; what actually stopped users
        # hitting it was SLURMPAST_TIMEOUT failing on time first -- an
        # undocumented memory cap.
        # Flattened: the note is WRAPPED to the terminal now (round seventy-eight
        # -- it was 109 cells and went out at that length whatever the width), so
        # the advice can legitimately straddle a line break. What must hold is
        # that it is disclosed, not where the break falls.
        flat = " ".join(text.split())
        assert "rows, about" in flat
        assert "narrow the window with -S" in flat

    def test_an_ordinary_window_says_nothing_about_memory(self):
        from slurmpast import report as reportmod

        history = History(sacctmod.parse(self._rows(20), delimiter="|"), window="last 7 days")
        text = reportmod.render_overview(history, limit=1)
        assert "MiB held" not in text


# --------------------------------------------------------------------------
# SP-29 -- an empty sizing screen is not an all-clear
# --------------------------------------------------------------------------
class TestAnEmptySizingScreenSaysSo:
    """Round 34 filed the sizing screen's least-informed state being its most
    reassuring one, and 0.8.2 fixed it for two of the three cases.  The residual
    gap is the **zero-workload** case, which fell through to the green branch
    because both counters it tested were 0.
    """

    def test_an_empty_window_is_not_an_all_clear(self):
        text = render_sizing(History([], window="last 2 minutes"))
        assert "already about right" not in text
        assert "no finished runs" in text

    def test_a_named_running_job_names_itself(self):
        # The consequential way in: a RUNNING job is filtered out before the
        # counting and so registers as neither category. One at 94.5% of its
        # memory limit was told it was about right.
        history = History(
            [
                # `open_ended`, as `cli._mark_open_records` sets it on a RUNNING
                # record: that is what drops the job from the groups, and so what
                # made it register as neither "no data" nor "judged".
                _running_job()._replace(job_id="48853296", open_ended=True),
            ]
        )
        text = render_sizing(history)
        assert "already about right" not in text
        assert "48853296" in text
        assert "still running" in text

    def test_several_running_jobs_are_counted(self):
        history = History(
            [
                _running_job()._replace(job_id="1", open_ended=True),
                _running_job()._replace(job_id="2", open_ended=True),
            ]
        )
        text = render_sizing(history)
        assert "already about right" not in text
        assert "2 still running" in text

    def test_a_genuine_all_clear_is_still_green(self, monkeypatch):
        """The control: the green branch must still be REACHED, and say so.

        A screen that never says "about right" would have traded one wrong answer
        for another. This used to assert the sentence appears in
        ``inspect.getsource(render_sizing)``, which passes just as happily if the
        branch is unreachable dead code -- this suite's named recurring failure
        mode, a test that asserts less than it appears to.

        Reaching it needs ``shown == 0`` with ``shown_judged > 0`` and
        ``no_data_groups == 0``: a workload that WAS judged and left alone. So
        `recommend` is patched to return a non-actionable ``keep`` -- the verdict
        that means "judged, nothing to change" -- over a history that has groups.
        """
        import slurmpast.report as reportmod
        from slurmpast.sizing import Advice

        monkeypatch.setattr(
            reportmod,
            "recommend",
            lambda jobs: [
                Advice(
                    flag="--mem",
                    verdict="keep",
                    requested="50G",
                    observed="44G",
                    suggestion="",
                    basis="p95 of 9 completed runs is 44G",
                ),
            ],
        )
        history = History([_finished_job()])
        assert history.groups, "the green branch needs a group to have judged"
        text = render_sizing(history)
        assert "every workload is already about right." in text
        assert "no finished runs" not in text
        assert "still running" not in text


# --------------------------------------------------------------------------
# The sibling finding recorded alongside SP-28
# --------------------------------------------------------------------------
def test_an_unresolvable_name_is_named_as_a_cause():
    """`sacct -u <name>` fails on a compute node with no passwd entry.

    The advice sent the reader to check a `-u` argument they had not passed,
    about a name that *was* their login name. The real cause is that the node
    cannot resolve it, which is the ordinary state of a diskless compute node.
    """
    explained = sacctmod._explain("sacct: error: Invalid user id: youzhi")
    assert "Invalid user id" in explained, "the scheduler's own words are kept"
    assert "if you passed one" in explained
    assert "passwd" in explained
    assert "login node" in explained


# --------------------------------------------------------------------------
# SP-28 review, 2026-08-27 -- `sstat` is owner-only, and that is not a delay
# --------------------------------------------------------------------------
class TestAnotherUsersLiveJobIsNotAskedAbout:
    """`sstat` fails the exit-0 way, and asking costs real time.

    Measured on midway3 against another user's running jobs:

        $ sstat --allsteps --noheader --parsable2 --jobs=<3 foreign> ...
        sstat: error: slurm_job_step_stat: ... rc = Invalid user id
        rc=0,  empty stdout,  1,176 stderr lines

        20 foreign jobs  ->  wall 18.1 s,  7,840 `error:` lines

    The client contacts every node of every step, so the cost scales with the
    other user's job, not with the question. A `-u <someone-else>` report over a
    day timed out at 300 s inside that one call; `--all-users` over this
    cluster's 288 running jobs would pay it on every run.

    None of it ever reached the terminal -- `_run` pipes stderr and drops it on
    exit 0, which is how this failure exits -- so the symptom was wall-clock, not
    noise. The answer is known before the call: don't make it.
    """

    @staticmethod
    def _calls(jobs, me="youzhi", out=""):
        asked = []

        def _runner(args):
            asked.append(args)
            return out

        return asked, merge_live_metrics(jobs, runner=_runner, user=me)

    def test_a_foreign_live_job_is_not_queried(self):
        job = _running_job()._replace(job_id="1", user="emanakayama")
        asked, got = self._calls([job])
        assert asked == [], f"asked sstat about another user's job: {asked}"
        assert got[0].foreign_owner is True

    def test_my_own_live_job_is_still_queried(self):
        """The control, and the one that must not regress.

        This is SP-28 itself: without the `sstat` reading a running job's peak
        comes from whatever short-lived step happened to finish, which was a 210x
        understatement published as trustworthy.
        """
        job = _running_job()._replace(job_id="1", user="youzhi")
        asked, _got = self._calls([job])
        assert len(asked) == 1, asked
        assert "--jobs=1" in " ".join(asked[0])

    def test_an_unknown_owner_is_queried_not_assumed_foreign(self):
        # A narrow `--format` carries no User. Skipping on that would drop the
        # live reading on the reader's own job to save a call.
        job = _running_job()._replace(job_id="1", user="")
        asked, got = self._calls([job])
        assert len(asked) == 1, asked
        assert got[0].foreign_owner is False

    def test_a_uid_and_a_name_are_not_compared(self):
        """The no-name-service cluster, which is why `current_user` has fallbacks.

        There `current_user()` returns the numeric uid and `sacct` reports a
        name. They are unequal and that means nothing, so the comparison must
        decline rather than conclude.
        """
        job = _running_job()._replace(job_id="1", user="youzhi")
        asked, got = self._calls([job], me="940740146")
        assert len(asked) == 1, asked
        assert got[0].foreign_owner is False

    def test_a_mixed_set_asks_only_about_mine(self):
        jobs = [
            _running_job()._replace(job_id="1", user="youzhi"),
            _running_job()._replace(job_id="2", user="emanakayama"),
            _running_job()._replace(job_id="3", user="youzhi"),
        ]
        asked, got = self._calls(jobs)
        assert len(asked) == 1, asked
        joined = " ".join(asked[0])
        assert "--jobs=1,3" in joined, joined
        assert [j.foreign_owner for j in got] == [False, True, False]

    def test_a_finished_foreign_job_is_untouched(self):
        # The flag is about a live reading that cannot be taken. A finished job's
        # accounting is final and readable by anyone, so nothing is missing.
        done = _running_job()._replace(
            job_id="1", user="emanakayama", state="COMPLETED", live=False
        )
        asked, got = self._calls([done])
        assert asked == []
        assert got[0].foreign_owner is False

    def test_the_reason_is_reported_as_permission_not_timing(self):
        job = _running_job()._replace(job_id="1", user="emanakayama")
        _asked, got = self._calls([job])
        assert got[0].peak_unmeasurable_by_permission is True
        assert got[0].peak_is_live_reading is False

    def test_my_own_unanswered_job_is_still_a_timing_question(self):
        """The control on the disclosure.

        A job of mine that `sstat` had nothing for really may fill in -- it just
        ended, or the site runs no `jobacct_gather`. Calling that a permission
        problem would send the reader after an access issue they do not have.
        """
        job = _running_job()._replace(job_id="1", user="youzhi")
        _asked, got = self._calls([job], out="")
        assert got[0].peak_unmeasurable_by_permission is False

    def test_identity_failure_does_not_break_the_merge(self):
        """`current_user()` raises where it could not before.

        It is documented to raise `SacctError` once every fallback fails, and
        that path now runs inside `merge_live_metrics`. Not knowing who we are
        makes one optimisation unavailable, not the report impossible.
        """
        import slurmpast.sacct as sacctmod

        real = sacctmod.current_user
        sacctmod.current_user = lambda: (_ for _ in ()).throw(
            sacctmod.SacctError("no passwd entry, no SLURM_JOB_USER, no uid")
        )
        try:
            job = _running_job()._replace(job_id="1", user="emanakayama")
            asked = []

            def _runner(args):
                asked.append(args)
                return ""

            got = merge_live_metrics([job], runner=_runner)
        finally:
            sacctmod.current_user = real
        assert len(asked) == 1, "declined to ask rather than degrading gracefully"
        assert got[0].foreign_owner is False


class TestTheJsonNamesThePermissionCase:
    """The disclosure half of the same review point."""

    def _payload(self, job):
        from slurmpast.cli import _job_json
        from slurmpast.diagnose import diagnose

        return json.loads(json.dumps(_job_json(job, None, diagnose(job), no_logs=True)))

    def test_a_foreign_running_job_says_why_the_live_figure_is_absent(self):
        """A fourth state, because three collapsed two different facts.

        `sacct (unflushed)` on my own running job means "wait"; on somebody
        else's it means "never, for you". A reader comparing their own running job
        against a colleague's read one label and got one meaning.
        """
        # A figure on a LIVE step, which is the only way one exists without
        # `sstat`: `measured_steps` excludes a finished straggler while the job
        # runs, which is the SP-28 fix and must not be worked around here. Some
        # sites' `jobacct_gather` does report a running step's MaxRSS, and that is
        # the state `sacct (unflushed)` was written for.
        base = _running_job()
        job = base._replace(
            user="emanakayama",
            foreign_owner=True,
            steps=tuple(
                s._replace(max_rss=473084 * 1024) if s.in_progress else s for s in base.steps
            ),
        )
        payload = self._payload(job)
        assert payload["memory"]["peak_source"] == "sacct (unflushed, sstat is owner-only)"
        assert payload["memory"]["peak_trustworthy"] is False
        assert payload["memory"]["peak_unavailable_reason"] is None, (
            "there IS a figure here, so only its source is in question"
        )

    def test_my_own_unflushed_job_keeps_the_timing_wording(self):
        # The control: the existing state must stay reachable and stay itself.
        job = _running_job()._replace(user="youzhi")
        assert self._payload(job)["memory"]["peak_source"] is None, (
            "a running job's live steps carry no flushed MaxRSS, so there is no "
            "figure and hence no source -- this is the ordinary case"
        )
        assert self._payload(job)["memory"]["peak_unavailable_reason"] == "in_progress_unflushed"

    def test_the_no_figure_case_is_the_one_that_needed_explaining(self):
        """No figure at all, which is what a running job normally reports.

        `peak_source` is null here and always was; what was missing is any
        account of the null. For another user's job the answer is permission, and
        that is the state `--all-users` produces for the majority of live rows.
        """
        mine = _running_job()._replace(user="youzhi")
        theirs = _running_job()._replace(user="emanakayama", foreign_owner=True)
        assert self._payload(mine)["memory"]["peak_source"] is None
        assert self._payload(theirs)["memory"]["peak_source"] is None
        assert (
            self._payload(mine)["memory"]["peak_unavailable_reason"]
            != self._payload(theirs)["memory"]["peak_unavailable_reason"]
        )
        assert (
            self._payload(theirs)["memory"]["peak_unavailable_reason"]
            == "foreign_owner_sstat_is_owner_only"
        )

    def test_a_finished_job_with_no_figure_blames_neither(self):
        # The control: a site that runs no `jobacct_gather` has no MaxRSS for
        # anybody, and calling that a permission problem or a flush delay would
        # both be wrong.
        done = _running_job()._replace(
            state="COMPLETED",
            steps=tuple(s._replace(state="COMPLETED", max_rss=None) for s in _running_job().steps),
        )
        payload = self._payload(done)
        assert payload["memory"]["peak_source"] is None
        assert payload["memory"]["peak_unavailable_reason"] == "not_gathered"


class TestTheGaugeCaptionSaysWhichKindOfMissing:
    """The same distinction on the screen a reader actually looks at.

    `--all-users` and `-u <someone>` reach other people's running jobs as a
    matter of course, and for every one of them the memory gauge draws `n/a`. The
    caption is the only place that can say whether waiting would help.
    """

    @staticmethod
    def _caption(job):
        # `resource_rows` returns rich `Text`; `str()` is the rendered line.
        from slurmpast.render import resource_rows

        for line in resource_rows(job):
            text = str(line)
            if " MEM " in text:
                return text
        return ""

    def test_another_users_running_job_names_the_permission(self):
        job = _running_job()._replace(user="emanakayama", foreign_owner=True)
        caption = self._caption(job)
        assert "sstat cannot read another user's running job" in caption, caption
        assert "not yet flushed" not in caption, (
            "'not yet' promises a wait that will never end for this reader"
        )

    def test_my_own_running_job_still_reads_as_a_delay(self):
        # The control. For my own job the figure really may fill in, and sending
        # the reader after an access problem they do not have is a new wrong
        # answer rather than a downgraded one.
        job = _running_job()._replace(user="youzhi")
        caption = self._caption(job)
        assert "another user" not in caption, caption
        assert "flushes a step's peak only when the step ends" in caption, caption

    def test_a_live_reading_is_unchanged(self):
        # The SP-28 caption, which must survive all of this untouched.
        job = _apply_live_metrics(
            _running_job()._replace(user="youzhi"),
            {
                "1.batch": {
                    "max_rss": 473084 * 1024,
                    "ave_cpu": 291.0,
                    "ntasks": 1,
                    "max_rss_node": "",
                    "max_rss_task": "",
                    "ave_rss": None,
                    "max_vmsize": None,
                    "max_pages": None,
                },
            },
        )
        caption = self._caption(job)
        assert caption.endswith("so far"), caption


def test_the_owner_test_uses_the_reader_not_the_queried_user():
    """`-u <someone-else>` means "show me their jobs", not "I am them".

    The permissions that decide whether `sstat` can answer are the invoking
    user's. Passing the `-u` argument here instead would conclude that a foreign
    job belongs to the reader and query it after all -- the 18-second call the
    skip exists to avoid, restored by a plausible-looking simplification.
    """
    asked = []

    def _runner(args):
        asked.append(args)
        return ""

    job = _running_job()._replace(job_id="1", user="emanakayama")
    # `user=` is the reader. Their own name, while reading someone else's history.
    got = merge_live_metrics([job], runner=_runner, user="youzhi")
    assert asked == [], asked
    assert got[0].foreign_owner is True


class TestARejectedTimeSpecSaysWhichSpellingsWork:
    """Polish pass, 2026-08-28: `-S` failed with sacct's raw text and nothing else.

        $ slurmpast -S notadate
        slurmpast: Invalid time specification (pos=0): notadate

    A byte offset into a string the user often did not type in that form --
    `-6months` is rewritten to `now-6months` by `normalize_time_spec` first, so
    `pos=4` points into slurmpast's own edit -- and no word about which spellings
    work. `-S` is this tool's most-used option.

    The knowledge was already in the repo: `tui.WINDOWS` carries the verified set
    and a comment recording that `now-6months` and `now-1year` are refused while
    every day/week spec returns rows. It just never reached the user at the moment
    they needed it.
    """

    def test_the_hint_fires_on_sacct_s_own_wording(self):
        from slurmpast.sacct import _explain

        out = _explain("Invalid time specification (pos=0): notadate")
        assert "now-7days" in out
        assert "NOT months or years" in out
        # The scheduler's own text is kept: it carries the offending value.
        assert "notadate" in out

    def test_every_window_the_tui_offers_is_named_in_the_advice(self):
        """The advice and the working set are one fact, so they cannot diverge.

        If a window is added to the cycle, this fails until the advice names it --
        which is the point: the two lists are the same knowledge.
        """
        from slurmpast.sacct import _explain
        from slurmpast.tui import WINDOWS

        advice = _explain("invalid time specification (pos=0): x")
        missing = [w for w in WINDOWS if w not in advice]
        assert not missing, f"the advice omits {missing}, which the TUI offers"

    def test_it_does_not_promise_a_unit_sacct_refuses(self):
        """The advice must not list months, and must say they are refused.

        Verified against Slurm 20.11.8 on the reporting cluster: `now-6months`,
        `now-2months` and `now-1year` are all `Invalid time specification`.
        """
        import re

        from slurmpast.sacct import _explain

        advice = _explain("invalid time specification (pos=0): x")
        offered = re.findall(r"`(now-[^`]+)`", advice)
        assert offered, advice
        bad = [o for o in offered if "month" in o or "year" in o]
        # `now-6months` may appear only as the counter-example.
        assert bad == ["now-6months"], bad
        assert "is rejected" in advice

    def test_an_unrelated_sacct_error_is_not_given_time_advice(self):
        # The control: `_HINTS` matches on wording, so a broadened marker would
        # start attaching window advice to failures that have nothing to do with
        # the window.
        from slurmpast.sacct import _explain

        for message in (
            "Invalid user id: youzhi",
            "sacct: error: Problem talking to the database",
            "accounting_storage/none is configured",
        ):
            assert "now-7days" not in _explain(message), message


class TestADroppedFlagIsReported:
    """Polish pass, 2026-08-28: `--no-logs --log-dir X` dropped `--log-dir` silently.

    `--all-users -u you` has been refused since round eighteen ("ask for different
    things; pick one") and the sibling package warns for the no-effect shape
    ("--append has no effect without --log; ignoring"). This combination had
    neither: `--no-logs` won and the extra search directories vanished.

    `--demo` is the same case by a different route -- it sets `no_logs` itself, for
    reasons recorded at that line -- so `--demo --log-dir X` was equally silent.

    A warning, not an error: `--no-logs` is an unambiguous off switch, so there is
    a clear winner. And not silent, unlike the `--plain` degrade a few lines below,
    which is silent *because* `--plain` carries the same information.
    """

    @staticmethod
    def _stderr(*args):
        import os
        import pathlib
        import subprocess
        import sys

        root = pathlib.Path(__file__).resolve().parent.parent
        done = subprocess.run(
            [sys.executable, "-m", "slurmpast", *args, "-n", "1"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(root),
            env={
                **os.environ,
                "PYTHONPATH": str(root / "src"),
                "PYTHONDONTWRITEBYTECODE": "1",
                "NO_COLOR": "1",
                "COLUMNS": "200",
            },
        )
        return done.returncode, done.stderr

    def test_no_logs_with_log_dir_says_which_flag_was_dropped(self):
        rc, err = self._stderr("--no-logs", "--log-dir", "/tmp")
        assert "--log-dir has no effect with --no-logs" in err, err
        # And which directory was discarded, so the reader can tell it was theirs.
        assert "/tmp" in err
        # A warning, not a failure -- stated as "the dropped flag changed nothing",
        # because that is the actual claim. Asserting `rc == 0` outright made this
        # test a hostage to the caller's own job history: the exit code carries the
        # REPORT's verdict (`return 1 if worst_critical else 0`, `cli.py`), so on a
        # week holding a critical finding it is 1 for reasons that have nothing to
        # do with flag handling. It passed for weeks and then went red on a quiet
        # Thursday. Measured here: 186 jobs in the default window, rc=1 with no
        # flags at all, the full report rendered correctly above it.
        baseline, _ = self._stderr("--no-logs")
        assert rc == baseline, (rc, baseline)

    def test_demo_names_itself_rather_than_no_logs(self):
        """`--demo` sets `no_logs` internally, so naming `--no-logs` would puzzle.

        The user did not pass it; blaming a flag they never typed is the same
        misdirection as saying nothing.
        """
        _rc, err = self._stderr("--demo", "--log-dir", "/tmp")
        assert "--log-dir has no effect with --demo" in err, err
        assert "--no-logs" not in err, err

    @pytest.mark.parametrize("argv", [["--log-dir", "/tmp"], ["--no-logs"]])
    def test_either_flag_alone_is_silent(self, argv):
        # The control: this reports a combination, not either flag.
        _rc, err = self._stderr(*argv)
        assert "no effect" not in err, err


class TestAnEmptyIdentityIsRefused:
    """Polish pass, 2026-08-28: `-u ''` reported the caller's own history.

    Output identical to passing no `-u` at all, at rc=0. A script doing
    `-u "$WHO"` with `WHO` unset therefore reported the *caller's* jobs under
    someone else's name, confidently.

    That is the failure `--all-users and -u/--user ask for different things`
    already guards, arriving by a different route: the report is scoped to
    something the reader did not ask for and nothing on screen says so. The
    original comment makes the argument in full -- "silently letting one win means
    the output is scoped to something the reader did not ask for" -- so this is the
    same rule applied to the spelling a shell produces by accident.
    """

    @staticmethod
    def _run(*args):
        import os
        import pathlib
        import subprocess
        import sys

        root = pathlib.Path(__file__).resolve().parent.parent
        return subprocess.run(
            [sys.executable, "-m", "slurmpast", *args, "-n", "1", "--plain"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(root),
            env={
                **os.environ,
                "PYTHONPATH": str(root / "src"),
                "PYTHONDONTWRITEBYTECODE": "1",
                "NO_COLOR": "1",
                "COLUMNS": "200",
            },
        )

    @pytest.mark.parametrize(
        "flag,named",
        [
            ("-u", "-u/--user"),
            ("--user", "-u/--user"),
            ("-p", "-p/--partition"),
            ("--partition", "-p/--partition"),
        ],
    )
    @pytest.mark.parametrize("value", ["", "   "])
    def test_an_empty_value_is_refused(self, flag, named, value):
        done = self._run(flag, value)
        assert done.returncode == 2, done.stdout + done.stderr
        assert named in done.stderr, done.stderr
        # Both readings are offered, since either may be what was meant.
        assert "drop the flag" in done.stderr
        assert "variable you passed" in done.stderr

    def test_all_users_is_named_as_the_other_way_out(self):
        # `-u` defaults to "yours", so "everyone" needs its own flag mentioned.
        assert "--all-users" in self._run("-u", "").stderr

    @pytest.mark.parametrize("which", ["user", "partition", "neither"])
    def test_a_real_value_and_an_absent_flag_are_untouched(self, which):
        """The control: omitting the flag must stay the way to say "the default".

        The fix would be worse than the defect if it forced a value on anyone who
        simply wanted their own history.

        Run against `--demo`, on the tape's OWN user and partition read out of
        `demo.history()`. The first version queried the live scheduler with
        `-u youzhi -p amd` and asserted `rc in (0, 1)`: those are this cluster's
        names, and anywhere Slurm is absent the run is rc=2 with "cannot execute
        sacct", so the control passed on the machine it was written on and
        reddened every runner. The empty-value check runs *before* the
        `args.demo` branch in `_main` -- pinned by the next test -- so `--demo`
        reaches the same code with no scheduler in the picture, and reading the
        values keeps a hardcoded `youzhi` from looking like a login again when
        it is in fact the synthetic user.
        """
        from slurmpast.demo import history

        jobs = list(history())
        argv = {
            "user": ["-u", sorted({job.user for job in jobs})[0]],
            "partition": ["-p", sorted({job.partition for job in jobs})[0]],
            "neither": [],
        }[which]
        done = self._run("--demo", *argv)
        # 1 is "something was flagged", which the tape always has; either way the
        # run reported rather than refusing.
        assert done.returncode in (0, 1), done.stdout + done.stderr
        assert "empty value" not in done.stderr, done.stderr

    @pytest.mark.parametrize("flag", ["-u", "--user", "-p", "--partition"])
    def test_demo_does_not_get_a_free_pass(self, flag):
        """Why the control above may use `--demo`: it is not a way round the check.

        Without this, `--demo` could stop reaching the validation and the control
        would keep passing while asserting nothing.
        """
        done = self._run("--demo", flag, "")
        assert done.returncode == 2, done.stdout + done.stderr
        assert "empty value" in done.stderr, done.stderr


class TestCtrlCIsNotACrash:
    """Polish pass, 2026-08-28: SIGINT escaped as a traceback out of `communicate`.

    This tool is the likeliest of the five to be interrupted, and the reason is a
    deliberate design choice rather than a defect: its query timeout is **300 s**,
    because an accounting database can genuinely take minutes, where the siblings
    bound a live-controller call at 30-45 s. Five minutes of silence is exactly
    when a user reaches for Ctrl-C -- and what they got was a `KeyboardInterrupt`
    traceback, which reads as a crash in a run they were cancelling on purpose.

    Three of the five already exited cleanly here.
    """

    @staticmethod
    def _interrupt(argv, wait=4.0):
        import os
        import pathlib
        import signal
        import subprocess
        import sys
        import tempfile
        import time

        root = pathlib.Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            fake = pathlib.Path(tmp) / "bin"
            fake.mkdir()
            for name in ("sacct", "sacctmgr", "squeue", "scontrol", "sstat", "sinfo"):
                stub = fake / name
                stub.write_text("#!/bin/bash\nsleep 300\n")
                stub.chmod(0o755)
            proc = subprocess.Popen(
                [sys.executable, "-m", "slurmpast", *argv],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=tmp,
                env={
                    "PATH": f"{fake}:/usr/bin:/bin",
                    "HOME": os.environ.get("HOME", tmp),
                    "PYTHONPATH": str(root / "src"),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "NO_COLOR": "1",
                    "COLUMNS": "200",
                },
            )
            time.sleep(wait)
            proc.send_signal(signal.SIGINT)
            try:
                _out, err = proc.communicate(timeout=60)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                pytest.fail("SIGINT did not stop it")
            return proc.returncode, err

    def test_it_exits_130_without_a_traceback(self):
        rc, err = self._interrupt(["--plain", "-n", "1"])
        assert "Traceback" not in err, err[-400:]
        assert "KeyboardInterrupt" not in err, err[-400:]
        assert rc == 130, f"rc={rc}, stderr={err[-200:]}"

    def test_main_is_a_wrapper_so_the_installed_script_is_covered(self):
        """`__main__.py` is not the only entry point.

        `pyproject` installs `main` as the console script, so catching the
        interrupt in `__main__.py` would leave the installed `slurmpast` command --
        the one everyone actually runs -- still printing a traceback.
        """
        import inspect

        from slurmpast.cli import main

        assert "KeyboardInterrupt" in inspect.getsource(main)


class TestAFailedClipWriteReportsItsOwnError:
    """Polish pass, 2026-08-28: a double close replaced the real error with EBADF.

    `os.fdopen` takes ownership of the descriptor, so the `with` closes it. The
    `except BaseException: os.close(fd)` wrapped the write as well, and closed it
    a second time -- and that second close raised, replacing whatever had actually
    gone wrong. Measured under `RLIMIT_FSIZE`:

        raised:  OSError: [Errno 9] Bad file descriptor
        masking: OSError: [Errno 27] File too large

    A full filesystem and an exceeded quota are the two reasons this fails on a
    cluster, and both arrived as "Bad file descriptor", which points nowhere. The
    guard now covers only the window in which the descriptor is still ours.
    """

    @staticmethod
    def _write_with_size_cap(target, size, cap=4096):
        """Call `_write_clip` in a child with RLIMIT_FSIZE, returning the error."""
        import os
        import pathlib
        import subprocess
        import sys

        root = pathlib.Path(__file__).resolve().parent.parent
        code = (
            "import resource, sys\n"
            f"resource.setrlimit(resource.RLIMIT_FSIZE, ({cap}, {cap}))\n"
            "from slurmpast.tui import _write_clip\n"
            "try:\n"
            f"    _write_clip(sys.argv[1], 'x' * {size})\n"
            "except BaseException as exc:\n"
            "    print(type(exc).__name__, getattr(exc, 'errno', ''), exc)\n"
            "else:\n"
            "    print('no error')\n"
        )
        done = subprocess.run(
            [sys.executable, "-c", code, str(target)],
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "PYTHONPATH": str(root / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
        )
        return done.stdout.strip(), done.stderr

    def test_the_real_errno_survives(self, tmp_path):
        import errno

        said, err = self._write_with_size_cap(tmp_path / "clip.txt", 200_000)
        assert "OSError" in said, said + err
        assert str(errno.EFBIG) in said, f"expected EFBIG, got: {said}"
        assert str(errno.EBADF) not in said, f"the double close is back: {said}"

    def test_a_normal_write_is_unaffected(self, tmp_path):
        # The control: the descriptor still has to be closed exactly once on the
        # success path, and the mode still has to be tightened.
        import os

        from slurmpast.tui import _write_clip

        target = tmp_path / "clip.txt"
        _write_clip(str(target), "hello")
        assert target.read_text() == "hello\n"
        assert oct(os.stat(target).st_mode & 0o777) == "0o600"

    def test_an_existing_loose_file_is_still_tightened(self, tmp_path):
        """The reason `fchmod` is there at all, per the function's own docstring.

        `os.open`'s mode applies only on creation, so an upgrade path with a
        world-readable `clip.txt` already on disk needs the explicit chmod.
        """
        import os

        from slurmpast.tui import _write_clip

        target = tmp_path / "clip.txt"
        target.write_text("old")
        os.chmod(target, 0o644)
        _write_clip(str(target), "new")
        assert oct(os.stat(target).st_mode & 0o777) == "0o600"


class TestASignalledDashboardRestoresTheTerminal:
    """Polish pass, 2026-08-28: SIGTERM and SIGHUP left the alternate screen open.

    Measured by driving the dashboard in a real pty and counting the escape
    sequences it emitted:

        q         exit=0    altscreen 1/1   restored
        SIGINT    exit=0    altscreen 1/1   restored
        SIGTERM   killed    altscreen 1/0   ** terminal left dirty **
        SIGHUP    killed    altscreen 1/0   ** terminal left dirty **

    "Dirty" means the user's scrollback is replaced by a dead dashboard until they
    run `reset`. Both signals are ordinary: slurmstepd SIGTERMs the step when a job
    running `srun --pty slurmpast` is cancelled, and a tmux pane being killed or an
    IDE terminal closing SIGHUPs the foreground group.

    SIGINT was already clean on screen but exited **0**, so `kill -INT` and a clean
    `q` were indistinguishable to a supervisor. The sibling package reached the same
    three handlers by the same route (its SW-26).
    """

    @staticmethod
    def _drive(signame=None, wait=12.0):
        """Run the dashboard in a pty, optionally signal it, and report.

        Driven with `--demo`, which is the only spelling that has a dashboard to
        signal everywhere. Without it the child needs a live `sacct`: on a host
        that has none it enters the alternate screen, the load fails, and
        `tui.run` returns the load error's 2 before any signal arrives --
        measured on this tree with Slurm stripped from PATH, `SIGHUP` reported
        `{'code': 2, 'entered': 1, 'left': 1}` against an expected 129 and the
        other three could not find a live process to wait for at all. The tape
        needs no scheduler and renders identically on a login node and a runner,
        so the signal is the only variable left.
        """
        import contextlib
        import os
        import pathlib
        import pty
        import select
        import signal as sig
        import sys
        import time

        root = pathlib.Path(__file__).resolve().parent.parent
        pid, fd = pty.fork()
        if pid == 0:  # pragma: no cover - the child execs immediately
            os.environ.update(
                {
                    "PYTHONPATH": str(root / "src"),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "TERM": "xterm-256color",
                    "COLUMNS": "120",
                    "LINES": "40",
                }
            )
            os.chdir(str(root))
            os.execv(sys.executable, [sys.executable, "-m", "slurmpast", "--demo"])

        out = bytearray()

        def pump(seconds):
            end = time.time() + seconds
            while time.time() < end:
                ready, _, _ = select.select([fd], [], [], 0.3)
                if not ready:
                    continue
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    return
                if not chunk:
                    return
                out.extend(chunk)

        pump(wait)
        if signame is None:
            with contextlib.suppress(OSError):
                os.write(fd, b"q")
        else:
            os.kill(pid, getattr(sig, f"SIG{signame}"))
        pump(6)

        # Bounded by the CLOCK, not by an iteration count. `pump` returns the
        # moment the pty master reports EIO, which happens when the child closes
        # the slave -- measured at 0.22 s after the signal, while the child is
        # reaped at 0.42 s. So `for _ in range(40): pump(0.4)` did not wait 16
        # seconds, it spun 40 times in microseconds and then declared a hang:
        # 2 failures in 3 runs, "the dashboard did not exit", and never the same
        # signal twice. The sleep paces the poll once the stream is at EOF; the
        # 45 s is 75x the worst exit measured here and still finite, because a
        # blocking `waitpid` in a suite with no global timeout is a wedged CI job
        # rather than a failing test.
        status = None
        deadline = time.time() + 45
        while time.time() < deadline:
            done, st = os.waitpid(pid, os.WNOHANG)
            if done:
                status = st
                break
            pump(0.3)
            time.sleep(0.05)
        if status is None:  # pragma: no cover - only on a hang
            os.kill(pid, sig.SIGKILL)
            os.waitpid(pid, 0)
            pytest.fail("the dashboard did not exit")
        text = out.decode("utf-8", "replace")
        return {
            "signalled": os.WIFSIGNALED(status),
            "code": None if os.WIFSIGNALED(status) else os.waitstatus_to_exitcode(status),
            "entered": text.count("\x1b[?1049h"),
            "left": text.count("\x1b[?1049l"),
            "traceback": "Traceback" in text,
        }

    @pytest.mark.parametrize(
        "signame,expected",
        [
            ("TERM", 143),
            ("HUP", 129),
            ("INT", 130),
        ],
    )
    def test_the_terminal_is_restored_and_the_code_says_signalled(self, signame, expected):
        got = self._drive(signame)
        if got["entered"] == 0:
            pytest.skip("the dashboard never reached the alternate screen here")
        assert not got["signalled"], f"killed by the signal instead of handling it: {got}"
        assert got["left"] == got["entered"], f"alternate screen left open: {got}"
        assert not got["traceback"], got
        assert got["code"] == expected, got

    def test_a_clean_quit_is_still_zero(self):
        """The control: signalling must not make an ordinary `q` look signalled."""
        got = self._drive(None)
        if got["entered"] == 0:
            pytest.skip("the dashboard never reached the alternate screen here")
        assert got["left"] == got["entered"], got
        assert got["code"] == 0, got

    def test_a_load_failure_still_outranks_a_signal_code(self):
        """`load_error` is 2 and must win: no data is what a script needs first."""
        import inspect

        from slurmpast import tui

        source = inspect.getsource(tui.run)
        assert source.index("load_error") < source.index("app.return_code")


def _drive_in_a_pty(argv, ready, signame, settle=40.0, budget=45.0):
    """Run `argv` in a real pty, signal it once `ready` has been written, report.

    Shared by the two tests below, which differ only in what they run and what
    they wait for.

    **The parent holds a second fd on the slave end for the whole run.** EOF on a
    pty master means the last slave fd is gone, and the kernel is free to drop
    whatever is still queued at that moment -- while both children here write
    their last bytes and then `os._exit` microseconds later. Holding the slave
    keeps the queue alive until the child has been reaped, and it is closed only
    then, which is what ends the drain. Nothing measured here was ever *traced*
    to that discard (the loss that looked like it was `sys.stdout` being
    redirected, fixed in `tui.py`), but a harness whose result depends on which
    of two microseconds wins is not one to assert on: this removes the channel
    rather than reasoning about it.

    Returns the decoded output, whether the child was killed by the signal, and
    its exit code -- everything the callers assert on, and nothing about how the
    bytes were collected.
    """
    import contextlib
    import fcntl
    import os
    import pathlib as _pathlib
    import pty
    import select
    import signal
    import sys
    import termios
    import time

    root = _pathlib.Path(__file__).resolve().parent.parent
    # `pty.openpty` + `fork` rather than `pty.fork`, which closes the slave in the
    # parent and leaves no way to hold it. (`os.ptsname`, which would let the
    # parent re-open it, is 3.13+ and this package's floor is 3.10.) The child
    # then does for itself what `pty.fork` would have done: new session, the pty
    # as its controlling terminal, the three standard fds on the slave.
    fd, slave = pty.openpty()
    pid = os.fork()
    if pid == 0:  # pragma: no cover - the child execs immediately
        os.setsid()
        with contextlib.suppress(OSError, AttributeError):
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
        for target in (0, 1, 2):
            os.dup2(slave, target)
        if slave > 2:
            os.close(slave)
        os.close(fd)
        os.environ.update(
            {
                "PYTHONPATH": str(root / "src"),
                "PYTHONDONTWRITEBYTECODE": "1",
                "TERM": "xterm-256color",
                "COLUMNS": "120",
                "LINES": "40",
            }
        )
        os.chdir(str(root))
        os.execv(sys.executable, [sys.executable, *argv])
        os._exit(127)  # only reached if the exec itself failed

    seen = bytearray()

    def read_some(timeout):
        readable, _, _ = select.select([fd], [], [], timeout)
        if not readable:
            return True
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            return False
        if not chunk:
            return False
        seen.extend(chunk)
        return True

    try:
        deadline = time.time() + settle
        while time.time() < deadline and ready not in seen:
            if not read_some(0.05):
                break
        arrived = ready in seen
        os.kill(pid, getattr(signal, f"SIG{signame}"))
        # Read WHILE waiting rather than after: a pty's queue is a few KB and a
        # dashboard tearing down writes a screenful, so a reader that waited
        # first could wedge the writer it is waiting for -- and with the slave
        # held open there is no EOF to end a read-then-wait loop anyway. Bounded
        # by the clock, because a blocking `waitpid` in a suite with no global
        # timeout is a wedged CI job rather than a failing test.
        signalled = code = None
        deadline = time.time() + budget
        while time.time() < deadline:
            read_some(0.1)
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                signalled = os.WIFSIGNALED(status)
                code = None if signalled else os.waitstatus_to_exitcode(status)
                break
        if signalled is None:  # pragma: no cover - only on a hang
            os.kill(pid, signal.SIGKILL)
            with contextlib.suppress(ChildProcessError):
                os.waitpid(pid, 0)
    finally:
        # The child is gone, so the parent's is the last slave fd: closing it is
        # what turns the next read into the EOF that ends the drain, and the
        # bytes written on the way out are still queued behind it.
        os.close(slave)
    end = time.time() + 5
    while time.time() < end and read_some(0.2):
        pass
    os.close(fd)
    return {
        "ready": arrived,
        "text": seen.decode("utf-8", "replace"),
        "signalled": signalled,
        "code": code,
    }


#: A stand-in for what Textual leaves in `sys.stdout` while the app is running: a
#: capture whose `write` queues into the app rather than reaching the terminal,
#: and whose `isatty()` still answers True. Run as `python -c` in a pty by
#: `test_a_redirected_stdout_does_not_swallow_the_restore`; the marker goes
#: straight to the descriptor so the parent can tell when to signal without
#: going through the object under test.
_REDIRECTED_CHILD = """
import os, sys, time
sys.path.insert(0, %r)
from slurmpast.tui import _guard_startup_window


class Capture:
    def write(self, text):
        return len(text)

    def flush(self):
        pass

    def isatty(self):
        return True


with _guard_startup_window():
    sys.stdout = Capture()
    sys.stderr = Capture()
    os.write(1, b"READY")
    time.sleep(30)
"""


class TestASignalInTheStartupWindowStillRestores:
    """The gap before `on_mount` installs the app's own handlers.

    Round 81's fix handles SIGTERM/SIGHUP/SIGINT in `on_mount`, which covers a
    *running* dashboard. It does not cover getting there. Textual writes the
    alternate-screen sequence as its very FIRST output — at the moment it appears
    only 8 bytes have been emitted, i.e. just that sequence — and `on_mount` runs a
    moment later:

        without `_guard_startup_window`   4/4  killed by signal, screen left open
        with it                           4/4  exit 143, screen restored

    A cancel racing startup is exactly when this window is open, and the sibling
    package had the same gap for the same reason: its `_TerminalGuard` existed but
    had only ever been applied to its two hop paths.
    """

    @staticmethod
    def _drive(signame):
        """The dashboard itself, signalled at the alternate-screen sequence.

        `--demo`, so there is a dashboard to signal on a host with no scheduler:
        without it the child needs a live `sacct` and races us to exit on its own
        load error, so the signal lands on whatever is left rather than on a
        dashboard in its startup window.
        """
        got = _drive_in_a_pty(["-m", "slurmpast", "--demo"], b"\x1b[?1049h", signame)
        return {
            "opened": got["text"].count("\x1b[?1049h"),
            "closed": got["text"].count("\x1b[?1049l"),
            "signalled": got["signalled"],
            "code": got["code"],
        }

    @pytest.mark.parametrize("signame,expected", [("TERM", 143), ("HUP", 129)])
    def test_the_screen_is_restored_and_the_code_matches_post_mount(self, signame, expected):
        got = self._drive(signame)
        if not got["opened"]:
            pytest.skip("the dashboard never reached the alternate screen here")
        assert got["signalled"] is False, (
            f"the default disposition still applied — the startup window is open: {got}"
        )
        assert got["closed"] >= got["opened"], f"screen left open: {got}"
        # The same codes the post-mount handlers report, so a supervisor sees one
        # story either side of the window.
        assert got["code"] == expected, got

    @pytest.mark.parametrize("signame,expected", [("TERM", 143), ("HUP", 129)])
    def test_a_redirected_stdout_does_not_swallow_the_restore(self, signame, expected):
        """The window is exactly when Textual takes `sys.stdout` away.

        Found because the test above failed **1 run in 5** with
        `{'opened': 1, 'closed': 0, 'code': 143}` — the exit code proving the
        handler had run while the capture said the screen was never restored.
        The cause was not the pty: `_restore_and_die` wrote the restore sequence
        through `sys.stdout`, and Textual replaces both streams with capture
        objects at about the moment it emits the alternate-screen sequence. Their
        `write` queues into the app and their `isatty()` still answers True, so
        the guard picked one, wrote into it, and `os._exit` a microsecond later
        dropped the queue. Whether the signal beat the redirect decided it, which
        is why the real dashboard shows it only sometimes.

        Arranged here instead, so it is deterministic: the child installs the real
        guard and then puts a stand-in capture in both streams. Measured against
        the stream version of the handler, this reports the restore missing 2/2,
        and 0/2 with the descriptor version — which is the neuter this test
        exists to keep red.
        """
        import pathlib

        src = str(pathlib.Path(__file__).resolve().parent.parent / "src")
        got = _drive_in_a_pty(["-c", _REDIRECTED_CHILD % (src,)], b"READY", signame)
        assert got["ready"], got
        assert got["signalled"] is False, got
        assert got["code"] == expected, got
        assert "\x1b[?1049l" in got["text"], (
            "the restore never reached the terminal: the handler wrote it into "
            f"the capture that had replaced sys.stdout. {got}"
        )

    def test_control_an_unredirected_child_is_restored_too(self):
        """CONTROL. Same child, streams left alone, so it holds either way.

        Verified by running it against the stream version of the handler: with
        nothing redirected `sys.stdout` IS the terminal and the restore arrives,
        which is precisely why the defect above could hide.
        """
        child = _REDIRECTED_CHILD.replace("sys.stdout = Capture()", "pass").replace(
            "sys.stderr = Capture()", "pass"
        )
        import pathlib

        src = str(pathlib.Path(__file__).resolve().parent.parent / "src")
        got = _drive_in_a_pty(["-c", child % (src,)], b"READY", "TERM")
        assert got["ready"], got
        assert got["code"] == 143, got
        assert "\x1b[?1049l" in got["text"], got

    def test_the_handlers_are_removed_afterwards(self):
        """A dashboard that could not start falls through to the caller.

        Leaving our handlers installed would make everything after `run()` exit via
        `os._exit`, skipping the clip-file cleanup that `run`'s own `finally` does.
        """
        import signal

        from slurmpast.tui import _guard_startup_window

        before = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP)}
        with _guard_startup_window():
            inside = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP)}
        after = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP)}
        assert inside != before, "the handlers were never installed"
        assert after == before, "the handlers outlived the dashboard"
