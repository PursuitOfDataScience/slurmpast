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

    def test_modest_io_is_only_informational(self):
        job = build(batch={"TRESUsageInTot": "fs/disk=%d" % (20 * 1024**3)})
        assert "io-volume" in codes(job)
        assert "io-heavy" not in codes(job)

    def test_small_io_says_nothing(self):
        job = build(batch={"TRESUsageInTot": "fs/disk=1048576"})
        assert "io-volume" not in codes(job)


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

    def test_spread_between_real_work_steps_still_reported(self):
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
        assert "rss-step-spread" in codes(job)

    def test_handful_of_page_faults_is_not_thrashing(self):
        assert "paging" not in codes(build(batch={"MaxPages": "15"}))

    def test_sustained_faulting_still_flagged(self):
        assert "paging" in codes(build(batch={"MaxPages": "500000"}))
