"""The wide field extraction and the diagnostics it unlocks.

Slurm 20.11 exposes 107 accounting fields. Everything measured here was
invisible to the first version of this tool, which requested 27 -- most
consequentially the *write* half of disk traffic (one real run read 112 GB and
wrote 139 GB, and only the read was reported).
"""

import pytest

from slurmpast.diagnose import diagnose
from slurmpast.sacct import parse
from tests.conftest import row


def codes(job, **kw):
    return {f.code for f in diagnose(job, **kw).findings}


def find(job, code, **kw):
    for f in diagnose(job, **kw).findings:
        if f.code == code:
            return f
    return None


def build(alloc=None, batch=None):
    """One allocation plus its .batch step, built by field name.

    The defaults describe a *healthy* job -- 50 GiB peak against a 64 GiB limit,
    4h of CPU on 8 cores, 4% system time -- so any finding a test sees is caused
    by the override it passed, not by the fixture.
    """
    alloc_fields = {
        "JobID": "900",
        "JobName": "w",
        "Partition": "test",
        "State": "COMPLETED",
        "ExitCode": "0:0",
        "Start": "2026-01-01T00:00:00",
        "End": "2026-01-01T01:00:00",
        "ElapsedRaw": "3600",
        "Elapsed": "01:00:00",
        "TimelimitRaw": "120",
        "AllocTRES": "billing=8,cpu=8,mem=64G,node=1",
        "AllocCPUS": "8",
        "NCPUS": "8",
        "NNodes": "1",
        "NodeList": "midway3-0600",
    }
    batch_fields = {
        "JobID": "900.batch",
        "JobName": "batch",
        "State": "COMPLETED",
        "ElapsedRaw": "3600",
        "CPUTimeRAW": "28800",
        "TotalCPU": "04:00:00",
        "UserCPU": "03:50:00",
        "SystemCPU": "10:00.000",
        "MaxRSS": "%dK" % (50 * 1024**2),
    }
    alloc_fields.update(alloc or {})
    batch_fields.update(batch or {})
    return parse("\n".join([row(**alloc_fields), row(**batch_fields)]))[0]


class TestRawSecondsPreferred:
    """``ElapsedRaw``/``CPUTimeRAW`` are integer seconds and remove the
    ``MM:SS.mmm`` vs ``HH:MM:SS`` ambiguity outright."""

    def test_elapsed_raw_wins_over_formatted(self):
        job = build(alloc={"ElapsedRaw": "3600", "Elapsed": "99:99:99"})
        assert job.elapsed == 3600.0

    def test_falls_back_to_formatted_when_raw_absent(self):
        job = build(alloc={"ElapsedRaw": "", "Elapsed": "01:00:00"})
        assert job.elapsed == 3600.0

    def test_timelimit_raw_is_minutes_not_seconds(self):
        """The one *Raw field with different units. 120 -> 2 hours, not 2 minutes."""
        assert build(alloc={"TimelimitRaw": "120"}).timelimit == 7200.0


class TestCpuSplit:
    def test_user_and_system_captured(self):
        job = build()
        assert job.user_cpu == pytest.approx(3 * 3600 + 50 * 60)
        assert job.system_cpu == pytest.approx(600.0)

    def test_system_fraction(self):
        assert build().system_cpu_fraction == pytest.approx(600.0 / 14400.0)

    def test_healthy_split_is_not_flagged(self):
        """A real training run measures ~4.7% system time."""
        assert "system-cpu-heavy" not in codes(build())

    def test_kernel_heavy_job_flagged(self):
        job = build(batch={"TotalCPU": "01:00:00", "SystemCPU": "00:45:00"})
        assert "system-cpu-heavy" in codes(job)

    def test_kernel_rule_silent_on_trivial_cpu(self):
        """A ratio over 3 seconds of CPU means nothing."""
        job = build(batch={"TotalCPU": "00:00:03", "SystemCPU": "00:00:02"})
        assert "system-cpu-heavy" not in codes(job)

    def test_cpu_frequency_captured(self):
        assert build(batch={"AveCPUFreq": "2.17M"}).cpu_freq == "2.17M"


class TestCoresBusy:
    """Reported as "what is cpu%? is it memory usage or cpu core usage?" -- a
    percentage with no named denominator does not say what it measures."""

    def test_cores_busy_is_utilization_times_the_allocation(self):
        job = build()
        assert job.cores_busy == pytest.approx(job.cpu_utilization * job.cpu_count)

    def test_it_reads_as_cores_of_cores(self):
        from slurmpast.render import cores_text

        text = cores_text(build())
        assert " of " in text
        assert text.split(" of ")[1] == str(build().cpu_count)

    def test_unmeasurable_is_n_a_never_zero(self):
        from slurmpast.model import Job
        from slurmpast.render import cores_text

        assert Job(job_id="1").cores_busy is None
        assert cores_text(Job(job_id="1")) == "n/a"


class TestCpuAcrossSteps:
    """An sbatch script whose work is one srun line has a near-zero batch step.
    Reading the batch step alone wrote off 15 real jobs here as having done nothing.
    """

    def _job(self, rows, **alloc):
        base = {
            "JobID": "910",
            "JobName": "w",
            "State": "COMPLETED",
            "ElapsedRaw": "1081",
            "AllocCPUS": "16",
            "NNodes": "4",
            "AllocTRES": "cpu=16,node=4",
            "CPUTimeRAW": str(16 * 1081),
            "TotalCPU": "04:47:33",
            "Start": "2026-01-01T00:00:00",
            "End": "2026-01-01T00:18:01",
        }
        base.update(alloc)
        return parse("\n".join([row(**base)] + rows))[0]

    def test_the_srun_step_is_not_discarded_for_the_batch_step(self):
        """Job 51554217: 16 cores over 4 nodes, 04:47:33 of CPU in step .0, and a
        batch step of 0.037s. It reported 0.0009% utilization and read as idle."""
        job = self._job(
            [
                row(JobID="910.batch", JobName="batch", State="COMPLETED", TotalCPU="00:00.037"),
                row(JobID="910.extern", JobName="extern", State="COMPLETED", TotalCPU="00:00.002"),
                row(
                    JobID="910.0",
                    JobName="bash",
                    State="COMPLETED",
                    TotalCPU="04:47:30",
                    AllocCPUS="16",
                    CPUTimeRAW=str(16 * 1081),
                ),
            ]
        )
        assert job.total_cpu == pytest.approx(4 * 3600 + 47 * 60 + 30 + 0.037, abs=0.01)
        assert job.cpu_utilization > 0.9

    def test_extern_is_excluded_from_the_sum(self):
        """Job 49842638's extern claims 538 core-hours against work steps that all
        report zero. Summing it in would invent CPU time for an idle reservation."""
        job = self._job(
            [
                row(JobID="910.batch", JobName="batch", State="COMPLETED", TotalCPU="00:00.005"),
                row(
                    JobID="910.extern", JobName="extern", State="COMPLETED", TotalCPU="22-10:18:45"
                ),
            ]
        )
        assert job.total_cpu == pytest.approx(0.005, abs=0.001)

    def test_the_denominator_covers_the_whole_allocation_not_one_node(self):
        """The batch step's CPUTime counts the node the script ran on. Dividing a
        4-node job's CPU by it reported 399% -- 16 cores' work over 4 cores' worth."""
        job = self._job(
            [
                row(
                    JobID="910.batch",
                    JobName="batch",
                    State="COMPLETED",
                    TotalCPU="00:00.037",
                    AllocCPUS="4",
                    CPUTimeRAW=str(4 * 1081),
                ),
                row(
                    JobID="910.0",
                    JobName="bash",
                    State="COMPLETED",
                    TotalCPU="04:47:30",
                    AllocCPUS="16",
                    CPUTimeRAW=str(16 * 1081),
                ),
            ]
        )
        assert job.cpu_time == pytest.approx(16 * 1081)
        assert job.cpu_utilization <= 1.0

    def test_a_step_outliving_the_allocation_does_not_exceed_100_percent(self):
        """Job 51554394: cancelled after 5s while step .0 ran 8s on 8 cores, so
        sacct's own TotalCPU (00:44.686) exceeds its own CPUTime (40s)."""
        job = self._job(
            [
                row(JobID="910.batch", JobName="batch", State="CANCELLED", TotalCPU="00:00.026"),
                row(
                    JobID="910.0",
                    JobName="bash",
                    State="CANCELLED",
                    TotalCPU="00:44.562",
                    AllocCPUS="8",
                    CPUTimeRAW="64",
                ),
            ],
            ElapsedRaw="5",
            AllocCPUS="8",
            NNodes="2",
            AllocTRES="cpu=8,node=2",
            CPUTimeRAW="40",
            TotalCPU="00:44.686",
        )
        assert job.cpu_time == pytest.approx(64)
        assert job.cpu_utilization <= 1.0


class TestDiskReadWriteSplit:
    def test_read_and_write_are_separate(self):
        job = build(
            batch={
                "TRESUsageInTot": "cpu=04:00:00,fs/disk=112710599158",
                "TRESUsageOutTot": "fs/disk=139565725797",
            }
        )
        assert job.read_bytes == 112710599158
        assert job.write_bytes == 139565725797

    def test_write_is_not_lost(self):
        """The bug this closes: reading only TRESUsageInTot hid 139 GB of writes."""
        job = build(batch={"TRESUsageOutTot": "fs/disk=139565725797"})
        assert job.write_bytes == 139565725797

    def test_io_total_and_rate(self):
        job = build(
            batch={
                "TRESUsageInTot": "fs/disk=3600000000",
                "TRESUsageOutTot": "fs/disk=3600000000",
            }
        )
        assert job.io_bytes == 7200000000
        assert job.io_rate == pytest.approx(2000000.0)

    def test_max_disk_fields_used_when_tres_absent(self):
        job = build(batch={"MaxDiskRead": "107489.20M", "MaxDiskWrite": "133100.25M"})
        assert job.read_bytes == pytest.approx(107489.20 * 1024**2, rel=1e-6)
        assert job.write_bytes == pytest.approx(133100.25 * 1024**2, rel=1e-6)

    def test_heavy_io_flagged(self):
        job = build(batch={"TRESUsageInTot": "fs/disk=%d" % (500 * 1024**3)})
        assert "io-heavy" in codes(job)

    def test_modest_io_says_nothing_at_all(self):
        """There used to be an INFO here restating the DISK gauge row verbatim --
        same bytes, same rate, no action. Two lines of the findings list telling
        the reader what they had just read one screen above."""
        job = build(batch={"TRESUsageInTot": "fs/disk=%d" % (20 * 1024**3)})
        assert "io-volume" not in codes(job)
        assert "io-heavy" not in codes(job)

    def test_small_io_says_nothing(self):
        job = build(batch={"TRESUsageInTot": "fs/disk=1048576"})
        assert "io-volume" not in codes(job)

    def test_the_bytes_are_still_reported_in_the_filesystem_section(self):
        """Dropping the io-volume finding must not drop the measurement."""
        from slurmpast.render import job_sections

        job = build(batch={"TRESUsageInTot": "fs/disk=%d" % (20 * 1024**3)})
        rows = dict(job_sections(job, summarized=True))["filesystem"]
        assert ("read", "20.0 GiB", None) in rows, rows


class TestMemoryDetail:
    def test_peak_attributed_to_node_and_task(self):
        job = build(batch={"MaxRSSNode": "midway3-0600", "MaxRSSTask": "3"})
        assert job.max_rss_node == "midway3-0600"
        assert job.max_rss_task == "3"

    def test_average_rss_captured(self):
        assert build(batch={"AveRSS": "500000K"}).ave_rss == 500000 * 1024

    def test_task_imbalance(self):
        job = build(
            batch={"MaxRSS": "1000000K", "AveRSS": "250000K", "NTasks": "4"}, alloc={"NTasks": "4"}
        )
        assert job.rss_task_imbalance == pytest.approx(4.0)
        assert "task-memory-imbalance" in codes(job)

    def test_vmsize_ratio_explained_not_alarming(self):
        job = build(batch={"MaxVMSize": "1777525092K", "MaxRSS": "193517740K"})
        assert job.vmsize_to_rss == pytest.approx(1777525092 / 193517740.0)

    def test_memory_slack_flagged_when_large_and_absolute(self):
        job = build(alloc={"AllocTRES": "cpu=8,mem=200G,node=1"}, batch={"MaxRSS": "10000000K"})
        assert "memory-slack" in codes(job)

    def test_memory_slack_silent_on_small_absolute_waste(self):
        """90% of a 2 GiB request unused is not worth a word."""
        job = build(alloc={"AllocTRES": "cpu=8,mem=2G,node=1"}, batch={"MaxRSS": "100000K"})
        assert "memory-slack" not in codes(job)

    def test_memory_slack_silent_when_well_sized(self):
        job = build(alloc={"AllocTRES": "cpu=8,mem=64G,node=1"}, batch={"MaxRSS": "60000000K"})
        assert "memory-slack" not in codes(job)

    def test_mem_utilization(self):
        job = build(
            alloc={"AllocTRES": "cpu=8,mem=100G,node=1"}, batch={"MaxRSS": "%dK" % (50 * 1024**2)}
        )
        assert job.mem_utilization == pytest.approx(0.5, abs=1e-3)


class TestPaging:
    def test_page_faults_flagged(self):
        assert "paging" in codes(build(batch={"MaxPages": "5000"}))

    def test_no_paging_no_finding(self):
        assert "paging" not in codes(build(batch={"MaxPages": "0"}))


class TestStragglers:
    def test_straggler_detected(self):
        job = build(
            alloc={"NTasks": "8"}, batch={"NTasks": "8", "AveCPU": "01:00:00", "MinCPU": "00:20:00"}
        )
        assert job.straggler_spread == pytest.approx(2 / 3.0)
        assert "straggler" in codes(job)

    def test_balanced_tasks_not_flagged(self):
        job = build(
            alloc={"NTasks": "8"}, batch={"NTasks": "8", "AveCPU": "01:00:00", "MinCPU": "00:58:00"}
        )
        assert "straggler" not in codes(job)

    def test_single_task_job_never_a_straggler(self):
        job = build(
            alloc={"NTasks": "1"}, batch={"NTasks": "1", "AveCPU": "01:00:00", "MinCPU": "00:01:00"}
        )
        assert job.straggler_spread is None
        assert "straggler" not in codes(job)

    def test_slowest_task_attributed(self):
        job = build(
            alloc={"NTasks": "4"},
            batch={
                "NTasks": "4",
                "AveCPU": "01:00:00",
                "MinCPU": "00:10:00",
                "MinCPUNode": "midway3-0385",
                "MinCPUTask": "2",
            },
        )
        assert job.slowest_task == ("midway3-0385", "2")
        assert "midway3-0385" in find(job, "straggler").evidence

    def test_straggler_advice_warns_about_the_victim(self):
        job = build(
            alloc={"NTasks": "4"}, batch={"NTasks": "4", "AveCPU": "01:00:00", "MinCPU": "00:10:00"}
        )
        assert "victim" in find(job, "straggler").action.lower()


class TestSchedulingAndContext:
    def test_backfill_detected(self):
        assert build(alloc={"Flags": "SchedBackfill"}).scheduled_by == "backfill"

    def test_main_scheduler_detected(self):
        assert build(alloc={"Flags": "SchedMain"}).scheduled_by == "main"

    def test_unknown_flags(self):
        assert build(alloc={"Flags": ""}).scheduled_by == ""

    def test_queue_wait_captured(self):
        assert build(alloc={"Reserved": "00:05:00"}).queue_wait == 300.0

    def test_priority_captured(self):
        assert build(alloc={"Priority": "1137634"}).priority == 1137634

    def test_derived_exit_code(self):
        assert build(alloc={"DerivedExitCode": "2:0"}).derived_exit_code == 2

    def test_identity_fields(self):
        job = build(
            alloc={
                "Cluster": "midway3",
                "Group": "youzhi",
                "UID": "94074",
                "WCKey": "proj",
                "Reservation": "rossby",
            }
        )
        assert job.cluster == "midway3"
        assert job.group == "youzhi"
        assert job.reservation == "rossby"

    def test_shape_fields(self):
        job = build(alloc={"NNodes": "4", "NTasks": "16", "AllocNodes": "4", "ReqNodes": "4"})
        assert job.node_count == 4
        assert job.task_count == 16

    def test_energy_absent_reports_none_not_zero(self):
        """AcctGatherEnergyType=none here, so energy must read n/a, never 0."""
        assert build(batch={"ConsumedEnergy": "0"}).energy_joules is None


class TestRestraintHolds:
    def test_a_healthy_job_still_says_nothing(self, healthy_job):
        criticals = [f for f in diagnose(healthy_job).findings if f.severity == "critical"]
        assert not criticals

    def test_wide_extraction_did_not_make_the_tool_chatty(self):
        """A clean job must not acquire findings just because more fields are read."""
        assert codes(build()) == set()


class TestJsonCompleteness:
    """The JSON must expose everything the reader extracted.

    If a measurement is captured but not emitted, downstream analysis has to
    re-run sacct with a wider --format, which defeats the point of reading it.
    """

    def _payload(self, job):
        from slurmpast.cli import _job_json

        return _job_json(job, "/tmp/j.out", diagnose(job))

    def test_all_groups_present(self):
        payload = self._payload(build())
        assert set(payload) >= {
            "identity",
            "outcome",
            "timing",
            "shape",
            "cpu",
            "memory",
            "filesystem",
            "gpu",
            "steps",
            "findings",
        }

    def test_cpu_split_exposed(self):
        cpu = self._payload(build())["cpu"]
        assert cpu["user_seconds"] is not None
        assert cpu["system_seconds"] is not None
        assert cpu["system_fraction"] is not None

    def test_read_and_write_both_exposed(self):
        job = build(
            batch={
                "TRESUsageInTot": "fs/disk=100",
                "TRESUsageOutTot": "fs/disk=200",
            }
        )
        fs = self._payload(job)["filesystem"]
        assert fs["read_bytes"] == 100
        assert fs["write_bytes"] == 200
        assert fs["total_bytes"] == 300

    def test_memory_attribution_exposed(self):
        job = build(batch={"MaxRSSNode": "midway3-0600", "MaxRSSTask": "7"})
        mem = self._payload(job)["memory"]
        assert mem["peak_node"] == "midway3-0600"
        assert mem["peak_task"] == "7"

    def test_steps_carry_their_own_measurements(self):
        payload = self._payload(build(batch={"MaxRSSNode": "n1", "AveCPU": "00:10:00"}))
        step = [s for s in payload["steps"] if s["step_id"].endswith(".batch")][0]
        assert step["max_rss_node"] == "n1"
        assert step["ave_cpu_seconds"] == 600.0

    def test_unreadable_values_are_null_never_zero(self):
        job = build(batch={"MaxRSS": "", "TRESUsageInTot": "", "MaxDiskRead": ""})
        payload = self._payload(job)
        assert payload["memory"]["peak_bytes"] is None
        assert payload["filesystem"]["read_bytes"] is None

    def test_gpu_utilization_is_explicitly_null(self):
        """gres/gpuutil is absent from this cluster's AccountingStorageTRES."""
        assert self._payload(build())["gpu"]["utilization"] is None

    def test_json_is_serialisable(self):
        import json

        json.dumps(self._payload(build()))


class TestFalsePositivesFoundOnRealData:
    """Both of these fired on a real seven-month history and were noise.

    Left uncorrected, `rss-step-spread` alone would have appeared on 77% of
    jobs -- the fastest way to train a user to ignore every finding.
    """

    def test_extern_step_does_not_create_a_spread_finding(self):
        """.extern holds ~2 MB on every job; that spread is structural."""
        job = parse(
            "\n".join(
                [
                    row(
                        JobID="901",
                        JobName="w",
                        State="COMPLETED",
                        ElapsedRaw="3600",
                        AllocTRES="cpu=8,mem=64G,node=1",
                        End="2026-01-01T01:00:00",
                    ),
                    row(
                        JobID="901.batch",
                        JobName="batch",
                        State="COMPLETED",
                        ElapsedRaw="3600",
                        TotalCPU="04:00:00",
                        MaxRSS="60000000K",
                    ),
                    row(
                        JobID="901.extern",
                        JobName="extern",
                        State="COMPLETED",
                        ElapsedRaw="3600",
                        TotalCPU="00:00:00",
                        MaxRSS="1956K",
                    ),
                ]
            )
        )[0]
        assert job.rss_step_spread is None
        assert "rss-step-spread" not in codes(job)

    def test_max_rss_still_spans_every_step(self):
        """Excluding extern from the *spread* must not change the *peak*."""
        job = parse(
            "\n".join(
                [
                    row(
                        JobID="902",
                        JobName="w",
                        State="COMPLETED",
                        ElapsedRaw="3600",
                        AllocTRES="cpu=8,mem=64G,node=1",
                        End="2026-01-01T01:00:00",
                    ),
                    row(JobID="902.batch", JobName="batch", State="COMPLETED", MaxRSS="4108K"),
                    row(
                        JobID="902.extern", JobName="extern", State="COMPLETED", MaxRSS="16439052K"
                    ),
                ]
            )
        )[0]
        assert job.max_rss == 16439052 * 1024

    def _extern_job(self, extern, batch="3920K", mem="50G"):
        return parse(
            "\n".join(
                [
                    row(
                        JobID="903",
                        JobName="w",
                        State="COMPLETED",
                        ElapsedRaw="3600",
                        AllocTRES="cpu=6,mem=%s,node=1" % mem,
                        End="2026-01-01T01:00:00",
                    ),
                    row(JobID="903.batch", JobName="batch", State="COMPLETED", MaxRSS=batch),
                    row(JobID="903.extern", JobName="extern", State="COMPLETED", MaxRSS=extern),
                ]
            )
        )[0]

    def test_an_extern_reading_the_allocation_rules_out_is_dropped(self):
        """Job 49455391: extern reads 2.81 TiB against mem=50G, on a cluster whose
        largest node holds 2.21 TiB, for a batch step that used 3.8 MiB and 0.004s.
        Reporting that as a 5757% MEM% is a phantom."""
        job = self._extern_job(extern="3018550856K")
        assert job.max_rss == 3920 * 1024
        assert job.mem_utilization < 0.01

    def test_a_plausible_extern_peak_is_still_the_peak(self):
        """The counter-example this rule must not break: job 51709094's extern
        holds 15.7 GiB against a 50 GiB limit -- inside the allocation, so it is
        the job's own processes accounted to the container step."""
        job = self._extern_job(extern="16439052K")
        assert job.max_rss == 16439052 * 1024

    def test_work_steps_over_the_limit_too_keeps_the_plain_max(self):
        """Then it is not an extern artefact but shared-page double counting, and
        the honest answer is the upper bound with the caveat already attached."""
        job = self._extern_job(extern="80G", batch="60G", mem="56G")
        assert job.max_rss == 80 * 1024**3

    def test_with_no_allocation_to_judge_against_the_max_stands(self):
        job = parse(
            "\n".join(
                [
                    row(JobID="904", JobName="w", State="COMPLETED", ElapsedRaw="3600"),
                    row(JobID="904.batch", JobName="batch", State="COMPLETED", MaxRSS="4108K"),
                    row(
                        JobID="904.extern",
                        JobName="extern",
                        State="COMPLETED",
                        MaxRSS="3018550856K",
                    ),
                ]
            )
        )[0]
        assert job.max_rss == 3018550856 * 1024

    def test_spread_between_real_work_steps_is_still_measured(self):
        job = parse(
            "\n".join(
                [
                    row(
                        JobID="903",
                        JobName="w",
                        State="COMPLETED",
                        ElapsedRaw="3600",
                        AllocTRES="cpu=8,mem=64G,node=1",
                        End="2026-01-01T01:00:00",
                    ),
                    row(
                        JobID="903.batch",
                        JobName="batch",
                        State="COMPLETED",
                        ElapsedRaw="3600",
                        TotalCPU="04:00:00",
                        MaxRSS="60000000K",
                    ),
                    row(
                        JobID="903.0",
                        JobName="srun",
                        State="COMPLETED",
                        ElapsedRaw="3600",
                        TotalCPU="04:00:00",
                        MaxRSS="1000K",
                    ),
                ]
            )
        )[0]
        assert job.rss_step_spread is not None
        assert job.rss_step_spread and job.rss_step_spread > 100
        assert "rss-step-spread" not in codes(job)

    def test_handful_of_page_faults_is_not_thrashing(self):
        assert "paging" not in codes(build(batch={"MaxPages": "15"}))

    def test_sustained_faulting_still_flagged(self):
        assert "paging" in codes(build(batch={"MaxPages": "500000"}))


class TestAnExplicitZeroIsAMeasurement:
    """`TRESUsageInTot` is authoritative, including when it says nothing was read.

    `_tres_bytes` turned every 0 into None so the documented fallback took over,
    and a job that provably moved no data was rendered from a stale `MaxDiskRead`
    -- complete with a filesystem-pacing finding about I/O it never did. The
    None-for-zero rule is right for a *ceiling* and wrong for a measurement.
    """

    def test_zero_bytes_read_is_reported_as_zero(self):
        job = build(
            batch={"TRESUsageInTot": "cpu=14400,fs/disk=0", "MaxDiskRead": "500G"},
        )
        assert job.read_bytes == 0

    def test_an_absent_field_still_falls_back(self):
        """Only an explicit zero changes; "not recorded" must still defer."""
        job = build(batch={"TRESUsageInTot": "cpu=14400", "MaxDiskRead": "500G"})
        assert job.read_bytes == 500 * 1024**3

    def test_a_zero_memory_ceiling_is_still_treated_as_unrecorded(self):
        """The rule that motivated None-for-zero: a 0-byte limit does not exist."""
        job = build(alloc={"AllocTRES": "billing=8,cpu=8,mem=0,node=1", "ReqMem": "64Gn"})
        assert job.mem_limit_bytes == 64 * 1024**3


class TestDeadlineIsAFailure:
    """Killed for exceeding a time it was given, exactly as TIMEOUT is.

    Left out of `Job.failed`, a DEADLINE run counted as neither failed nor
    completed: it dropped out of the failure count, out of `problems`, and out of
    `fail_rate`'s denominator, so five COMPLETED beside five DEADLINE reported a 0%
    failure rate. `theme.STATE_HEALTH` graded it "crit" the whole time.
    """

    def test_a_deadline_run_counts_as_failed(self):
        job = build(alloc={"State": "DEADLINE"})
        assert job.failed is True
        assert job.completed is False
        assert job.cancelled is False

    def test_it_reaches_the_failure_rate(self):
        from slurmpast.index import build_groups

        jobs = [build(alloc={"JobID": "%d" % (700 + i)}) for i in range(5)]
        jobs += [build(alloc={"JobID": "%d" % (800 + i), "State": "DEADLINE"}) for i in range(5)]
        group = build_groups(jobs)[0]
        assert group.failed == 5
        assert group.failure_rate == 0.5


class TestDiskTotalsSumTheStepsThatMovedTheData:
    """`_from_steps` sums CPU because "Slurm's steps are disjoint sets of processes
    ... no process is counted twice", and rejects the alternative in the same
    breath: "Falling back to the largest step was wrong too: it drops every step but
    one." Read and write bytes did exactly that. Four `srun` steps each reading
    30 GiB reported 30 GiB, `io_rate` came out at a quarter of the truth, and
    `io-heavy` -- whose whole purpose is to say when the filesystem set the pace --
    stayed silent at a real 136 MiB/s against its 100 MiB/s threshold.
    """

    GIB = 1024**3

    @classmethod
    def _pipeline(cls, steps=4, read_gib=30, write_gib=10, elapsed=3600, extern_gib=None):
        rows = [
            row(
                JobID="960",
                JobName="pipeline",
                State="COMPLETED",
                ExitCode="0:0",
                Start="2026-01-01T00:00:00",
                End="2026-01-01T01:00:00",
                ElapsedRaw=str(elapsed),
                AllocTRES="cpu=8,mem=64G,node=1",
                AllocCPUS="8",
                NNodes="1",
                NodeList="n1",
            ),
            row(JobID="960.batch", JobName="batch", State="COMPLETED", TotalCPU="00:10"),
        ]
        if extern_gib is not None:
            rows.append(
                row(
                    JobID="960.extern",
                    JobName="extern",
                    State="COMPLETED",
                    TRESUsageInTot="fs/disk=%d" % (extern_gib * cls.GIB),
                )
            )
        for index in range(steps):
            rows.append(
                row(
                    JobID="960.%d" % index,
                    JobName="step",
                    State="COMPLETED",
                    TotalCPU="10:00",
                    TRESUsageInTot="fs/disk=%d" % (read_gib * cls.GIB),
                    TRESUsageOutTot="fs/disk=%d" % (write_gib * cls.GIB),
                )
            )
        return parse("\n".join(rows))[0]

    def test_four_steps_report_four_steps_worth(self):
        job = self._pipeline()
        assert job.read_bytes == 4 * 30 * self.GIB
        assert job.write_bytes == 4 * 10 * self.GIB
        assert job.io_bytes == 4 * 40 * self.GIB

    def test_one_step_is_unchanged(self):
        """The single-`srun` job that is most of a real history reads the same as
        it always did -- a sum over one step is that step."""
        job = self._pipeline(steps=1)
        assert job.read_bytes == 30 * self.GIB

    def test_the_rate_and_the_finding_follow(self):
        """Four steps of 120 GiB in an hour is 136 MiB/s sustained, past
        IO_RATE_LOUD. Reported as one step's 34 MiB/s, `io-heavy` never fired --
        the finding whose entire purpose is to say when the filesystem, not the
        GPU, set the pace."""
        job = self._pipeline(read_gib=120, write_gib=0, elapsed=3600)
        assert job.io_rate == pytest.approx(4 * 120 * self.GIB / 3600.0)
        assert job.io_rate > 100 * 1024**2
        assert "io-heavy" in codes(job)

    def test_extern_cannot_speak_for_the_job(self):
        """The same artefact `_from_steps` documents in CPU: a job whose extern step
        claims 500 GiB against 1 GiB of real work was reporting 500."""
        job = self._pipeline(steps=1, read_gib=1, extern_gib=500)
        assert job.read_bytes == 1 * self.GIB

    def test_extern_is_still_the_answer_when_it_is_the_only_one(self):
        """Reporting nothing would be the bigger loss -- the same fallback shape
        `total_cpu` uses when no work step recorded a figure."""
        job = self._pipeline(steps=0, extern_gib=2)
        assert job.read_bytes == 2 * self.GIB
