"""Every assumption about "the cluster" that turned out to be about *one* cluster.

This tool was written against Slurm 20.11.8 on Midway3, and each case below is a
place where that showed through -- verified against the Slurm documentation, the
release notes that changed the behaviour, or `scontrol show hostnames` itself.
None of them fail on Midway3, which is exactly why they need pinning.
"""

import io
import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime

import pytest

from slurmpast import logs, model
from slurmpast import sacct as sacct_mod
from slurmpast.duration import parse_bytes, parse_mem_limit
from slurmpast.nodes import expand_nodelist
from slurmpast.sacct import (
    _ALIASES,
    _FIELDS,
    _OPTIONAL,
    SAFE_DELIMITER,
    Sacct,
    SacctError,
    child_env,
    live_job_ids,
    parse,
    resolve_fields,
)
from slurmpast.site import Site, gpu_utilization_note, maxrss_caveat, site

from .conftest import make_text, row

_SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "slurmpast"


def _fields_lower(names):
    return {n.lower() for n in names}


class TestFieldNamesAcrossReleases:
    """Slurm renames fields. A rename is not the same as a removal.

    `Reserved` became `Planned` in 23.02 (release notes: "sacct - Rename
    'Reserved' field to 'Planned'"). Treating it as merely optional means every
    cluster from 23.02 onward drops queue wait with no error at all.
    """

    def test_reserved_is_asked_for_on_an_older_slurm(self):
        chosen = resolve_fields(_fields_lower(_FIELDS))
        assert "Reserved" in chosen
        assert "Planned" not in chosen

    def test_planned_is_asked_for_when_reserved_is_gone(self):
        available = _fields_lower(_FIELDS) - {"reserved"}
        available.add("planned")
        chosen = resolve_fields(available)
        assert "Planned" in chosen
        assert "Reserved" not in chosen

    def test_queue_wait_is_read_back_under_one_name(self):
        """The rest of the codebase must not learn that the field moved."""
        fields = resolve_fields(_fields_lower(_FIELDS) - {"reserved"} | {"planned"})
        values = {"Planned": "00:05:00", "JobID": "7", "State": "COMPLETED"}
        text = "|".join(values.get(name, "") for name in fields)
        job = parse(text, fields=fields)[0]
        assert job.queue_wait == 300.0

    def test_a_field_this_slurm_never_had_is_dropped(self):
        """Requesting one unknown field makes sacct reject the whole query."""
        available = _fields_lower(_FIELDS) - {"stdout", "stderr", "submitline"}
        chosen = resolve_fields(available)
        assert "StdOut" not in chosen and "SubmitLine" not in chosen
        assert "JobID" in chosen and "State" in chosen

    def test_a_non_optional_field_is_kept_so_breakage_is_loud(self):
        chosen = resolve_fields({"jobid"})
        assert "State" in chosen, "silently dropping a load-bearing field hides the fault"

    def test_no_probe_asks_for_everything(self):
        assert resolve_fields(None) == [_ALIASES.get(f, (f,))[0] for f in _FIELDS]

    def test_every_optional_name_is_actually_requested(self):
        """A typo in _OPTIONAL makes a field un-droppable and breaks old clusters."""
        assert not set(_OPTIONAL) - set(_FIELDS)


class TestDelimiter:
    """`--constraint="v100|a100"` is documented Slurm syntax, and `--parsable2`
    does not escape the pipe it puts in the Constraints column."""

    def test_a_pipe_in_a_value_no_longer_shifts_every_later_column(self):
        fields = list(_FIELDS)
        values = {
            "JobID": "11",
            "JobName": "train",
            "State": "COMPLETED",
            "Constraints": "v100|a100",
            "ElapsedRaw": "600",
            "AllocTRES": "cpu=8,mem=64G,node=1",
            "AllocCPUS": "8",
        }
        text = SAFE_DELIMITER.join(str(values.get(name, "")) for name in fields)
        job = parse(text, fields=fields, delimiter=SAFE_DELIMITER)[0]
        assert job.constraints == "v100|a100"
        # The columns after Constraints are the ones a shift corrupts.
        assert job.alloc_tres == "cpu=8,mem=64G,node=1"
        assert job.cpu_count == 8
        assert job.elapsed == 600.0

    def test_the_query_asks_for_the_safe_delimiter(self):
        seen = []

        def runner(args):
            seen.append(args)
            return ""

        Sacct(runner=runner, probe=" ".join(_FIELDS)).history(user="u")
        assert any("--delimiter=" + SAFE_DELIMITER in a for a in seen[0])

    def test_an_ancient_sacct_without_the_option_falls_back(self):
        calls = []

        def runner(args):
            calls.append(args)
            if any(a.startswith("--delimiter") for a in args):
                raise SacctError("sacct: unrecognized option '--delimiter=\\x1f'")
            return row(JobID="12", JobName="w", State="COMPLETED", ElapsedRaw="60")

        sacct = Sacct(runner=runner, probe=" ".join(_FIELDS))
        jobs = sacct.history(user="u")
        assert [j.job_id for j in jobs] == ["12"]
        assert len(calls) == 2, "should retry exactly once, without the option"
        # And it remembers, rather than paying for the failure on every query.
        sacct.history(user="u")
        assert len(calls) == 3

    def test_a_real_error_is_not_retried_as_an_option_problem(self):
        calls = []

        def runner(args):
            calls.append(args)
            raise SacctError("sacct: fatal: Bad job/step specified: zzz")

        with pytest.raises(SacctError, match="Bad job/step"):
            Sacct(runner=runner, probe=" ".join(_FIELDS)).jobs(["zzz"])
        assert len(calls) == 1

    def test_a_pipe_bearing_row_is_dropped_not_misread_on_the_fallback(self):
        """With `|` there is no way to realign, and a shifted row reports another
        column's memory as this job's -- worse than reporting nothing."""
        fields = list(_FIELDS)
        good = row(JobID="20", JobName="w", State="COMPLETED", ElapsedRaw="60")
        bad = row(JobID="21", JobName="a|b", State="COMPLETED", ElapsedRaw="60")
        jobs = parse(good + "\n" + bad, fields=fields, delimiter="|")
        assert [j.job_id for j in jobs] == ["20"]


class TestTimestampFormat:
    """SLURM_TIME_FORMAT rewrites every timestamp sacct prints. Verified live on
    20.11.8: `relative` turns 2026-04-29T14:55:48 into "29 Apr 14:55"."""

    def test_the_child_is_told_which_format_to_use(self):
        env = child_env({"SLURM_TIME_FORMAT": "relative"})
        assert env["SLURM_TIME_FORMAT"] == "standard"

    def test_a_strftime_value_is_overridden_too(self):
        assert child_env({"SLURM_TIME_FORMAT": "%s"})["SLURM_TIME_FORMAT"] == "standard"

    def test_format_overrides_that_change_the_columns_are_dropped(self):
        env = child_env({"SACCT_FORMAT": "jobid,user", "SQUEUE_FORMAT": "%i"})
        assert "SACCT_FORMAT" not in env and "SQUEUE_FORMAT" not in env

    def test_the_rest_of_the_environment_survives(self):
        env = child_env({"HOME": "/home/me", "SLURM_CONF": "/etc/slurm/slurm.conf"})
        assert env["HOME"] == "/home/me"
        assert env["SLURM_CONF"] == "/etc/slurm/slurm.conf"


class TestHostlistExpansion:
    """Checked against `scontrol show hostnames`, which is the authority."""

    @pytest.mark.parametrize(
        "expression,expected",
        [
            ("node[1-3]", ["node1", "node2", "node3"]),
            (
                "midway3-[0277-0279,0281]",
                ["midway3-0277", "midway3-0278", "midway3-0279", "midway3-0281"],
            ),
            ("tux[1,3,5-7]", ["tux1", "tux3", "tux5", "tux6", "tux7"]),
            ("a1,b[2-3],c", ["a1", "b2", "b3", "c"]),
            # Underscores and dots are legal in a node name; a character class
            # enumerating "what a prefix may contain" got both of these wrong and
            # returned the bracket expression itself as a node name.
            ("cn_[01-02]", ["cn_01", "cn_02"]),
            ("gpu.node[1-2]", ["gpu.node1", "gpu.node2"]),
            # Shared suffix after the bracket, allowed from Slurm 23.11.
            ("node[1-2]-ib", ["node1-ib", "node2-ib"]),
            ("midway3-0600", ["midway3-0600"]),
        ],
    )
    def test_matches_slurm(self, expression, expected):
        assert expand_nodelist(expression) == expected

    def test_several_ranges_in_one_name_are_a_cartesian_product(self):
        """`unit[0-31]rack[0-41]` is documented in slurm.conf(5) under NodeName,
        and `scontrol show hostnames unit[0-3]rack[0-2]` returns 12 names. The old
        expander returned four, each still holding an unexpanded bracket -- so
        every node of such an allocation was invisible to the node table."""
        assert expand_nodelist("unit[0-1]rack[0-1]") == [
            "unit0rack0",
            "unit0rack1",
            "unit1rack0",
            "unit1rack1",
        ]

    def test_a_list_mixing_both_forms(self):
        assert expand_nodelist("node[1-2],unit[0-1]rack[0-1]") == [
            "node1",
            "node2",
            "unit0rack0",
            "unit0rack1",
            "unit1rack0",
            "unit1rack1",
        ]

    def test_no_nodes_assigned_is_not_two_nodes_called_none_and_assigned(self):
        assert expand_nodelist("None assigned") == []
        assert expand_nodelist("") == []

    def test_a_malformed_range_does_not_hang_or_invent_names(self):
        assert expand_nodelist("node[a-b]") == ["nodea-b"]
        assert expand_nodelist("node[5-1]") == ["node5-1"]

    def test_expansion_is_bounded(self):
        assert len(expand_nodelist("n[1-99999999]")) <= 65536

    def test_the_bound_holds_where_ranges_multiply(self):
        """The bound has to be applied *while* expanding, not to the finished list.
        Trimming afterwards left `u[1-2000]r[1-2000]` building four million strings
        and 325 MiB first, and a third range never returned at all."""
        import resource
        import time

        before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        started = time.time()
        for expression in (
            "u[1-2000]r[1-2000]",
            "x[1-300]y[1-300]z[1-300]",
            "n[1-99999999]m[1-99999999]",
        ):
            assert len(expand_nodelist(expression)) <= 65536
        assert time.time() - started < 5.0
        # Peak RSS is a high-water mark, so this only rises if the run above
        # allocated more than everything before it -- 4M strings would.
        grew_mib = (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before) / 1024.0
        assert grew_mib < 200, "expansion allocated %.0f MiB" % grew_mib

    def test_a_truncated_range_yields_real_names_not_one_fabricated_one(self):
        """The names kept are the first N actual nodes. The old over-limit branch
        fell back to the bracket expression itself, which is not a node at all."""
        names = expand_nodelist("n[1-99999999]")
        assert names[0] == "n1" and names[1] == "n2"
        assert not any("[" in name or "-" in name for name in names)

    @pytest.mark.skipif(
        subprocess.run(["which", "scontrol"], capture_output=True).returncode != 0,
        reason="no Slurm on this machine",
    )
    @pytest.mark.parametrize(
        "expression",
        [
            "node[1-3]",
            "unit[0-3]rack[0-2]",
            "midway3-[0277-0279,0281]",
            "cn_[01-02]",
            "a1,b[2-3],c",
        ],
    )
    def test_agrees_with_the_local_scheduler(self, expression):
        """Differential test against the real expander, where one is available."""
        proc = subprocess.run(
            ["scontrol", "show", "hostnames", expression], capture_output=True, text=True
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            pytest.skip("this Slurm rejects %s" % expression)
        assert expand_nodelist(expression) == proc.stdout.split()


class TestGpuCountAcrossConfigurations:
    """How a cluster records GPUs differs by release and by gres.conf."""

    def _job(self, **kw):
        return parse(row(JobID="1", JobName="w", State="COMPLETED", ElapsedRaw="60", **kw))[0]

    def test_untyped_tres(self):
        assert self._job(AllocTRES="cpu=8,gres/gpu=4,mem=64G,node=1").gpu_count == 4

    def test_typed_tres_alone_still_counts(self):
        """Slurm usually emits the untyped total beside the typed entry, but not on
        every release -- and without this the job reads as CPU-only, so its
        GPU-hours vanish from every total and its group is ranked as CPU work."""
        assert self._job(AllocTRES="cpu=8,gres/gpu:a100=4,mem=64G,node=1").gpu_count == 4

    def test_two_models_on_one_node_are_summed(self):
        job = self._job(AllocTRES="cpu=8,gres/gpu:a100=2,gres/gpu:v100=1,mem=64G,node=1")
        assert job.gpu_count == 3

    def test_the_untyped_total_wins_when_both_are_present(self):
        job = self._job(AllocTRES="cpu=8,gres/gpu=4,gres/gpu:a100=4,mem=64G,node=1")
        assert job.gpu_count == 4

    def test_pre_2011_allocgres_spelling(self):
        """AllocGRES/ReqGRES were removed in Slurm 20.11 in favour of TRES, so on
        an older cluster they are the only place the count exists."""
        assert self._job(AllocGRES="gpu:4").gpu_count == 4
        assert self._job(AllocGRES="gpu:tesla:2").gpu_count == 2
        assert self._job(ReqGRES="gpu").gpu_count == 1

    def test_tres_is_preferred_over_the_legacy_field(self):
        job = self._job(AllocTRES="cpu=8,gres/gpu=4,mem=64G,node=1", AllocGRES="gpu:1")
        assert job.gpu_count == 4

    def test_a_cluster_that_tracks_no_gpus_reports_none_not_zero_hours(self):
        job = self._job(AllocTRES="cpu=8,mem=64G,node=1")
        assert job.gpu_count == 0
        assert job.gpu_hours is None


class TestGpuUtilizationWhereRecorded:
    """`gres/gpuutil` and `gres/gpumem` are gathered automatically wherever
    gres.conf sets AutoDetect=nvml. Midway3 does not, which is why this tool used
    to hardcode "not recorded by Slurm" as though no cluster records it."""

    def _job(self, in_ave="", in_max=""):
        text = "\n".join(
            [
                row(
                    JobID="30",
                    JobName="w",
                    State="COMPLETED",
                    ElapsedRaw="3600",
                    AllocTRES="cpu=8,gres/gpu=2,mem=64G,node=1",
                    AllocCPUS="8",
                ),
                row(
                    JobID="30.batch",
                    JobName="batch",
                    State="COMPLETED",
                    ElapsedRaw="3600",
                    TotalCPU="01:00:00",
                    CPUTimeRAW="28800",
                    TRESUsageInAve=in_ave,
                    TRESUsageInMax=in_max,
                ),
            ]
        )
        return parse(text)[0]

    def test_average_utilization_is_read_as_a_fraction(self):
        job = self._job(in_ave="cpu=00:59:00,gres/gpuutil=87,mem=100K")
        assert job.gpu_utilization == pytest.approx(0.87)

    def test_peak_gpu_memory_is_read_with_its_unit(self):
        job = self._job(in_max="gres/gpumem=36266M,gres/gpuutil=100,mem=100K")
        assert job.gpu_mem_peak_bytes == 36266 * 1024**2

    def test_a_cluster_that_gathers_nothing_reports_none_not_zero(self):
        job = self._job()
        assert job.gpu_utilization is None
        assert job.gpu_mem_peak_bytes is None

    def test_a_recorded_idle_gpu_is_a_measurement_not_an_inference(self):
        from slurmpast.diagnose import diagnose

        verdict = diagnose(self._job(in_ave="gres/gpuutil=1,mem=100K"))
        codes = {f.code for f in verdict.findings}
        assert "gpu-idle" in codes
        assert "gpu-suspect-idle" not in codes, "the CPU proxy must stand down"
        finding = next(f for f in verdict.findings if f.code == "gpu-idle")
        assert "as recorded by Slurm" in finding.evidence

    def test_a_partly_busy_gpu_is_a_warning_not_a_verdict(self):
        from slurmpast.diagnose import diagnose

        codes = {f.code for f in diagnose(self._job(in_ave="gres/gpuutil=22")).findings}
        assert "gpu-underused" in codes

    def test_a_busy_gpu_draws_nothing(self):
        from slurmpast.diagnose import diagnose

        codes = {f.code for f in diagnose(self._job(in_ave="gres/gpuutil=94")).findings}
        assert "gpu-idle" not in codes and "gpu-underused" not in codes

    def test_the_note_names_the_site_setting_rather_than_blaming_slurm(self):
        assert "AutoDetect=nvml" in gpu_utilization_note(Site(tres=("cpu", "gres/gpu")))
        assert "for this job" in gpu_utilization_note(Site(tres=("cpu", "gres/gpuutil")))
        # Nothing known about the cluster: no claim about why.
        assert gpu_utilization_note(Site()) == "not recorded by Slurm"


class TestPerNodeMemory:
    """AllocTRES `mem=` totals the allocation; MaxRSS is one task's peak and
    `--mem` is per node. Verified on job 51553906: `--mem=8G` on 2 nodes records
    `mem=16G`."""

    def _multinode(self, nodes=2, mem="16G", rss="7000000K", req_mem=""):
        text = "\n".join(
            [
                row(
                    JobID="40",
                    JobName="w",
                    State="COMPLETED",
                    ElapsedRaw="600",
                    End="2026-01-01T00:10:00",
                    NNodes=str(nodes),
                    ReqMem=req_mem,
                    AllocTRES="cpu=8,mem=%s,node=%d" % (mem, nodes),
                    AllocCPUS="8",
                ),
                row(
                    JobID="40.batch",
                    JobName="batch",
                    State="COMPLETED",
                    ElapsedRaw="600",
                    TotalCPU="00:40:00",
                    CPUTimeRAW="4800",
                    MaxRSS=rss,
                ),
            ]
        )
        return parse(text)[0]

    def test_the_per_node_ceiling_is_the_total_over_the_nodes(self):
        job = self._multinode(nodes=2, mem="16G")
        assert job.mem_limit_total_bytes == 16 * 1024**3
        assert job.mem_limit_bytes == 8 * 1024**3

    def test_utilization_is_no_longer_understated_by_the_node_count(self):
        job = self._multinode(nodes=2, mem="16G", rss=str(7 * 1024 * 1024) + "K")
        # 7 GiB of an 8 GiB per-node ceiling, not 7 of 16.
        assert job.mem_utilization == pytest.approx(7 / 8.0, rel=1e-3)

    def test_a_single_node_job_is_unchanged(self):
        job = self._multinode(nodes=1, mem="8G")
        assert job.mem_limit_bytes == job.mem_limit_total_bytes == 8 * 1024**3

    def test_an_explicit_per_node_reqmem_is_not_divided(self):
        """Slurm 20.11 and older write `8Gn`, which is already per node."""
        job = self._multinode(nodes=2, mem="", req_mem="8Gn")
        assert job.mem_limit_bytes == 8 * 1024**3
        assert job.mem_limit_total_bytes == 16 * 1024**3

    def test_a_per_cpu_reqmem_is_multiplied_out_for_the_total(self):
        text = row(
            JobID="41",
            JobName="w",
            State="COMPLETED",
            ElapsedRaw="60",
            NNodes="1",
            ReqCPUS="4",
            AllocCPUS="4",
            ReqMem="1750Mc",
        )
        job = parse(text)[0]
        assert job.mem_limit_total_bytes == 4 * 1750 * 1024**2

    def test_a_21_08_style_reqmem_with_no_suffix_is_a_total(self):
        """Slurm 21.08 changed ReqMem to mirror ReqTRES: no n/c marker, and the
        figure is the allocation total."""
        text = row(
            JobID="42", JobName="w", State="COMPLETED", ElapsedRaw="60", NNodes="2", ReqMem="16G"
        )
        job = parse(text)[0]
        assert job.req_mem_scope is None
        assert job.mem_limit_total_bytes == 16 * 1024**3
        assert job.mem_limit_bytes == 8 * 1024**3

    def test_the_detail_screen_names_both_figures_on_a_multinode_job(self):
        """The gauge shows the per-node ceiling and AllocTRES shows the total, so
        without a row saying so the two look like a contradiction."""
        from slurmpast.render import job_sections, mem_text

        job = self._multinode(nodes=15, mem="750G", req_mem="50Gn")
        assert mem_text(job) == "50.0 GiB per node (750.0 GiB over 15)"
        memory = {label: value for _title, rows in job_sections(job) for label, value, _ in rows}
        assert "per node" in memory["limit"]

    def test_a_single_node_job_does_not_gain_a_redundant_row(self):
        from slurmpast.render import job_sections

        job = self._multinode(nodes=1, mem="8G", req_mem="8Gn")
        labels = [label for _t, rows in job_sections(job) for label, _v, _b in rows]
        assert "limit" not in labels

    def test_the_provenance_quotes_what_reqmem_actually_read(self):
        """`0n` is the Slurm 20.11 spelling of "not recorded"; 21.08 writes
        something else, so hardcoding it printed a value the record did not hold."""
        from slurmpast.render import mem_text

        assert "ReqMem read 0n" in mem_text(self._multinode(nodes=1, mem="8G", req_mem="0n"))
        assert "ReqMem read empty" in mem_text(self._multinode(nodes=1, mem="8G", req_mem=""))

    def test_the_slack_finding_no_longer_fires_on_a_well_sized_multinode_job(self):
        """ "Peak 40 GiB of a 750 GiB limit -- 710 GiB never used" was said about a
        15-node job running at 80% of its real per-node ceiling."""
        from slurmpast.diagnose import diagnose

        job = self._multinode(nodes=15, mem="750G", rss=str(40 * 1024 * 1024) + "K")
        assert {f.code for f in diagnose(job).findings}.isdisjoint({"memory-slack"})


class TestPerTaskCpus:
    """`--cpus-per-task` is per task; every CPU counter sacct reports is a total."""

    def _job(self, cpus=8, ntasks=1, nnodes=1, total_cpu="00:10:00"):
        text = "\n".join(
            [
                row(
                    JobID="50",
                    JobName="w",
                    State="COMPLETED",
                    ElapsedRaw="3600",
                    End="2026-01-01T01:00:00",
                    NNodes=str(nnodes),
                    AllocCPUS=str(cpus),
                    AllocTRES="cpu=%d,mem=64G,node=%d" % (cpus, nnodes),
                ),
                row(
                    JobID="50.batch",
                    JobName="batch",
                    State="COMPLETED",
                    ElapsedRaw="3600",
                    TotalCPU=total_cpu,
                    CPUTimeRAW=str(3600 * cpus),
                    NTasks=str(ntasks),
                    MaxRSS="1000K",
                ),
            ]
        )
        return parse(text)[0]

    def test_a_single_task_job_is_unchanged(self):
        job = self._job(cpus=8, ntasks=1)
        assert job.cpus_per_task == 8

    def test_cores_are_divided_among_the_tasks(self):
        job = self._job(cpus=90, ntasks=15)
        assert job.cpus_per_task == 6

    def test_tasks_unrecorded_falls_back_to_the_node_count(self):
        text = row(
            JobID="51",
            JobName="w",
            State="COMPLETED",
            ElapsedRaw="60",
            NNodes="3",
            AllocCPUS="12",
        )
        assert parse(text)[0].cpus_per_task == 4

    # 90 cores over 15 tasks (6 each) for an hour, having burned 12h36m of CPU:
    # 14% utilization, so 12.6 cores of real work in total and 0.84 per task.
    # Reading the total as a per-task figure advised `--cpus-per-task=16` -- more
    # than the 6 the job had, for a workload told to use fewer.
    _FOURTEEN_PERCENT = "12:36:00"

    def test_the_advice_is_per_task_not_per_allocation(self):
        from slurmpast.sizing import cpu_advice

        jobs = [
            self._job(cpus=90, ntasks=15, total_cpu=self._FOURTEEN_PERCENT)._replace(job_id=str(i))
            for i in range(4)
        ]
        advice = cpu_advice(jobs)
        assert advice.requested == "6"
        assert advice.suggestion == "2"
        assert "per task" in advice.basis
        assert "15" in advice.caution

    def test_the_diagnosis_suggests_a_per_task_figure(self):
        from slurmpast.diagnose import diagnose

        job = self._job(cpus=90, ntasks=15, total_cpu=self._FOURTEEN_PERCENT)
        finding = next(f for f in diagnose(job).findings if f.code == "cpu-overrequest")
        assert "--cpus-per-task=1," in finding.action
        # The total is still shown -- it is what was allocated -- but it is labelled.
        assert "of 90 cores across 15 tasks" in finding.evidence


class TestSiteConfiguration:
    """Two of this tool's most-repeated sentences are only true on some clusters."""

    def test_cgroup_gather_means_maxrss_is_a_real_high_water_mark(self):
        text = maxrss_caveat(Site(jobacct_gather_type="jobacct_gather/cgroup"))
        assert "cgroup peak" in text
        assert "sums RSS" not in text

    def test_linux_gather_keeps_the_warning_that_was_earned_here(self):
        text = maxrss_caveat(Site(jobacct_gather_type="jobacct_gather/linux"))
        assert "sums RSS across the process tree" in text

    def test_an_unreachable_scheduler_hedges_rather_than_asserting(self):
        text = maxrss_caveat(Site())
        assert "depending on this cluster" in text

    def test_config_is_parsed_case_insensitively(self):
        found = site(
            runner=lambda _a: (
                "SLURM_VERSION           = 24.05.4\n"
                "JobAcctGatherType       = jobacct_gather/cgroup\n"
                "AccountingStorageTRES   = cpu,mem,node,billing,gres/gpu,gres/gpuutil\n"
            ),
            refresh=True,
        )
        assert found.slurm_version == "24.05.4"
        assert found.rss_from_cgroup is True
        assert found.tracks_gpu is True
        assert found.tracks_gpu_utilization is True
        assert found.known

    def test_a_machine_with_no_scontrol_is_not_an_error(self):
        def missing(_args):
            raise SacctError("cannot execute scontrol")

        found = site(runner=missing, refresh=True)
        assert not found.known
        assert found.rss_from_cgroup is None
        assert found.tracks_gpu is None

    def test_a_cluster_not_tracking_gpus_in_tres_is_distinguishable(self):
        found = Site(tres=("cpu", "mem", "node"), jobacct_gather_type="jobacct_gather/linux")
        assert found.tracks_gpu is False


class TestPackageSurface:
    def test_the_site_submodule_is_not_shadowed_by_a_re_export(self):
        """Re-exporting the `site()` accessor from the package bound the name
        `slurmpast.site` to a function, so `slurmpast.site.reset_cache` stopped
        resolving and every fixture that patched it broke at collection time."""
        import slurmpast
        import slurmpast.site as submodule

        assert slurmpast.site is submodule
        assert callable(submodule.site)

    def test_everything_named_in_all_actually_exists(self):
        import slurmpast

        missing = [name for name in slurmpast.__all__ if not hasattr(slurmpast, name)]
        assert not missing

    def test_the_package_docstring_lists_every_module_the_guarantee_covers(self):
        """It named six of the ten, leaving out `sizing` -- which is the module the
        README's own library example imports -- along with `model`, `logs` and
        `duration`. The guarantee always covered them; the sentence promising it
        was short, so a reader checking whether it was safe to import `sizing` on a
        login node was told nothing."""
        import slurmpast

        promised = slurmpast.__doc__
        renderers = {"tui", "theme", "render", "report"}
        free = {
            name[:-3]
            for name, found in _third_party_imports().items()
            if not found and name.endswith(".py")
        }
        free -= {"__init__", "__main__", "_version", "cli", "demo"}
        missing = sorted(name for name in free if "``%s``" % name not in promised)
        assert not missing, "third-party-free but not named in the docstring: %s" % missing
        # And it must not promise one of the four that do reach for rich/textual.
        overclaimed = sorted(
            name for name in renderers if "``%s``" % name in promised.split("only by")[0]
        )
        assert not overclaimed, overclaimed

    def test_the_analysis_layer_needs_no_third_party_package(self):
        """The README promises this: usable as a library on a login node with no
        UI framework installed. Only the four rendering modules may reach for
        rich or textual."""
        renderers = {"tui.py", "theme.py", "render.py", "report.py"}
        analysis = {
            name: found for name, found in _third_party_imports().items() if name not in renderers
        }
        assert not any(analysis.values()), analysis
        # And the check is not vacuous: the renderers really do import them.
        assert any(_third_party_imports()[name] for name in renderers)


def _third_party_imports(packages=("textual", "rich")):
    """Which slurmpast modules import which of ``packages``, by static read."""
    import ast

    found = {}
    for path in sorted(_SRC.glob("*.py")):
        hits = set()
        for node in ast.walk(ast.parse(path.read_text())):
            roots = []
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots = [node.module.split(".")[0]]
            hits.update(r for r in roots if r in packages)
        found[path.name] = sorted(hits)
    return found


class TestRecordedLogPaths:
    """From Slurm 24.05 sacct records StdOut/StdErr -- as patterns, unexpanded."""

    def _job(self, **kw):
        base = {
            "JobID": "60",
            "JobName": "train",
            "User": "me",
            "State": "FAILED",
            "ElapsedRaw": "60",
            "WorkDir": "/work",
            "NodeList": "node[5-6]",
        }
        base.update(kw)
        return parse(row(**base))[0]

    def test_the_default_pattern_is_expanded(self):
        job = self._job(StdOut="/work/slurm-%j.out")
        assert logs.expand_pattern(job.std_out, job) == "/work/slurm-60.out"

    def test_an_array_element_uses_its_own_allocation_number_for_j(self):
        job = self._job(JobID="60_4", JobIDRaw="73")
        assert logs.expand_pattern("/w/o-%A_%a-%j.out", job) == "/w/o-60_4-73.out"

    def test_the_job_name_and_user_codes(self):
        job = self._job()
        assert logs.expand_pattern("/w/%u-%x.log", job) == "/w/me-train.log"

    def test_a_zero_pad_width_is_honoured(self):
        job = self._job()
        assert logs.expand_pattern("/w/%6j.out", job) == "/w/000060.out"

    def test_an_absurd_zero_pad_width_is_bounded_not_allocated(self):
        """The pattern comes out of the accounting database, so the width is whatever
        the user typed. `--output=o-%2000000000j.out` had zfill allocate 2 GB and took
        find_log down with an uncaught MemoryError -- in a tool whose job is to
        explain a crash, not add one."""
        job = self._job()
        got = logs.expand_pattern("/w/o-%2000000000j.out", job)
        assert len(got) < 200, len(got)
        assert got.endswith(".out")
        # And through the caller, which is where the crash actually surfaced.
        assert logs.find_log(job._replace(std_out="/w/o-%2000000000j.out")) is None

    def test_a_width_at_the_bound_still_pads(self):
        job = self._job()
        assert logs.expand_pattern("/w/%64j.out", job) == "/w/" + "60".zfill(64) + ".out"

    def test_a_literal_percent(self):
        job = self._job()
        assert logs.expand_pattern("/w/100%%.out", job) == "/w/100%.out"

    def test_the_node_code_resolves_to_the_first_node(self):
        job = self._job()
        assert logs.expand_pattern("/w/%N.out", job) == "/w/node5.out"

    def test_an_unresolvable_code_yields_nothing_rather_than_a_stray_percent(self):
        job = self._job(NodeList="")
        assert logs.expand_pattern("/w/%N.out", job) == ""

    def test_a_relative_pattern_is_resolved_against_the_work_directory(self):
        job = self._job(StdErr="logs/err-%j.txt")
        assert logs.recorded_paths(job) == ["/work/logs/err-60.txt"]

    def test_stderr_is_preferred_and_duplicates_collapse(self):
        job = self._job(StdOut="/work/j-%j.out", StdErr="/work/j-%j.err")
        assert logs.recorded_paths(job) == ["/work/j-60.err", "/work/j-60.out"]
        same = self._job(StdOut="/work/j-%j.out", StdErr="/work/j-%j.out")
        assert logs.recorded_paths(same) == ["/work/j-60.out"]

    def test_a_cluster_recording_nothing_yields_nothing(self):
        assert logs.recorded_paths(self._job()) == []

    def test_the_recorded_path_is_searched_before_a_guessed_one(self):
        job = self._job(StdErr="/work/real-%j.err")
        candidates = logs.candidate_paths(job)
        assert candidates[0] == "/work/real-60.err"
        assert "/work/slurm-60.out" in candidates

    def test_a_miss_names_the_recorded_path_where_there_is_one(self):
        """Knowing Slurm recorded /scratch/x.err and that it is not there is a
        different, actionable fact from "no log found anywhere"."""
        from slurmpast.report import Style, render_job

        text, _ = render_job(
            self._job(StdErr="/nowhere/real-%j.err"), style=Style(enabled=False), log_text=None
        )
        assert "none at /nowhere/real-60.err" in text
        assert "moved or deleted" in text

    def test_a_miss_on_a_cluster_recording_nothing_stays_vague(self):
        from slurmpast.report import Style, render_job

        text, _ = render_job(self._job(), style=Style(enabled=False), log_text=None)
        assert "none found" in text
        assert "moved or deleted" not in text

    def test_it_is_still_confirmed_to_exist_rather_than_trusted(self, tmp_path):
        real = tmp_path / "out-60.err"
        real.write_text("boom\n")
        job = self._job(StdErr=str(tmp_path / "out-%j.err"))
        assert logs.find_log(job) == str(real)
        missing = self._job(StdErr=str(tmp_path / "absent-%j.err"))
        assert logs.find_log(missing) is None


class TestSubmitLineLogPaths:
    """SubmitLine arrived in Slurm 21.08, five releases before StdOut/StdErr (24.05).

    On every cluster in between, the -o the job was submitted with is recorded and
    the path is knowable -- reading it is the difference between knowing and guessing
    on roughly three years' worth of releases.
    """

    def _job(self, line, **kw):
        base = {
            "JobID": "60",
            "JobName": "train",
            "User": "me",
            "State": "FAILED",
            "ElapsedRaw": "60",
            "WorkDir": "/work",
            "NodeList": "node[5-6]",
            "SubmitLine": line,
        }
        base.update(kw)
        return parse(row(**base))[0]

    def test_the_long_form_with_equals(self):
        job = self._job('sbatch --output="/work/report/144-train.out" run.sh')
        assert logs.recorded_paths(job) == ["/work/report/144-train.out"]

    def test_the_long_form_as_a_separate_argument(self):
        job = self._job("sbatch --error /work/a.err run.sh")
        assert logs.recorded_paths(job) == ["/work/a.err"]

    def test_the_short_form(self):
        job = self._job("sbatch -o /work/a.out run.sh")
        assert logs.recorded_paths(job) == ["/work/a.out"]

    def test_the_attached_short_form(self):
        """getopt accepts ``-oslurm.out`` with no separator, and so does sbatch."""
        job = self._job("sbatch -o/work/a.out run.sh")
        assert logs.recorded_paths(job) == ["/work/a.out"]

    def test_stderr_is_preferred_over_stdout(self):
        job = self._job("sbatch -o /work/a.out -e /work/a.err run.sh")
        assert logs.recorded_paths(job) == ["/work/a.err", "/work/a.out"]

    def test_a_pattern_in_the_submit_line_is_expanded(self):
        job = self._job("sbatch -o slurm-%j.out run.sh")
        assert logs.recorded_paths(job) == ["/work/slurm-60.out"]

    def test_a_relative_path_resolves_against_the_work_directory(self):
        job = self._job("sbatch -o report/144-train.out run.sh")
        assert logs.recorded_paths(job) == ["/work/report/144-train.out"]

    def test_an_embedded_command_is_not_mistaken_for_an_output_option(self):
        """``--wrap`` holds a shell command. Only the option name before ``=`` is
        inspected, so the -o belonging to gcc is never seen as sbatch's."""
        job = self._job('sbatch --wrap="gcc -o /tmp/a.out a.c"')
        assert logs.recorded_paths(job) == []

    def test_a_later_option_wins_because_that_is_what_sbatch_does(self):
        job = self._job("sbatch -o /work/first.out -o /work/second.out run.sh")
        assert logs.recorded_paths(job)[0] == "/work/second.out"

    def test_a_truncated_option_yields_nothing_rather_than_a_flag(self):
        job = self._job("sbatch -o --exclusive run.sh")
        assert logs.recorded_paths(job) == []

    def test_an_unbalanced_quote_does_not_raise(self):
        job = self._job('sbatch -o "/work/a.out run.sh')
        assert logs.recorded_paths(job) == []

    def test_a_recorded_path_still_beats_a_conventional_name(self):
        job = self._job("sbatch -o /work/real.out run.sh")
        assert logs.candidate_paths(job)[0] == "/work/real.out"

    def test_a_cluster_below_21_08_recording_nothing_yields_nothing(self):
        assert logs.recorded_paths(self._job("")) == []

    def test_stdout_is_preferred_over_the_submit_line_when_both_exist(self):
        """On 24.05+ both are recorded. StdOut is what Slurm resolved and used;
        the submit line is what was typed, so it loses ties."""
        job = self._job("sbatch -o /work/typed.out run.sh", StdOut="/work/used.out")
        assert logs.recorded_paths(job) == ["/work/used.out", "/work/typed.out"]


class TestTheScanAnswersFromOneListdir:
    """``find_log`` probes ~170 conventional spellings per job, which over a
    6,600-job history is more than a million ``stat`` calls for questions one
    ``listdir`` per directory already answers -- the difference between a
    cross-job pass being affordable behind a keypress and not.
    """

    def _job(self, tmp_path, **kw):
        base = {
            "JobID": "60",
            "JobName": "train",
            "User": "me",
            "State": "FAILED",
            "ElapsedRaw": "60",
            "WorkDir": str(tmp_path),
        }
        base.update(kw)
        return parse(row(**base))[0]

    def test_a_missing_log_suffixed_name_is_answered_without_a_stat(self, tmp_path, monkeypatch):
        """The listing settles absence, which is where the million calls went.

        ~170 spellings are probed per job and nearly all of them miss, so it is the
        misses that have to stay free. This asserted that a *hit* skipped the stat
        too, which is what let a dangling symlink count as a confirmed log: a name
        is in the listing whether or not it resolves.
        """
        (tmp_path / "slurm-60.out").write_text("out\n")
        scan = logs.Scan()
        monkeypatch.setattr(os.path, "isfile", lambda p: pytest.fail("should not stat"))
        assert scan.exists(str(tmp_path / "slurm-99.out")) is False

    def test_a_hit_is_confirmed_and_the_stat_is_cached(self, tmp_path, monkeypatch):
        """One stat per hit, not per probe -- and only the first time it is asked."""
        (tmp_path / "slurm-60.out").write_text("out\n")
        scan = logs.Scan()
        assert scan.exists(str(tmp_path / "slurm-60.out")) is True
        calls = []
        real = os.path.isfile
        monkeypatch.setattr(os.path, "isfile", lambda p: calls.append(p) or real(p))
        for _ in range(5):
            assert scan.exists(str(tmp_path / "slurm-60.out")) is True
        assert calls == [], "the confirmed answer should come from the cache"

    def test_a_dangling_symlink_is_not_a_log(self, tmp_path):
        """A purged scratch target leaves the name in the listing but nothing behind it.

        Reported as a certain match, it shadowed the readable file beside it: the
        report named a log path and then said no log was found to explain the exit.
        """
        (tmp_path / "slurm-60.err").symlink_to(tmp_path / "gone.err")
        (tmp_path / "slurm-60.out").write_text("the real one\n")
        job = self._job(tmp_path, StdErr=str(tmp_path / "slurm-60.err"))
        assert logs.Scan().exists(str(tmp_path / "slurm-60.err")) is False
        assert logs.find_log_by_name(job) == str(tmp_path / "slurm-60.out")
        assert logs.find_log(job) == str(tmp_path / "slurm-60.out")

    def test_a_recorded_path_with_no_log_suffix_still_resolves(self, tmp_path):
        """``--output=/scratch/me/mylog`` has no suffix, so the directory listing
        cannot speak for it and it has to be stat'd."""
        target = tmp_path / "mylog"
        target.write_text("boom\n")
        job = self._job(tmp_path, StdErr=str(target))
        assert logs.Scan().exists(str(target)) is True
        assert logs.find_log_by_name(job) == str(target)

    def test_one_directory_is_listed_once_however_many_jobs_ask(self, tmp_path, monkeypatch):
        (tmp_path / "slurm-1.out").write_text("x\n")
        calls = []
        real = os.listdir
        monkeypatch.setattr(os, "listdir", lambda d: calls.append(d) or real(d))
        scan = logs.Scan()
        jobs = [self._job(tmp_path, JobID=str(n)) for n in range(1, 6)]
        for job in jobs:
            logs.find_log_by_name(job, scan=scan)
        assert len(set(calls)) == len(calls), "a directory was listed twice"

    def test_the_digit_index_delimits_so_a_longer_number_does_not_match(self, tmp_path):
        (tmp_path / "1060-train.out").write_text("x\n")
        (tmp_path / "run-60.out").write_text("mine\n")
        index = logs.Scan().by_digits(str(tmp_path))
        assert index["1060"] == ["1060-train.out"]
        assert index["60"] == ["run-60.out"]


class TestLogNamesCarryingTheJobId:
    """``--output=%x-%j.out`` is the commonest convention there is, and no fixed
    pattern list can hold it: the id is present but the rest of the name is the
    job's. Measured on a real history, 20 jobs whose log sat in a searched directory
    under their own id were sent to the timing guess instead."""

    def _job(self, tmp_path, **kw):
        base = {
            "JobID": "60",
            "JobName": "train",
            "User": "me",
            "State": "FAILED",
            "Start": "2026-07-01T10:00:00",
            "End": "2026-07-01T11:00:00",
            "ElapsedRaw": "3600",
            "WorkDir": str(tmp_path),
        }
        base.update(kw)
        return parse(row(**base))[0]

    def test_the_name_and_id_convention_is_found(self, tmp_path):
        target = tmp_path / "sft-h100-60.out"
        target.write_text("boom\n")
        assert logs.find_log_by_id(self._job(tmp_path)) == str(target)

    def test_it_counts_as_certain_not_a_guess(self, tmp_path):
        (tmp_path / "sft-h100-60.out").write_text("boom\n")
        _path, _text, inferred = logs.load_for(self._job(tmp_path))
        assert inferred is False

    def test_the_id_must_be_delimited_so_a_longer_number_does_not_match(self, tmp_path):
        (tmp_path / "1060-train.out").write_text("not mine\n")
        assert logs.find_log_by_id(self._job(tmp_path)) is None

    def test_stderr_wins_when_both_carry_the_id(self, tmp_path):
        (tmp_path / "run-60.out").write_text("out\n")
        (tmp_path / "run-60.err").write_text("err\n")
        assert logs.find_log_by_id(self._job(tmp_path)) == str(tmp_path / "run-60.err")

    def test_an_array_element_prefers_its_own_id_over_the_master(self, tmp_path):
        (tmp_path / "train-60.out").write_text("master\n")
        (tmp_path / "train-60_4.out").write_text("mine\n")
        job = self._job(tmp_path, JobID="60_4", JobIDRaw="73")
        assert logs.find_log_by_id(job) == str(tmp_path / "train-60_4.out")

    def test_a_recorded_path_still_outranks_it(self, tmp_path):
        (tmp_path / "train-60.out").write_text("by id\n")
        recorded = tmp_path / "recorded.err"
        recorded.write_text("recorded\n")
        job = self._job(tmp_path, StdErr=str(recorded))
        assert logs.find_log_by_name(job) == str(recorded)


class TestTimingIsNotLetLoose:
    """Two measured failure modes of an mtime match, both fixed here: an unrelated
    file in the submit directory, and one file claimed by several sibling runs."""

    def _job(self, tmp_path, jid="60", start="10:00:00", end="11:00:00", name="train"):
        return parse(
            row(
                JobID=jid,
                JobName=name,
                User="me",
                State="FAILED",
                Start="2026-07-01T" + start,
                End="2026-07-01T" + end,
                ElapsedRaw="3600",
                WorkDir=str(tmp_path),
            )
        )[0]

    def _at(self, path, when):
        stamp = datetime.fromisoformat("2026-07-01T" + when).timestamp()
        os.utime(path, (stamp, stamp))

    def test_an_unrelated_file_in_the_submit_directory_is_refused(self, tmp_path):
        """The real case: a backup script's log being appended to in $HOME, whose
        mtime therefore lands in whichever job window it currently falls in."""
        stray = tmp_path / "openclaw_backup_verify.log"
        stray.write_text("nothing to do with the job\n")
        self._at(stray, "10:59:00")
        assert logs.find_log_by_time(self._job(tmp_path)) is None

    def test_the_same_file_inside_a_log_directory_is_accepted(self, tmp_path):
        """A report/ directory exists to hold job output, so mtime is evidence
        there in a way it is not in a home directory."""
        (tmp_path / "report").mkdir()
        log = tmp_path / "report" / "144-train.out"
        log.write_text("output\n")
        self._at(log, "10:59:00")
        assert logs.find_log_by_time(self._job(tmp_path)) == str(log)

    def test_a_stray_is_accepted_once_the_user_names_its_directory(self, tmp_path):
        stray = tmp_path / "whatever.log"
        stray.write_text("mine after all\n")
        self._at(stray, "10:59:00")
        job = self._job(tmp_path)
        assert logs.find_log_by_time(job) is None
        assert logs.find_log_by_time(job, extra_dirs=[str(tmp_path)]) == str(stray)

    def test_slurms_own_default_name_is_related_enough(self, tmp_path):
        log = tmp_path / "slurm-99999.out"
        log.write_text("out\n")
        self._at(log, "10:59:00")
        assert logs.find_log_by_time(self._job(tmp_path)) == str(log)

    def test_a_name_carrying_the_job_name_is_related_enough(self, tmp_path):
        log = tmp_path / "144-train.out"
        log.write_text("out\n")
        self._at(log, "10:59:00")
        assert logs.find_log_by_time(self._job(tmp_path)) == str(log)

    def test_one_file_is_not_handed_to_two_jobs(self, tmp_path):
        """Measured: 51 of 296 timing matches pointed at a file another job also
        claimed -- one was the nearest match for four runs of the same workload."""
        (tmp_path / "report").mkdir()
        log = tmp_path / "report" / "76-train.out"
        log.write_text("output\n")
        self._at(log, "11:00:00")
        near = self._job(tmp_path, jid="60", end="11:00:30")
        far = self._job(tmp_path, jid="61", end="10:50:00")
        assigned = logs.assign_logs([far, near])
        assert assigned["60"] == (str(log), True)
        assert assigned["61"] == (None, False)

    def test_the_loser_falls_through_to_its_own_next_candidate(self, tmp_path):
        (tmp_path / "report").mkdir()
        shared = tmp_path / "report" / "76-train.out"
        shared.write_text("shared\n")
        self._at(shared, "11:00:00")
        other = tmp_path / "report" / "75-train.out"
        other.write_text("other\n")
        self._at(other, "10:50:00")
        near = self._job(tmp_path, jid="60", end="11:00:10")
        second = self._job(tmp_path, jid="61", end="10:50:20")
        assigned = logs.assign_logs([near, second])
        assert assigned["60"][0] == str(shared)
        assert assigned["61"][0] == str(other)

    def test_the_assignment_does_not_depend_on_the_order_jobs_arrive(self, tmp_path):
        (tmp_path / "report").mkdir()
        log = tmp_path / "report" / "76-train.out"
        log.write_text("output\n")
        self._at(log, "11:00:00")
        a = self._job(tmp_path, jid="60", end="11:00:05")
        b = self._job(tmp_path, jid="61", end="11:00:40")
        assert logs.assign_logs([a, b]) == logs.assign_logs([b, a])

    def test_a_name_match_is_exempt_because_two_jobs_can_share_an_output_path(self, tmp_path):
        """``--output=night-placeholder.out`` reused by every run of a chain is a
        real thing people do. There the name is evidence, not a coincidence."""
        shared = tmp_path / "slurm-60.out"
        shared.write_text("out\n")
        one = self._job(tmp_path, jid="60")
        two = parse(
            row(
                JobID="61",
                JobName="train",
                User="me",
                State="FAILED",
                Start="2026-07-01T10:00:00",
                End="2026-07-01T11:00:00",
                ElapsedRaw="3600",
                WorkDir=str(tmp_path),
                StdOut=str(shared),
            )
        )[0]
        assigned = logs.assign_logs([one, two])
        assert assigned["60"] == (str(shared), False)
        assert assigned["61"] == (str(shared), False)

    def test_a_caller_can_exclude_paths_it_has_already_used(self, tmp_path):
        (tmp_path / "report").mkdir()
        log = tmp_path / "report" / "76-train.out"
        log.write_text("output\n")
        self._at(log, "11:00:00")
        job = self._job(tmp_path)
        assert logs.find_log_by_time(job) == str(log)
        assert logs.find_log_by_time(job, taken={str(log)}) is None


class TestCommentLogPaths:
    """Works on every Slurm, which is the point: below 21.08 nothing else does."""

    def _job(self, comment, **kw):
        base = {
            "JobID": "60",
            "JobName": "train",
            "User": "me",
            "State": "FAILED",
            "ElapsedRaw": "60",
            "WorkDir": "/work",
            "Comment": comment,
        }
        base.update(kw)
        return parse(row(**base))[0]

    def test_an_absolute_log_path_is_read(self):
        job = self._job("/home/me/report/144-train.out")
        assert logs.recorded_paths(job) == ["/home/me/report/144-train.out"]

    def test_free_text_is_not_resolved_into_a_candidate(self):
        """The field is used for all sorts of things. Joining "rerun of 4412"
        onto the work directory would invent a path out of a sentence."""
        assert logs.recorded_paths(self._job("rerun of 4412")) == []

    def test_a_relative_path_is_not_trusted_either(self):
        assert logs.recorded_paths(self._job("report/144-train.out")) == []

    def test_a_path_that_is_not_a_log_is_left_alone(self):
        assert logs.recorded_paths(self._job("/home/me/checkpoint.pt")) == []

    def test_it_loses_to_what_slurm_itself_recorded(self):
        job = self._job("/home/me/stashed.out", StdErr="/work/real.err")
        assert logs.recorded_paths(job) == ["/work/real.err", "/home/me/stashed.out"]


class TestSqueueReconciliation:
    @staticmethod
    def _recorder(fail_on_me=False):
        calls = []

        def runner(args):
            calls.append(args)
            if fail_on_me and "--me" in args:
                raise SacctError("squeue: unrecognized option '--me'")
            return "123\n456\n"

        return runner, calls

    def test_the_fallback_asks_for_one_user_not_the_whole_cluster(self, monkeypatch):
        """`--me` arrived in Slurm 20.02. The old fallback dropped the filter
        entirely, which on a busy cluster returns every queued job there is."""
        monkeypatch.setattr(sacct_mod.getpass, "getuser", lambda: "alice")
        runner, calls = self._recorder(fail_on_me=True)

        assert live_job_ids(runner=runner, user="alice") == {"123", "456"}
        assert calls[1] == ["squeue", "--noheader", "-u", "alice", "--format=%i"]

    def test_another_users_records_are_never_checked_against_my_queue(self, monkeypatch):
        """`--me` used to be tried first unconditionally, so on every Slurm since
        20.02 -- all of them -- `-u alice` reconciled alice's RUNNING records
        against *my* queue and the `user` argument was dead. Only the fallback
        branch had a test, so it read as working."""
        monkeypatch.setattr(sacct_mod.getpass, "getuser", lambda: "bob")
        runner, calls = self._recorder()

        assert live_job_ids(runner=runner, user="alice") == {"123", "456"}
        assert calls == [["squeue", "--noheader", "-u", "alice", "--format=%i"]]
        assert not any("--me" in c for c in calls)

    def test_my_own_query_still_prefers_me(self, monkeypatch):
        monkeypatch.setattr(sacct_mod.getpass, "getuser", lambda: "bob")
        runner, calls = self._recorder()

        assert live_job_ids(runner=runner) == {"123", "456"}
        assert calls == [["squeue", "--noheader", "--me", "--format=%i"]]

    def test_all_users_asks_the_whole_cluster_on_purpose(self, monkeypatch):
        monkeypatch.setattr(sacct_mod.getpass, "getuser", lambda: "bob")
        runner, calls = self._recorder()

        assert live_job_ids(runner=runner, all_users=True) == {"123", "456"}
        assert calls == [["squeue", "--noheader", "--format=%i"]]

    def test_no_squeue_at_all_returns_none_so_nothing_is_guessed(self):
        def broken(_args):
            raise SacctError("no squeue")

        assert live_job_ids(runner=broken, user="alice") is None


class TestValueShapesAcrossReleases:
    def test_reqmem_zero_is_not_a_zero_byte_ceiling(self):
        assert parse_bytes("0n") in (0, None)
        job = parse(row(JobID="70", JobName="w", State="COMPLETED", ReqMem="0n"))[0]
        assert job.mem_limit_bytes is None

    def test_units_are_read_whichever_sacct_chose(self):
        """Default output converts to the largest unit; --noconvert and --units
        do not. All three shapes reach this parser."""
        assert parse_bytes("204800M") == 200 * 1024**2 * 1024
        assert parse_bytes("200G") == 200 * 1024**3
        assert parse_bytes("209715200K") == 200 * 1024**3
        assert parse_bytes("1.50G") == int(1.5 * 1024**3)

    def test_sentinels_are_matched_whatever_their_case(self):
        job = parse(
            row(
                JobID="71",
                JobName="w",
                State="COMPLETED",
                Timelimit="UNLIMITED",
                Reason="none",
                End="Unknown",
            )
        )[0]
        assert job.timelimit is None
        assert job.reason == ""

    def test_a_partition_limit_timelimit_is_not_a_duration(self):
        job = parse(row(JobID="72", JobName="w", State="PENDING", Timelimit="Partition_Limit"))[0]
        assert job.timelimit is None

    def test_a_heterogeneous_job_component_keys_to_its_own_component(self):
        text = "\n".join(
            [
                row(JobID="80+0", JobName="w", State="COMPLETED", ElapsedRaw="60"),
                row(JobID="80+0.0", JobName="s", State="COMPLETED", TotalCPU="00:01:00"),
                row(JobID="80+1", JobName="w", State="COMPLETED", ElapsedRaw="60"),
            ]
        )
        jobs = parse(text)
        assert [j.job_id for j in jobs] == ["80+0", "80+1"]
        assert len(jobs[0].steps) == 1 and not jobs[1].steps

    def test_an_array_element_keeps_its_task_index(self):
        text = "\n".join(
            [
                row(JobID="90_3", JobName="w", State="COMPLETED", ElapsedRaw="60"),
                row(JobID="90_3.batch", JobName="batch", State="COMPLETED", TotalCPU="00:01:00"),
            ]
        )
        jobs = parse(text)
        assert jobs[0].job_id == "90_3"
        assert jobs[0].total_cpu == 60.0

    def test_a_pending_array_expression_is_not_treated_as_a_finished_job(self):
        job = parse(row(JobID="91_[5-9]", JobName="w", State="PENDING"))[0]
        assert job.open_ended, "no End and a non-terminal state: excluded from totals"


class TestEndToEndOnASimulatedModernCluster:
    """One replay of a cluster this code has never run on.

    Slurm 24.05, `jobacct_gather/cgroup`, `AutoDetect=nvml`, typed GRES, recorded
    StdErr, four nodes, `Planned` instead of `Reserved`. The unit tests above each
    pin one difference; this drives the whole pipeline through all of them at once,
    because the failure mode being guarded against is a query that comes back empty
    or a number that is quietly per-allocation.
    """

    MODERN = """\
SLURM_VERSION           = 24.05.4
JobAcctGatherType       = jobacct_gather/cgroup
AccountingStorageType   = accounting_storage/slurmdbd
AccountingStorageTRES   = cpu,mem,node,billing,gres/gpu,gres/gpuutil,gres/gpumem
"""

    def _sacct(self):
        # What `sacct --helpformat` prints on 24.05: Planned, not Reserved; StdOut,
        # StdErr and SubmitLine present; AllocGRES and ReqGRES long gone.
        available = (_fields_lower(_FIELDS) - {"reserved", "allocgres", "reqgres"}) | {"planned"}
        probe = " ".join(sorted(available))
        fields = resolve_fields(available)

        def build(values):
            return SAFE_DELIMITER.join(str(values.get(name, "")) for name in fields)

        rows = [
            build(
                {
                    "JobID": "884411",
                    "JobName": "sft-h100-x",
                    "User": "dana",
                    "Account": "ml",
                    "Cluster": "aurora",
                    "Partition": "gpu",
                    "State": "COMPLETED",
                    "ExitCode": "0:0",
                    "Submit": "2026-06-01T09:00:00",
                    "Start": "2026-06-01T09:05:00",
                    "End": "2026-06-01T11:05:00",
                    "ElapsedRaw": "7200",
                    "TimelimitRaw": "180",
                    "Planned": "00:05:00",
                    # No n/c suffix: 21.08 changed ReqMem to mirror ReqTRES, and
                    # the figure totals the allocation.
                    "ReqMem": "512G",
                    "NNodes": "4",
                    "AllocCPUS": "128",
                    # `|` is the OR operator; it reaches the column verbatim.
                    "Constraints": "h100|a100",
                    "AllocTRES": "cpu=128,gres/gpu=16,gres/gpu:h100=16,mem=512G,node=4",
                    "NodeList": "unit[0-1]rack[0-1]",
                    "StdErr": "/scratch/dana/logs/%x-%A.err",
                    "SubmitLine": "sbatch --gpus=16 --constraint=h100|a100 run.sh",
                    "Flags": "SchedBackfill",
                }
            ),
            build(
                {
                    "JobID": "884411.batch",
                    "JobName": "batch",
                    "State": "COMPLETED",
                    "ElapsedRaw": "7200",
                    "TotalCPU": "8-00:00:00",
                    "UserCPU": "7-20:00:00",
                    "SystemCPU": "0-04:00:00",
                    "CPUTimeRAW": "921600",
                    "NTasks": "16",
                    "MaxRSS": "104857600K",
                    "AveRSS": "104857600K",
                    "TRESUsageInAve": "cpu=8-00:00:00,gres/gpumem=68000M,gres/gpuutil=91,mem=100G",
                    "TRESUsageInMax": "gres/gpumem=72000M,gres/gpuutil=99,mem=100G",
                    "TRESUsageInTot": "fs/disk=500000000000",
                    "TRESUsageOutTot": "fs/disk=90000000000",
                }
            ),
        ]

        def runner(args):
            if "--helpformat" in args:
                return probe
            assert any(a.startswith("--delimiter") for a in args), args
            return "\n".join(rows)

        return Sacct(runner=runner, probe=probe)

    @pytest.fixture
    def job(self, monkeypatch):
        monkeypatch.setattr("slurmpast.site._CACHE", [])
        site(runner=lambda _a: self.MODERN, refresh=True)
        return self._sacct().jobs(["884411"])[0]

    def test_the_query_returns_the_record_at_all(self, job):
        assert job.job_id == "884411"
        assert job.state == "COMPLETED"
        assert job.elapsed == 7200.0

    def test_queue_wait_survives_the_rename(self, job):
        assert job.queue_wait == 300.0

    def test_the_pipe_in_constraints_did_not_shift_the_columns(self, job):
        assert job.constraints == "h100|a100"
        assert job.alloc_tres == "cpu=128,gres/gpu=16,gres/gpu:h100=16,mem=512G,node=4"
        assert job.cpu_count == 128

    def test_the_four_node_hostlist_expands(self, job):
        assert expand_nodelist(job.node_list) == [
            "unit0rack0",
            "unit0rack1",
            "unit1rack0",
            "unit1rack1",
        ]

    def test_gpus_and_gpu_hours(self, job):
        assert job.gpu_count == 16
        assert job.gpu_hours == pytest.approx(32.0)

    def test_gpu_busy_ness_is_a_measurement_here(self, job):
        assert job.gpu_utilization == pytest.approx(0.91)
        assert job.gpu_mem_peak_bytes == 72000 * 1024**2

    def test_memory_is_per_node_not_per_allocation(self, job):
        assert job.mem_limit_total_bytes == 512 * 1024**3
        assert job.mem_limit_bytes == 128 * 1024**3
        assert job.max_rss == 100 * 1024**3
        assert job.mem_utilization == pytest.approx(100 / 128.0)

    def test_cores_are_per_task(self, job):
        assert job.task_count == 16
        assert job.cpus_per_task == 8

    def test_the_recorded_log_path_is_expanded_from_the_pattern(self, job):
        assert logs.recorded_paths(job) == ["/scratch/dana/logs/sft-h100-x-884411.err"]

    def test_the_cgroup_wording_replaces_the_process_tree_warning(self, job):
        assert job.max_rss < job.mem_limit_bytes
        assert "cgroup peak" in maxrss_caveat()
        assert "sums RSS" not in maxrss_caveat()

    def test_the_whole_detail_screen_renders(self, job):
        from slurmpast.diagnose import diagnose
        from slurmpast.report import Style, render_job

        text, verdict = render_job(job, style=Style(enabled=False))
        assert "884411" in text
        assert "h100|a100" in text
        assert "91.0%" in text, "recorded GPU utilization should reach the screen"
        assert "128.0 GiB per node (512.0 GiB over 4)" in text
        assert "sbatch --gpus=16" in text
        assert "not gathered by this cluster" not in text
        # A healthy run: nothing critical, and the backfill note is informational.
        assert not [f for f in diagnose(job).findings if f.severity == "critical"]

    def test_sizing_advice_is_in_the_units_the_flags_take(self, job):
        from slurmpast.sizing import recommend

        runs = [job._replace(job_id="884411_%d" % i) for i in range(5)]
        advice = {a.flag: a for a in recommend(runs)}
        assert advice["--mem"].requested == "128.0 GiB"
        assert advice["--cpus-per-task"].requested == "8"
        assert "per task" in advice["--cpus-per-task"].basis

    def test_the_rollup_ranks_it_as_gpu_work(self, job):
        from slurmpast.index import History

        history = History([job])
        group = history.groups[0]
        assert group.kind == "gpu"
        assert group.gpu_hours == pytest.approx(32.0)
        assert group.problems == 0


class TestTresParsingIsExact:
    def test_a_key_is_not_matched_by_prefix(self):
        """`gres/gpumem` must not be read as `gres/gpu`."""
        assert model._tres_int("gres/gpumem=36266,cpu=4", "gres/gpu") is None

    def test_a_typed_key_is_not_confused_with_another_resource(self):
        assert model._typed_tres_total("gres/gpumem:x=5", "gres/gpu") is None

    def test_a_percentage_is_read_as_a_float(self):
        assert model._tres_float("gres/gpuutil=87.5", "gres/gpuutil") == 87.5
        assert model._tres_float("gres/gpuutil=nan-ish", "gres/gpuutil") is None
        assert model._tres_float("", "gres/gpuutil") is None


class TestHeterogeneousJobFilenames:
    """`%j` is a job number, so Slurm never wrote a `+` into a filename.

    sacct displays `500+1` for a heterogeneous component while JobIDRaw carries the
    plain allocation number. Consulting JobIDRaw only for array tasks sent the
    display form through, so the recorded path expanded to `slurm-500+1.err` and
    could not match anything -- for a job whose output location was known exactly.
    """

    def _het(self, tmp_path, pattern):
        return parse(
            row(
                JobID="500+1",
                JobIDRaw="501",
                JobName="het",
                State="FAILED",
                ElapsedRaw="60",
                WorkDir=str(tmp_path),
                StdErr=pattern,
            )
        )[0]

    def test_the_plain_allocation_number_is_substituted(self, tmp_path):
        job = self._het(tmp_path, str(tmp_path / "slurm-%j.err"))
        assert logs.expand_pattern(job.std_err, job) == str(tmp_path / "slurm-501.err")

    def test_the_recorded_path_now_matches_the_file_on_disk(self, tmp_path):
        (tmp_path / "slurm-501.err").write_text("boom\n")
        job = self._het(tmp_path, str(tmp_path / "slurm-%j.err"))
        assert logs.find_log_by_name(job) == str(tmp_path / "slurm-501.err")

    def test_an_ordinary_job_is_unaffected(self, tmp_path):
        job = parse(
            row(
                JobID="500",
                JobIDRaw="500",
                JobName="plain",
                State="FAILED",
                ElapsedRaw="60",
                WorkDir=str(tmp_path),
                StdErr=str(tmp_path / "slurm-%j.err"),
            )
        )[0]
        assert logs.expand_pattern(job.std_err, job) == str(tmp_path / "slurm-500.err")


class TestTheArrayMasterIdIsOfferedLast:
    """`--output=%x-%A.out` writes one shared file per array and no `%a`.

    `job_identifiers`' docstring promises the master's bare `60` as a third,
    weakest identifier, but `base_job_id` strips `.step` and `+het` and not
    `_task`, so it returned `60_4` unchanged -- a duplicate that got dropped.
    """

    def _element(self, tmp_path):
        return parse(
            row(
                JobID="60_4",
                JobIDRaw="73",
                JobName="train",
                State="FAILED",
                ElapsedRaw="60",
                WorkDir=str(tmp_path),
            )
        )[0]

    def test_all_three_identifiers_are_offered(self, tmp_path):
        assert logs.job_identifiers(self._element(tmp_path)) == ["60_4", "73", "60"]

    def test_a_shared_array_log_is_found(self, tmp_path):
        (tmp_path / "train-60.out").write_text("shared\n")
        assert logs.find_log_by_id(self._element(tmp_path)) == str(tmp_path / "train-60.out")

    def test_a_plain_job_offers_no_spurious_third(self, tmp_path):
        job = parse(row(JobID="61", JobIDRaw="61", JobName="t", State="FAILED", ElapsedRaw="60"))[0]
        assert logs.job_identifiers(job) == ["61"]


class TestTheListingIsIndexedOnceNotPerProbe:
    """The fast path had an O(n) test inside it.

    ``exists`` asked ``name not in set(self.entries(directory))``. The listing was
    cached; the *set built from it* was not, so the membership test this class
    exists to make constant-time was linear in the directory instead -- ~84 times
    per job. Measured against a 13,000-file log directory: 16.6 us per probe against
    2.8 cached, which over the 6,600-job history the class docstring cites is about
    9 s of pure rebuilding behind an interactive keypress. ``by_digits`` already
    caches its derived index per directory; this was the one that did not.
    """

    def test_one_listdir_and_one_index_per_directory(self, tmp_path, monkeypatch):
        for index in range(50):
            (tmp_path / ("run-%03d.out" % index)).write_text("x\n")
        scan = logs.Scan()
        listings = []
        real = os.listdir
        monkeypatch.setattr(os, "listdir", lambda p: listings.append(p) or real(p))
        for index in range(200):
            scan.exists(str(tmp_path / ("slurm-%d.out" % index)))
        assert len(listings) == 1, "the listing itself was already cached"
        # And the index derived from it, which is the part that was not.
        assert list(scan._names) == [str(tmp_path)]

    def test_the_answers_are_the_same_ones(self, tmp_path):
        """A cache is only worth having if it cannot change what is reported."""
        (tmp_path / "slurm-60.out").write_text("out\n")
        scan = logs.Scan()
        assert scan.exists(str(tmp_path / "slurm-60.out")) is True
        assert scan.exists(str(tmp_path / "slurm-61.out")) is False
        assert scan.exists(str(tmp_path / "slurm-60.out")) is True

    def test_the_cost_does_not_grow_with_the_directory(self, tmp_path, monkeypatch):
        """The invariant behind the measurement, counted rather than timed so a
        loaded machine cannot make it flaky: probing a 2,000-name directory builds
        the same one index a 50-name one does."""
        built = []
        monkeypatch.setattr(logs.Scan, "_names_in", _counting_names_in(built))
        for size in (50, 2000):
            directory = tmp_path / str(size)
            directory.mkdir()
            for index in range(size):
                (directory / ("run-%05d.out" % index)).write_text("x\n")
            scan = logs.Scan()
            before = len(built)
            for index in range(100):
                scan.exists(str(directory / ("slurm-%d.out" % index)))
            assert len(built) - before == 1, "one set per directory, whatever its size"


def _counting_names_in(log):
    """`Scan._names_in`, recording each directory whose set it actually builds."""
    original = logs.Scan._names_in

    def counted(self, directory):
        if directory not in self._names:
            log.append(directory)
        return original(self, directory)

    return counted


class TestATruncatedStateMeansWhatItSays:
    """`OUT_OF_ME+` is sacct's column-truncated `OUT_OF_MEMORY`.

    It was recognised in exactly one place -- `sacct._TERMINAL_STATES` -- and
    appeared nowhere else in the codebase, so a record carrying it was correctly
    treated as closed and then mis-handled by everything downstream: counted as
    neither a failure nor a completion, given no finding, and invisible to both the
    memory-bisection detector and the `--mem` floor in `sizing.memory_advice`.

    Whichever query produced the truncation, one spelling of one state cannot mean
    two things in one codebase, so it is folded at the parse boundary -- the same
    job `_ALIASES` does for a field Slurm renamed.
    """

    COMMON = {
        "JobName": "tok",
        "Partition": "test",
        "User": "me",
        "ExitCode": "0:125",
        "End": "2026-01-01T00:10:00",
        "Elapsed": "00:10:00",
        "Timelimit": "01:00:00",
        "AllocTRES": "cpu=8,mem=16G,node=1",
        "NodeList": "n1",
        "ReqCPUS": "8",
    }

    def _jobs(self, state, count=1, first=100):
        return parse(
            "\n".join(row(JobID=str(first + i), State=state, **self.COMMON) for i in range(count))
        )

    def test_the_truncated_spelling_reads_as_the_full_one(self):
        job = self._jobs("OUT_OF_ME+")[0]
        assert job.state == "OUT_OF_MEMORY"
        assert job.base_state == "OUT_OF_MEMORY"
        assert job.failed
        assert not job.open_ended

    def test_it_draws_the_same_finding(self):
        from slurmpast.diagnose import diagnose

        truncated = {f.code for f in diagnose(self._jobs("OUT_OF_ME+")[0]).findings}
        full = {f.code for f in diagnose(self._jobs("OUT_OF_MEMORY")[0]).findings}
        assert "host-oom" in truncated
        assert truncated == full

    def test_the_cross_run_detectors_see_it(self):
        from slurmpast.patterns import find_memory_search
        from slurmpast.sizing import memory_advice

        # Four identical records, so the detector names it `memory-unchanged`
        # rather than `memory-search` -- the request never moved. Which of the two
        # is beside the point here: this test is about the truncated spelling being
        # *visible* to the cross-run detectors at all, and pinning the code made it
        # over-specified.
        jobs = self._jobs("OUT_OF_ME+", count=4)
        found = find_memory_search(jobs)
        assert len(found) == 1, [f.code for f in found]
        assert "4 OOM kills" in found[0].evidence
        advice = memory_advice(jobs)
        assert advice.verdict == "raise"
        assert "4 OOM kills" in advice.observed

    def test_the_cancelled_suffix_survives_the_fold(self):
        """`Job.state` carries sacct's `by <uid>` and `base_state` drops it; both
        are read, so folding must not eat either."""
        from slurmpast.sacct import _canonical_state

        assert _canonical_state("CANCELLED by 1234") == "CANCELLED by 1234"
        assert _canonical_state("OUT_OF_ME+ by 1234") == "OUT_OF_MEMORY by 1234"

    def test_an_unfamiliar_state_passes_through_untouched(self):
        """The control. Only the one spelling already named in this module is
        folded -- nothing guesses at what an unknown `+` was cut from."""
        from slurmpast.sacct import _canonical_state

        for state in ("COMPLETED", "REVOKED", "SPECIAL_EXIT", "SOME_NEW+", ""):
            assert _canonical_state(state) == state


class TestTheToolsDeclareWhatTheyImport:
    """`tools/demo_gif.py` said a dev install brought in what it needs. It did not.

    Its own docstring is the standard it failed: "A build step nobody can run is a
    build step that does not happen" -- which is why it replaced the vhs tape in the
    first place, and it then reproduced the same failure in Python. `cairosvg` and
    `pillow` were in NO extra, so `pip install -e ".[dev]"` -- what CI runs and what
    the README implies for a contributor -- left the command the README prints
    raising ModuleNotFoundError.
    """

    @staticmethod
    def _project():
        """``(repo root, the [project] table)``.

        ``tomllib`` is stdlib from 3.11 and this package declares
        ``requires-python = ">=3.10"``, so on the floor version this test -- whose
        subject is precisely "declare what you import" -- did not declare what it
        imports. Local gates run on one interpreter and could not see it; CI's
        py3.10 and oldest-Textual jobs both failed on it. ``tomli`` is the
        conventional backfill and is now in the dev extra, guarded by a marker so
        3.11+ does not install it.
        """
        import pathlib

        try:
            import tomllib
        except ModuleNotFoundError:  # Python 3.10
            import tomli as tomllib

        root = pathlib.Path(__file__).resolve().parent.parent
        return root, tomllib.loads((root / "pyproject.toml").read_text())["project"]

    @staticmethod
    def _third_party(path, known_local):
        """Top-level modules ``path`` imports that are neither stdlib nor local."""
        import ast
        import sys

        stdlib = set(sys.stdlib_module_names)
        found = set()
        for node in ast.walk(ast.parse(path.read_text())):
            roots = []
            if isinstance(node, ast.Import):
                roots = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots = [node.module.split(".")[0]]
            for root in roots:
                if root not in stdlib and root not in known_local:
                    found.add(root)
        return found

    def test_every_third_party_import_in_tools_is_declared(self):
        root, project = self._project()
        declared = set()
        for spec in list(project.get("dependencies", [])):
            declared.add(spec.split(">")[0].split("<")[0].split("=")[0].strip().lower())
        for group in project.get("optional-dependencies", {}).values():
            for spec in group:
                declared.add(spec.split(">")[0].split("<")[0].split("=")[0].strip().lower())
        # `PIL` is the import name of the `pillow` distribution.
        aliases = {"pil": "pillow"}
        undeclared = {}
        for path in sorted((root / "tools").glob("*.py")):
            imports = self._third_party(path, known_local={"slurmpast"})
            missing = sorted(
                name for name in imports if aliases.get(name.lower(), name.lower()) not in declared
            )
            if missing:
                undeclared[path.name] = missing
        assert not undeclared, "imported by tools/ and declared nowhere: %s" % undeclared

    def test_the_gif_generator_names_its_extra(self):
        """And the extra it names has to exist, with both packages in it."""
        root, project = self._project()
        source = (root / "tools" / "demo_gif.py").read_text()
        extras = project["optional-dependencies"]
        assert 'pip install -e ".[assets]"' in source, "the docstring should name the extra"
        assert "assets" in extras, extras.keys()
        names = {s.split(">")[0].split("=")[0].strip().lower() for s in extras["assets"]}
        assert {"cairosvg", "pillow"} <= names, names
        # And it no longer claims `dev` is enough.
        assert "what a dev install already brings in" not in source

    def test_the_readme_names_the_install_step_too(self):
        """The README is where a contributor reads the regenerate command, so the
        command there has to be the one that works on a clean checkout."""
        root, _ = self._project()
        readme = (root / "README.md").read_text()
        assert "tools/demo_gif.py" in readme
        line = next(ln for ln in readme.splitlines() if "tools/demo_gif.py" in ln)
        assert "[assets]" in line, line

    def test_the_screenshot_tool_needs_nothing_extra(self):
        """The control: `screenshots.py` really does run on a plain dev install, so
        the sweep above is distinguishing the two rather than flagging both."""
        root, _ = self._project()
        imports = self._third_party(root / "tools" / "screenshots.py", known_local={"slurmpast"})
        assert not (imports - {"textual", "rich"}), imports


class TestTheProseSpellsPunctuationOneWay:
    """``--ascii`` promises "ASCII instead of Unicode ... glyphs and punctuation".

    It keeps that promise by folding: ``render.ascii_fold`` maps each mark this
    codebase uses onto a one-cell ASCII stand-in, once, on the finished text of a
    view. A sentence that spells the mark in ASCII to begin with is invisible to
    that -- there is nothing to fold -- so it reads the same in both modes while
    everything around it changes, and it cannot be restyled later from one place.

    Seventeen user-facing sentences spelled the em dash ``--`` against thirty that
    spelled it ``—``, and `diagnose.py` did both inside one `Finding`:

        " Note MaxRSS reports %s against a %s per-node limit -- above the hard ..."
        "Raise --mem, or cut what multiplies per-worker footprint — workers, ..."

    Comments and docstrings are exempt and deliberately so: this repo writes them
    in ASCII, and none of them reaches a screen.
    """

    # `-- ` inside these is an option, not punctuation: `--mem`, `--time`, `-S`.
    MODULES = (
        "cli.py",
        "diagnose.py",
        "duration.py",
        "index.py",
        "logs.py",
        "model.py",
        "nodes.py",
        "patterns.py",
        "render.py",
        "report.py",
        "sacct.py",
        "site.py",
        "sizing.py",
        "tui.py",
    )

    @staticmethod
    def _output_literals(path):
        """Non-docstring string constants, i.e. the ones that can reach a screen."""
        import ast

        tree = ast.parse(path.read_text())
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

    def test_no_user_facing_sentence_writes_the_em_dash_in_ascii(self):
        root = pathlib.Path(__file__).resolve().parent.parent / "src" / "slurmpast"
        offenders = []
        for name in self.MODULES:
            for value in self._output_literals(root / name):
                # The dashboard's CSS is not prose and carries `/* -- */` comments.
                if "{" in value and "}" in value:
                    continue
                if " -- " in value:
                    offenders.append("%s: %r" % (name, value[:70]))
        assert not offenders, "spell it — so --ascii can fold it: %s" % "; ".join(offenders)

    def test_the_fold_actually_reaches_them(self):
        """The control, end to end: every mark in the rendered views has an ASCII
        stand-in, so ``--ascii`` output is ASCII and one cell wide per mark."""
        from slurmpast.demo import history
        from slurmpast.index import History
        from slurmpast.render import _ASCII_FOLD, ascii_fold
        from slurmpast.report import (
            Style,
            render_job,
            render_nodes,
            render_overview,
            render_patterns,
            render_sizing,
        )

        jobs = history()
        h = History(jobs)
        style = Style(enabled=False)

        def views(ascii_mode):
            return [
                render_overview(h, style=style, ascii_mode=ascii_mode),
                render_patterns(h, style=style, ascii_mode=ascii_mode),
                render_nodes(h, style=style, ascii_mode=ascii_mode),
                render_sizing(h, style=style, ascii_mode=ascii_mode),
            ] + [
                render_job(j, style=style, show_steps=True, no_logs=True, ascii_mode=ascii_mode)[0]
                for j in jobs
            ]

        for unicode_form, folded in zip(views(False), views(True), strict=True):
            assert folded.isascii(), [c for c in folded if not c.isascii()][:5]
            # One cell for one cell, which is what lets the fold run last -- after
            # the wrapping and the column fitting that measured those cells.
            assert len(folded) == len(unicode_form)
            # And the punctuation specifically: the glyph swaps above happen at
            # the drawing site, the marks are what `ascii_fold` is for, and after
            # it not one of them is left.
            left = [c for c in ascii_fold(unicode_form) if c in _ASCII_FOLD]
            assert not left, left[:5]

    def test_the_mark_is_the_one_the_codebase_uses(self):
        """Not a style opinion invented here: the em dash is what the prose already
        spells, by better than two to one, and it is in the fold table."""
        from slurmpast.render import _ASCII_FOLD

        root = pathlib.Path(__file__).resolve().parent.parent / "src" / "slurmpast"
        em = sum(
            value.count("—")
            for name in self.MODULES
            for value in self._output_literals(root / name)
        )
        assert em > 20, em
        assert _ASCII_FOLD["—"] == "-"


class TestNothingImportsPastTheDeclaredPythonFloor:
    """`requires-python = ">=3.10"`, and one test imported a module that arrived
    in 3.11.

    `TestTheToolsDeclareWhatTheyImport` reads `pyproject.toml` with `tomllib` --
    stdlib from 3.11 -- so the test whose subject is "declare what you import" did
    not, on the oldest interpreter this package claims to support. Four of its
    assertions died with `ModuleNotFoundError` in CI's py3.10 and oldest-Textual
    jobs, having passed every local gate: a local run is one interpreter, and this
    is the class of defect that costs nothing to catch and cannot be caught there.

    `sys.stdlib_module_names` is the *running* interpreter's, so it cannot answer
    "was this in 3.10". The table below is the alternative and is deliberately
    small: the stdlib additions between this floor and the newest version CI runs.
    A module missing from it is not a false pass -- CI still runs 3.10 -- it is one
    round-trip through CI instead of a local failure, which is what this exists to
    save.
    """

    # module -> the version it entered the stdlib.
    ADDED_IN = {
        "tomllib": (3, 11),
        "dbm.sqlite3": (3, 13),
        "annotationlib": (3, 14),
        "compression": (3, 14),
    }

    @classmethod
    def _floor(cls):
        import re

        root = pathlib.Path(__file__).resolve().parent.parent
        spec = re.search(
            r'requires-python\s*=\s*"[>=~^]*([\d.]+)"', (root / "pyproject.toml").read_text()
        )
        assert spec, "pyproject no longer declares requires-python"
        return tuple(int(part) for part in spec.group(1).split("."))

    @staticmethod
    def _guarded_imports(tree):
        """Names imported inside a `try:` -- a backfill, not an unguarded import."""
        import ast

        safe = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            for inner in ast.walk(node):
                if isinstance(inner, ast.Import):
                    safe.update(alias.name for alias in inner.names)
                elif isinstance(inner, ast.ImportFrom) and inner.module:
                    safe.add(inner.module)
        return safe

    def test_no_module_newer_than_the_floor_is_imported_unguarded(self):
        import ast

        floor = self._floor()
        late = {name: added for name, added in self.ADDED_IN.items() if added > floor}
        assert late, "the floor has moved past every module in the table; prune it"

        root = pathlib.Path(__file__).resolve().parent.parent
        offenders = []
        for path in sorted(
            list((root / "src" / "slurmpast").glob("*.py"))
            + list((root / "tests").glob("*.py"))
            + list((root / "tools").glob("*.py"))
        ):
            tree = ast.parse(path.read_text())
            guarded = self._guarded_imports(tree)
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names = [node.module]
                for name in names:
                    if name in late and name not in guarded:
                        offenders.append(
                            "%s:%d imports %s (stdlib from %s, floor is %s)"
                            % (
                                path.name,
                                node.lineno,
                                name,
                                ".".join(map(str, late[name])),
                                ".".join(map(str, floor)),
                            )
                        )
        assert not offenders, "; ".join(offenders)

    def test_the_one_backfill_there_is_is_declared(self):
        """The control on the fix: `tomllib` is guarded *and* `tomli` is in the dev
        extra behind a marker, so 3.10 installs it and 3.11+ does not."""
        root = pathlib.Path(__file__).resolve().parent.parent
        text = (root / "pyproject.toml").read_text()
        assert "tomli>=" in text
        assert "python_version < '3.11'" in text
        source = (root / "tests" / "test_portability.py").read_text()
        assert "except ModuleNotFoundError:" in source
        assert "import tomli as tomllib" in source

    def test_it_would_have_caught_the_one_that_shipped(self):
        """The control that matters: an unguarded `import tomllib` is reported."""
        import ast

        tree = ast.parse("import pathlib\nimport tomllib\n")
        guarded = self._guarded_imports(tree)
        assert "tomllib" not in guarded
        wrapped = ast.parse(
            "try:\n    import tomllib\nexcept ModuleNotFoundError:\n    import tomli as tomllib\n"
        )
        assert "tomllib" in self._guarded_imports(wrapped)


class TestTheNoNodesSentinelIsNotANodeName:
    """`NodeList=None assigned` is what sacct writes for a job that never held an
    allocation. It is a sentence meaning "no nodes", and it was carried through as
    though it were a hostname:

        nodes            None assigned  (1 node)

    -- a node called "None assigned", and a count of 1 asserted about a job that
    got zero. 38 of a real 15,085-job history carry it, every one CANCELLED at
    elapsed 0: cancelled while still pending.

    Only real data showed it. No fixture in this suite had ever built the value,
    because you have to have watched sacct emit it to know it exists.

    Folded at the parse boundary for the reason `_TRUNCATED_STATES` folds
    `OUT_OF_ME+`: that is where sacct's spellings stop being sacct's problem.
    """

    COMMON = {
        "JobName": "pending-then-cancelled",
        "Partition": "test",
        "State": "CANCELLED by 12345",
        "ExitCode": "0:0",
        "Submit": "2026-06-01T01:00:00",
        "End": "2026-06-01T01:00:00",
        "ElapsedRaw": "0",
        "Elapsed": "00:00:00",
        "Timelimit": "01:00:00",
        "ReqCPUS": "8",
        "NNodes": "1",
    }

    def _job(self, node_list):
        return parse(row(JobID="700", NodeList=node_list, **self.COMMON))[0]

    def test_the_sentinel_becomes_no_nodes(self):
        assert self._job("None assigned").node_list == ""

    def test_a_real_node_list_is_untouched(self):
        """The control, in three shapes -- a name, a range, and a comma list."""
        for value in ("midway3-0602", "midway3-[0600-0607,0611]", "n1,n2"):
            assert self._job(value).node_list == value

    def test_the_post_mortem_stops_inventing_a_node(self):
        from slurmpast.report import Style, render_job

        text, _ = render_job(self._job("None assigned"), style=Style(enabled=False), no_logs=True)
        assert "None assigned" not in text
        # The row is omitted rather than blanked: `job_sections` already guards on
        # a falsy node_list, so there is no "nodes  (1 node)" left behind either.
        assert not [ln for ln in text.splitlines() if ln.strip().startswith("nodes ")], text

    def test_json_does_not_hand_a_consumer_a_fake_hostname(self):
        from slurmpast.cli import _job_json
        from slurmpast.diagnose import diagnose

        job = self._job("None assigned")
        doc = _job_json(job, None, diagnose(job))
        assert doc["shape"]["node_list"] == ""

    def test_the_requested_node_count_is_left_alone(self):
        """Deliberately not "fixed": for a job cancelled while pending, NNodes is
        what was *requested*, which is a real reading and the only one sacct has."""
        assert self._job("None assigned").node_count == 1

    def test_the_node_table_was_never_polluted_and_still_is_not(self):
        """`expand_nodelist` already returned [] for the sentinel, so this half was
        correct before the fold. Asserted so a future change to either one cannot
        quietly reintroduce a node named "None assigned"."""
        from slurmpast.nodes import expand_nodelist, node_table

        assert expand_nodelist("None assigned") == []
        assert expand_nodelist("") == []
        # The comparison job is FAILED, not CANCELLED: the failure metric censors
        # cancellations from the denominator now, and a fixture of two cancelled
        # jobs would produce an empty table for a reason that has nothing to do
        # with the sentinel this class is about. The sentinel job stays CANCELLED,
        # because that is what all 38 real ones are.
        real = self._job("midway3-0602")._replace(state="FAILED", exit_code=1)
        table = node_table(
            [self._job("None assigned"), real], workload=None, metric="failure", min_samples=1
        )
        assert [r["node"] for r in table["rows"]] == ["midway3-0602"]


class TestAnUnexpandedArrayIdCanBeLookedUp:
    """sacct prints `49046820_[1-20%10]` and then refuses it.

    That is the spelling of a pending array in sacct's own `JobID` column under
    `--parsable2`, and in `squeue`, which is where anyone copies a job id from. The
    tool handed it straight to `sacct -j` and got a fatal error, so the one command
    a reader would reach for did not work on any throttled pending array:

        $ slurmpast '49046820_[1-20%10]'
        slurmpast: sacct: fatal: Bad job array element specified: 49046820

    Verified against the live scheduler rather than reasoned about:

        sacct -j '49046820_[1-20%10]'   fatal
        sacct -j '49046820_[1-20]'      fatal   -- the brackets, not the %throttle
        sacct -j 49046820               49046820_[1-20%10]|PENDING
        sacct -j 49046820_4             accepted (a real element)
        sacct -j 53833807.batch         accepted (a step id)

    Found only by running against the cluster: no user's own history contains a
    pending array belonging to someone else, and the demo has none at all.
    """

    def test_an_unexpanded_range_reduces_to_the_master(self):
        from slurmpast.sacct import queryable_job_id

        assert queryable_job_id("49046820_[1-20%10]") == "49046820"
        assert queryable_job_id("53601970_[0-4%2]") == "53601970"
        # The throttle is not the problem, so a plain range folds too.
        assert queryable_job_id("49046820_[1-20]") == "49046820"

    def test_every_other_spelling_is_left_alone(self):
        """The control. sacct accepts all of these, so touching them could only
        break a lookup that works."""
        from slurmpast.sacct import queryable_job_id

        for value in ("12345", "49046820_4", "500+1", "53833807.batch", "53833807.extern", ""):
            assert queryable_job_id(value) == value, value

    def test_the_query_is_built_from_the_reduced_id(self):
        """End to end through `Sacct.jobs`, with the runner captured: what reaches
        sacct is what sacct will answer."""
        from slurmpast.sacct import Sacct

        seen = []

        def runner(args):
            seen.append(args)
            return ""

        sacct = Sacct(runner=runner)
        sacct.jobs(["49046820_[1-20%10]", "53363721_4"])
        # The first call is `sacct --helpformat`, the field negotiation.
        queries = [args for args in seen if "-j" in args]
        assert queries, seen
        asked = queries[0][queries[0].index("-j") + 1]
        assert asked == "49046820,53363721_4", asked
        assert "[" not in asked

    def test_the_id_the_reader_typed_is_what_gets_echoed_back(self):
        """The reduction is a query detail. An error names what they asked for."""
        from slurmpast.cli import main

        code = main(["49046820_[1-20%10]", "--demo", "--plain", "--no-color"])
        assert code == 2


class TestAFieldMayContainANewline:
    """`sacct --parsable2` separates records with a newline and does not escape
    one occurring inside a value, so splitting on newlines shatters a record.

    Measured on midway2 (Slurm 23.02) against a real 60-day history: 41 records
    arrived as 123 physical lines and parsed as 56 "jobs", 45 of them shell
    fragments promoted to job ids --

        job_id='hostname; cat /etc/redhat-release; ldd --version | head -1'
        job_id='module use /project/rcc/youzhi/modulefiles'

    -- none of which carry an `End`, so each counted as an unterminated record
    and the overview reported `47 unterminated, excluded` where the true number
    was 2. The one line whose whole purpose is explaining a low job count was
    manufacturing the discrepancy it was explaining.

    Cluster-agnostic: the trigger is the submit style, not the site. Slurm has
    recorded `SubmitLine` since 21.08 and `sbatch --wrap=$'a\\nb'` is ordinary.
    """

    WRAP = "hostname; cat /etc/redhat-release\nmodule use /project/rcc/modulefiles\necho done"

    def _text(self):
        return make_text(
            row(
                JobID="48818838",
                JobName="probe",
                User="youzhi",
                State="COMPLETED",
                Start="2026-08-22T09:58:00",
                End="2026-08-22T10:00:00",
                ElapsedRaw="120",
                SubmitLine=self.WRAP,
            ),
            row(
                JobID="48818838.batch",
                JobName="batch",
                State="COMPLETED",
                ElapsedRaw="120",
                TotalCPU="00:01.000",
            ),
            row(
                JobID="48818841",
                JobName="probe2",
                User="youzhi",
                State="COMPLETED",
                Start="2026-08-22T10:59:00",
                End="2026-08-22T11:00:00",
                ElapsedRaw="60",
                SubmitLine="sbatch --wrap='echo hi'",
            ),
        )

    def test_the_embedded_newlines_do_not_become_records(self):
        jobs = parse(self._text(), fields=_FIELDS)
        assert [j.job_id for j in jobs] == ["48818838", "48818841"]

    def test_no_shell_fragment_is_promoted_to_a_job_id(self):
        jobs = parse(self._text(), fields=_FIELDS)
        assert [j for j in jobs if not j.job_id[:1].isdigit()] == []

    def test_the_unterminated_count_is_not_inflated(self):
        """The number the reader actually saw. Both records are closed, so the
        report has nothing to exclude and must say so."""
        from slurmpast.patterns import goodput

        assert goodput(parse(self._text(), fields=_FIELDS))["excluded_open_records"] == 0

    def test_the_multi_line_submit_line_survives_whole(self):
        """Not merely "the phantoms are gone" -- the script is data the job screen
        shows, and truncating it at the first newline would pass every assertion
        above while losing most of it. `SubmitLine` is the LAST field asked for,
        which is exactly the case a delimiter-counting reassembly gets wrong."""
        job = parse(self._text(), fields=_FIELDS)[0]
        assert job.submit_line == self.WRAP
        assert job.submit_line.count("\n") == 2

    def test_a_history_with_no_embedded_newline_is_untouched(self, cot_exp):
        """The control. Ordinary output must parse exactly as it did before."""
        assert cot_exp.job_id == "47865145"
        assert len(cot_exp.steps) == 2

    def test_a_genuinely_open_record_is_still_counted(self):
        """The other control, and the one that matters: the fix must not reach
        the count by suppressing real unterminated records."""
        from slurmpast.patterns import goodput

        text = make_text(
            row(
                JobID="48818900",
                JobName="live",
                State="RUNNING",
                Start="2026-08-22T10:00:00",
                ElapsedRaw="300",
                SubmitLine="sbatch --wrap='sleep 1000'",
            )
        )
        assert goodput(parse(text, fields=_FIELDS))["excluded_open_records"] == 1

    def test_a_pending_array_range_is_not_mistaken_for_a_continuation(self):
        """The control for how loose the boundary guard is allowed to be.

        The report asked that a record be rejected unless its first field matches
        `^\\d+(_\\d+)?(\\.\\S+)?$`. Taken literally that deletes real rows: a
        *pending* array is written `<id>_[lo-hi%throttle]`, which the anchored
        spelling has no branch for. Two such rows sit in Midway3's own 30-day
        history --

            53421602_[10-15%5] | cloze_S | CANCELLED by 940574...
            53488568_[1-6%1]   | n93big  | CANCELLED by 940574...

        -- so the strict guard would have replaced a parser that invents jobs
        with one that loses them. Hence: first character a digit, no whitespace.
        """
        text = make_text(
            row(
                JobID="53421602_[10-15%5]",
                JobName="cloze_S",
                User="youzhi",
                State="CANCELLED by 940740146",
                Submit="2026-08-20T09:00:00",
                SubmitLine="sbatch --array=1-15%5 run.sh",
            ),
            row(
                JobID="53421603+0",
                JobName="het",
                User="youzhi",
                State="COMPLETED",
                Start="2026-08-20T10:00:00",
                End="2026-08-20T10:05:00",
                ElapsedRaw="300",
                SubmitLine="sbatch het.sh",
            ),
        )
        assert [j.job_id for j in parse(text, fields=_FIELDS)] == [
            "53421602_[10-15%5]",
            "53421603+0",
        ]


class TestTheSingleJobPostMortemOnAMultiLineWrap:
    """The surface that made the newline bug a wrong answer rather than a wrong
    count -- and the one the first report got wrong about itself.

    Round 1 of the midway2 report concluded "not corrupted ... this is a
    count/garbage bug, **not a data-loss bug**", true only of the aggregate views,
    which filter phantoms through `usable()`. `cli.main` sets `matches = jobs` on
    the explicit-id branch and filters nothing, so a real OOM job submitted with a
    multi-line `sbatch --wrap` rendered a *phantom* instead:

        job "  ?
          ● TIME   ░░░░░░░░░░░░          n/a   · n/a of the n/a limit
          job
            name             n/a
          [INFO] Accounting record is not closed
                → squeue has never heard of it, so the job is long gone

    named `"` for a quote character out of the wrap script, and printed twice.
    The truth was `OUT_OF_MEMORY`, four minutes earlier. A user asking this tool's
    headline question got a confident wrong answer, not a degraded one.

    Driven through the real runner rather than by handing `parse` some text: the
    defect lived between the parser and the id branch, so a test that stops at
    `parse` would not have seen it.
    """

    WRAP = "python - <<'PY'\nbuf = 'x' * (600 << 20)\nprint('allocated')\nPY\necho done"

    def _runner(self):
        text = make_text(
            row(
                JobID="48819165",
                JobName="oomjob",
                User="youzhi",
                Partition="build",
                State="OUT_OF_MEMORY",
                ExitCode="0:125",
                Submit="2026-08-22T15:00:00",
                Start="2026-08-22T15:00:05",
                End="2026-08-22T15:00:41",
                ElapsedRaw="36",
                Timelimit="00:10:00",
                TimelimitRaw="10",
                ReqMem="100M",
                ReqCPUS="1",
                NCPUS="1",
                AllocCPUS="1",
                NNodes="1",
                NodeList="midway2-0300",
                AllocTRES="billing=1,cpu=1,mem=100M,node=1",
                SubmitLine=self.WRAP,
            ),
            row(
                JobID="48819165.batch",
                JobName="batch",
                State="OUT_OF_MEMORY",
                ExitCode="0:125",
                ElapsedRaw="36",
                TotalCPU="00:00.900",
                MaxRSS="102400K",
                NCPUS="1",
                NNodes="1",
                NodeList="midway2-0300",
            ),
            row(
                JobID="48819165.extern",
                JobName="extern",
                State="COMPLETED",
                ExitCode="0:0",
                ElapsedRaw="36",
                NCPUS="1",
                NNodes="1",
                NodeList="midway2-0300",
            ),
        ).replace("|", SAFE_DELIMITER)

        def run(args):
            # The field probe has to answer from the same fake Slurm, or the query
            # negotiates against whatever sacct is on the runner's PATH.
            if "--helpformat" in args:
                return " ".join(_FIELDS)
            if args and args[0] in ("squeue", "scontrol"):
                return ""
            return text

        return run

    def _report(self, monkeypatch, capsys):
        from slurmpast import cli

        monkeypatch.setattr("slurmpast.sacct._run", self._runner())
        code = cli.main(["48819165", "--plain", "--no-color", "--no-logs"])
        return code, capsys.readouterr().out

    def test_the_post_mortem_is_printed_once(self, monkeypatch, capsys):
        _code, out = self._report(monkeypatch, capsys)
        assert out.count("● TIME") == 1, out

    def test_it_is_the_real_job_and_not_a_phantom(self, monkeypatch, capsys):
        _code, out = self._report(monkeypatch, capsys)
        assert "job 48819165  OUT_OF_MEMORY" in out, out
        assert "oomjob" in out
        assert "n/a of the n/a limit" not in out

    def test_the_real_cause_is_diagnosed(self, monkeypatch, capsys):
        """Not merely "a record was found" -- the finding that made this worth
        reporting was the tool confidently naming the wrong cause."""
        code, out = self._report(monkeypatch, capsys)
        assert "Host memory exhausted" in out, out
        assert "Accounting record is not closed" not in out
        assert code == 1, "an OOM is a finding the exit code has to carry"

    def test_the_wrap_script_is_shown_whole(self, monkeypatch, capsys):
        """The job screen prints `submitted as`, so every line of the script has
        to have survived the parse to reach it.

        Supporting, not discriminating: against the reverted tree the same lines
        appear anyway, as the *phantom records they were turned into*.
        `test_the_multi_line_submit_line_survives_whole` is the one that tells the
        two apart, because it asks a single Job for the whole field.
        """
        _code, out = self._report(monkeypatch, capsys)
        for line in self.WRAP.split("\n"):
            assert line in out, line


class TestARedirectMustNotLaunchTheDashboard:
    """`slurmpast > report.txt` hung forever, which is the most ordinary thing
    anyone does with a report.

    Measured on midway2 under a 20 s SIGKILL cap: `slurmpast -S now-2days > file`
    exited **137**, having written 26,514 bytes of escape sequences into the file
    and entered the alternate screen, then waited for a keypress a redirect can
    never deliver. `| cat` did the same. Under cron or CI the job never finishes.

    The package had exactly one `isatty` call before this (`report.Style`) and it
    only chooses colours; nothing guarded the decision to launch Textual.
    """

    class _Stream:
        def __init__(self, tty):
            self._tty = tty

        def isatty(self):
            return self._tty

    def test_two_terminals_is_the_only_interactive_case(self):
        from slurmpast.cli import _has_terminal

        yes, no = self._Stream(True), self._Stream(False)
        assert _has_terminal(stdin=yes, stdout=yes) is True
        assert _has_terminal(stdin=yes, stdout=no) is False
        # stdin too: Textual reads keys from it, so `slurmpast </dev/null` would
        # paint a screen nobody can drive or quit.
        assert _has_terminal(stdin=no, stdout=yes) is False

    def test_a_stream_that_cannot_answer_is_not_a_terminal(self):
        """A closed stream raises ValueError from isatty(), and one replaced by a
        harness may not have the method at all. Either way the answer wanted is
        "no terminal", not a traceback out of an argument-parsing path."""
        from slurmpast.cli import _has_terminal

        class Closed:
            def isatty(self):
                raise ValueError("I/O operation on closed file")

        assert _has_terminal(stdin=Closed(), stdout=self._Stream(True)) is False
        assert _has_terminal(stdin=object(), stdout=self._Stream(True)) is False

    def test_a_redirect_gets_the_plain_report_instead_of_ansi(self, monkeypatch, capsys):
        """End to end. pytest's captured stdout is not a tty, which is the same
        condition a redirect creates -- so `--demo` with no text flag must return
        the plain report and exit rather than block on the app."""
        from slurmpast import cli

        def no_dashboard(*a, **kw):
            raise AssertionError("the dashboard was launched with stdout redirected")

        monkeypatch.setattr("slurmpast.tui.run", no_dashboard)
        code = cli.main(["--demo", "--no-color"])
        out = capsys.readouterr().out
        assert code in (0, 1), code
        assert out.strip(), "a redirect produced no report at all"
        assert "\x1b[" not in out, "escape sequences reached a non-terminal stdout"

    def test_a_terminal_still_gets_the_dashboard(self, monkeypatch):
        """The control, and the one worth writing carefully: a guard that
        degrades unconditionally would pass every assertion above and quietly
        delete the dashboard."""
        from slurmpast import cli

        launched = []
        monkeypatch.setattr("slurmpast.cli._has_terminal", lambda *a, **kw: True)
        monkeypatch.setattr("slurmpast.tui.run", lambda *a, **kw: launched.append(True) or 0)
        assert cli.main(["--demo"]) == 0
        assert launched == [True]

    def test_an_explicit_text_flag_is_unaffected_either_way(self, monkeypatch, capsys):
        """`--overview` in a terminal must stay text: the guard only ever adds
        `--plain`, it never takes a chosen view away."""
        from slurmpast import cli

        monkeypatch.setattr("slurmpast.cli._has_terminal", lambda *a, **kw: True)
        cli.main(["--demo", "--overview", "--no-color"])
        assert capsys.readouterr().out.strip()


class TestAUnitLessMemoryLimitIsMegabytes:
    """A bare integer in a memory *option* is megabytes in Slurm, not bytes.

    `sbatch(1)`, `--mem=<size>[units]`: *"Default units are megabytes"*. Reported
    as a divergence across the three tools rather than against this one -- on the
    same inputs slurmate read `16` as 16 MB while slurmpast and slurmwatch both
    read it as **16 bytes**, off by 1,048,576x and silent. slurmate was right.

    Latent on both clusters checked: Slurm 23.02 and 20.11.8 alike write an
    explicit unit into `ReqMem`, and 30 days of Midway3 accounting (609,511 rows
    at `4Gn` alone) held no unit-less spelling. Pinned rather than hunted for,
    because the thing that decides it is a site's Slurm version.

    The narrowing matters as much as the fix: `parse_bytes` was left alone. It
    also decodes `MaxPages`, which is a *page count* this cluster emits bare
    (`0`), and `MaxDiskRead`/`MaxDiskWrite`, which are byte counters. Applying the
    limit convention to those would read a bare `312` as 312 MiB.
    """

    def test_a_bare_integer_limit_is_mebibytes(self):
        assert parse_mem_limit("16") == 16 * 1024**2

    def test_the_scope_suffix_does_not_change_that(self):
        """`16n` is 16 MiB per node on Slurm <= 20.11, not 16 bytes."""
        assert parse_mem_limit("16n") == 16 * 1024**2
        assert parse_mem_limit("16c") == 16 * 1024**2

    def test_every_suffixed_spelling_is_unchanged(self):
        """The control. The forms real clusters actually emit must read exactly
        as they did before, or the fix has moved every memory figure in the tool."""
        for text in ("4Gn", "500Mc", "3810Mc", "1.50T", "53741792K", "80G"):
            assert parse_mem_limit(text) == parse_bytes(text), text

    def test_parse_bytes_still_reads_a_bare_counter_as_bytes(self):
        """The control that stops the fix spreading. `MaxPages` is a page count
        and `MaxDiskRead` a byte counter; this cluster emits `MaxPages` bare."""
        assert parse_bytes("16") == 16
        assert parse_bytes("0") == 0

    def test_the_unreadable_and_the_missing_are_still_told_apart(self):
        """`64GB` is not Slurm syntax and stays unparseable rather than being
        guessed at -- the divergence the report noted across the three tools, left
        as it was on purpose."""
        assert parse_mem_limit("64GB") is None
        assert parse_mem_limit("") is None
        assert parse_mem_limit(None) is None

    def test_the_job_record_carries_the_corrected_limit(self):
        """Through the parser, not just the helper: `ReqMem` is the one field
        wired to the limit convention."""
        text = make_text(
            row(
                JobID="900001",
                JobName="bare",
                User="youzhi",
                State="COMPLETED",
                Start="2026-08-22T10:00:00",
                End="2026-08-22T10:01:00",
                ElapsedRaw="60",
                ReqMem="16",
            )
        )
        job = parse(text, fields=_FIELDS)[0]
        assert job.req_mem_bytes == 16 * 1024**2


class TestAHostileLogDoesNotTakeTheReaderDown:
    """The log reader is the likeliest place a post-mortem tool dies on a real
    cluster, and until now nothing in this suite exercised it.

    A portability round on a second cluster built a `.err` hostile in the two
    ways HPC logs actually are -- invalid UTF-8 (what MPI/CUDA/Fortran tooling
    emits) and 40 MB on a single line -- with the real error buried after the
    noise, and reported a clean pass: no crash, 17 MB peak RSS against the 40 MB
    file, a 1,572-byte report, and the right diagnosis found past the padding.

    That was a *negative* result, which is exactly the kind that quietly stops
    being true. `read_tail` appears in this suite three times and is monkeypatched
    on all three (`test_tui.py:773,833,849`), so none of those properties was
    pinned by anything. They are now.

    Reproduced here before being written down: a 40 MB build of the same file
    reads in 262,144 characters and finds the error, while `Path.read_text()` on
    it raises `UnicodeDecodeError: ... can't decode byte 0xff in position 30`. The
    fixtures below use a smaller multiple of the cap so the suite stays fast --
    the property is "bounded by max_bytes whatever the size", and four times the
    cap tests it as well as a hundred and sixty times does.
    """

    NOISE = b"\xff\xfe\x80\x81 \xc3\x28 \xed\xa0\x80 "
    REAL = "RuntimeError: real failure after the noise"

    def _hostile(self, tmp_path):
        from slurmpast.logs import MAX_TAIL_BYTES

        path = tmp_path / "badlog-48819300.err"
        with path.open("wb") as fh:
            fh.write(b"start of one very long line: ")
            while fh.tell() < MAX_TAIL_BYTES * 4:
                fh.write(self.NOISE + b"x" * 4096)
            fh.write(("\n%s\n" % self.REAL).encode())
        return path

    def test_invalid_utf8_does_not_raise(self, tmp_path):
        """`Path.read_text()` on this file raises. The reader must not."""
        from slurmpast.logs import read_tail

        path = self._hostile(tmp_path)
        with pytest.raises(UnicodeDecodeError):
            path.read_text()
        assert read_tail(str(path)) is not None

    def test_the_read_is_bounded_by_the_cap_not_the_file(self, tmp_path):
        """17 MB peak against a 40 MB log was the reported figure; the mechanism
        behind it is that the file is never slurped."""
        from slurmpast.logs import MAX_TAIL_BYTES, read_tail

        path = self._hostile(tmp_path)
        assert path.stat().st_size > MAX_TAIL_BYTES * 4
        text = read_tail(str(path))
        assert len(text) <= MAX_TAIL_BYTES, len(text)

    def test_the_real_error_after_the_noise_still_arrives(self, tmp_path):
        """Bounding is only correct because it keeps the *tail*. A reader that
        capped the head would pass the test above and lose the diagnosis."""
        from slurmpast.logs import read_tail

        assert self.REAL in read_tail(str(self._hostile(tmp_path)))

    def test_a_small_clean_log_is_returned_whole(self, tmp_path):
        """The control. Bounding must not start truncating ordinary logs."""
        from slurmpast.logs import read_tail

        path = tmp_path / "fine.err"
        path.write_text("line one\nline two\n")
        assert read_tail(str(path)) == "line one\nline two\n"

    def test_carriage_returns_are_still_normalised(self, tmp_path):
        """The other control: the reader's documented job. tqdm spam collapsing a
        traceback onto one row is why this function exists, and a fix aimed at
        hostile bytes must not cost that."""
        from slurmpast.logs import read_tail

        path = tmp_path / "tqdm.err"
        path.write_bytes(b"50%\r99%\r100%\r\nTraceback\n")
        assert read_tail(str(path)) == "50%\n99%\n100%\nTraceback\n"

    def test_an_unreadable_path_is_none_not_an_exception(self, tmp_path):
        """A missing log is an ordinary state for a post-mortem, not an error."""
        from slurmpast.logs import read_tail

        assert read_tail(str(tmp_path / "nope.err")) is None


class TestARequeuedJobIsNotInvisible:
    """`sacct` reports only a job's *latest* incarnation unless `-D` is asked for,
    and `sacct.py` contained no `-D`. A job requeued on NODE_FAIL, on preemption,
    or by `scontrol requeue` therefore rendered as its final attempt with no sign
    there had been others -- which is the one case where the missing part *is* the
    answer: "why is my job still pending when I watched it start" is a requeue.

    Reproduced on Midway3's real accounting, job 53432121::

        53432121|NODE_FAIL|2026-08-17T10:08:59|...|00:27:49
        53432121|COMPLETED|2026-08-17T10:48:35|...|03:41:52

    The tool showed `COMPLETED` after 03:41:52 and said nothing about the 27m49s
    burned on a node that failed under it. 773 of 922,534 rows in seven
    cluster-days here are requeues, so it is uncommon and not rare.

    One `Job` per id still comes out -- the newest incarnation, with the earlier
    ones in `earlier` -- so no count, ranking or post-mortem starts doubling.
    """

    def _jobs(self):
        text = make_text(
            row(
                JobID="53432121",
                JobName="latent_sweep",
                User="youzhi",
                State="NODE_FAIL",
                Submit="2026-08-17T10:08:59",
                Start="2026-08-17T10:20:46",
                End="2026-08-17T10:48:35",
                ElapsedRaw="1669",
                Timelimit="10:00:00",
            ),
            row(
                JobID="53432121.batch",
                JobName="batch",
                State="CANCELLED",
                Submit="2026-08-17T10:20:46",
                ElapsedRaw="1669",
            ),
            row(
                JobID="53432121",
                JobName="latent_sweep",
                User="youzhi",
                State="COMPLETED",
                Submit="2026-08-17T10:48:35",
                Start="2026-08-17T10:50:37",
                End="2026-08-17T14:32:29",
                ElapsedRaw="13312",
                Timelimit="10:00:00",
            ),
            row(
                JobID="53432121.batch",
                JobName="batch",
                State="COMPLETED",
                Submit="2026-08-17T10:50:37",
                ElapsedRaw="13312",
                MaxRSS="10822892K",
            ),
        )
        return parse(text, fields=_FIELDS)

    def test_the_query_asks_for_duplicates(self):
        """Without `-D` none of the rest of this can happen: Slurm simply does not
        send the earlier incarnation."""
        seen = []

        def runner(args):
            seen.append(args)
            return ""

        Sacct(runner=runner, probe=" ".join(_FIELDS)).history(user="u")
        assert "-D" in seen[0], seen[0]

    def test_the_id_still_yields_exactly_one_job(self):
        """The requeue must not become a second job in the rollup, or every count
        in the tool moves for a job that ran once."""
        jobs = self._jobs()
        assert [j.job_id for j in jobs] == ["53432121"]

    def test_it_is_the_latest_incarnation_that_is_the_job(self):
        job = self._jobs()[0]
        assert job.base_state == "COMPLETED"
        assert job.elapsed == 13312.0
        assert job.submit == "2026-08-17T10:48:35"

    def test_the_earlier_attempt_and_the_time_it_burned_survive(self):
        """The count alone would not say 27m49s went into a failed node, and the
        time is the part that was missing from accounting."""
        (earlier,) = self._jobs()[0].earlier
        assert earlier.base_state == "NODE_FAIL"
        assert earlier.elapsed == 1669.0

    def test_the_steps_attach_to_the_incarnation_that_ran_them(self):
        """The control that matters most, and the one this fix first got wrong.

        A step's `Submit` is its own start, not the job's -- `53432121.batch`
        reads `10:50:37` where its allocation reads `10:48:35` -- so grouping
        steps by Submit matches nothing and silently empties every job's step
        list. That surfaces as `MEM  n/a` on a job whose memory was recorded, an
        erasure that looks like missing data rather than a bug. Steps attach
        positionally instead, which is the order sacct emits them in.
        """
        job = self._jobs()[0]
        assert [s.step_id for s in job.steps] == ["53432121.batch"]
        assert job.max_rss == 10822892 * 1024
        assert job.earlier[0].steps and job.earlier[0].steps[0].state == "CANCELLED"

    def test_the_report_says_how_many_times_and_what_happened(self, capsys):
        from slurmpast import report

        out, _verdict = report.render_job(
            self._jobs()[0], no_logs=True, style=report.Style(enabled=False)
        )
        assert "requeued" in out
        assert "1x" in out and "NODE_FAIL" in out and "00:27:49" in out, out

    def test_an_ordinary_job_is_untouched(self):
        """The control. Nothing about a job that was never requeued may change --
        no `earlier`, and its steps still attach."""
        text = make_text(
            row(
                JobID="700001",
                JobName="plain",
                User="youzhi",
                State="COMPLETED",
                Submit="2026-08-17T10:00:00",
                Start="2026-08-17T10:00:05",
                End="2026-08-17T10:01:05",
                ElapsedRaw="60",
            ),
            row(
                JobID="700001.batch",
                JobName="batch",
                State="COMPLETED",
                Submit="2026-08-17T10:00:05",
                ElapsedRaw="60",
                MaxRSS="2048K",
            ),
        )
        (job,) = parse(text, fields=_FIELDS)
        assert job.earlier == ()
        assert [s.step_id for s in job.steps] == ["700001.batch"]
        assert job.max_rss == 2048 * 1024
        from slurmpast import report

        text, _verdict = report.render_job(job, no_logs=True, style=report.Style(enabled=False))
        assert "requeued" not in text


class TestAStepRowsMultiLineFieldMakesNoPhantoms:
    """SP-1's second trigger, and the far more common one.

    Round 4 pinned the newline bug to a multi-line `sbatch --wrap`. A later round
    found it reaches any multi-line field in *any* row, including **step** rows:
    job 48819348 was submitted the tidy way, from a script file, so its own
    `SubmitLine` is the single line `sbatch steps.sh` -- and asking for that one
    job id still printed four post-mortems, because step `.1` was an ordinary
    `srun ... bash -c` with a heredoc in it.

    That matters more than the `--wrap` case: the user did nothing unusual, and
    `srun python -c "..."` / heredocs are everyday HPC usage. The two failure
    modes also differ -- a multi-line *job* row replaces the real record with a
    phantom, while a multi-line *step* row leaves the record correct and appends
    fabricated post-mortems to it.

    The fix needed no change: the boundary test asks whether a line's first field
    looks like a JobID, and `48819348.1` does while `from slurmwatch import slurm`
    does not. Pinned because the report named it as a distinct trigger, and a
    reassembly rule that happened to cover it should be shown to.
    """

    HEREDOC = (
        "srun --jobid=48819348 --overlap bash -c "
        "'python - <<EOF\nfrom slurmwatch import slurm\nEOF'"
    )

    def _jobs(self):
        text = make_text(
            row(
                JobID="48819348",
                JobName="steps",
                User="youzhi",
                State="COMPLETED",
                Submit="2026-08-23T00:00:00",
                Start="2026-08-23T00:00:01",
                End="2026-08-23T00:01:00",
                ElapsedRaw="60",
                SubmitLine="sbatch steps.sh",
            ),
            row(
                JobID="48819348.1",
                JobName="bash",
                State="COMPLETED",
                Submit="2026-08-23T00:00:05",
                ElapsedRaw="45",
                SubmitLine=self.HEREDOC,
            ),
        )
        return parse(text, fields=_FIELDS)

    def test_the_heredoc_lines_do_not_become_jobs(self):
        assert [j.job_id for j in self._jobs()] == ["48819348"]

    def test_the_step_still_attaches_to_its_job(self):
        """The control: rejecting the fragments must not cost the step itself."""
        assert [s.step_id for s in self._jobs()[0].steps] == ["48819348.1"]

    def test_only_one_post_mortem_is_printed_for_the_requested_id(self, monkeypatch, capsys):
        """The reported symptom: three extra post-mortems below the real one.

        Driven through `cli.main`, not `report.render_job`. Handing the renderer a
        single Job cannot see this defect at all -- one job in, one block out,
        whatever the parser did -- so that version of this test passed against the
        broken parser and was asserting nothing. The phantoms only become visible
        where `matches = jobs` on the explicit-id branch decides how many jobs
        there are to render.
        """
        from slurmpast import cli

        text = make_text(
            row(
                JobID="48819348",
                JobName="steps",
                User="youzhi",
                State="COMPLETED",
                Submit="2026-08-23T00:00:00",
                Start="2026-08-23T00:00:01",
                End="2026-08-23T00:01:00",
                ElapsedRaw="60",
                SubmitLine="sbatch steps.sh",
            ),
            row(
                JobID="48819348.1",
                JobName="bash",
                State="COMPLETED",
                Submit="2026-08-23T00:00:05",
                ElapsedRaw="45",
                SubmitLine=self.HEREDOC,
            ),
        ).replace("|", SAFE_DELIMITER)

        def run(args):
            if "--helpformat" in args:
                return " ".join(_FIELDS)
            if args and args[0] in ("squeue", "scontrol"):
                return ""
            return text

        monkeypatch.setattr("slurmpast.sacct._run", run)
        cli.main(["48819348", "--plain", "--no-color", "--no-logs"])
        out = capsys.readouterr().out
        assert out.count("\u25cf TIME") == 1, out
        # Collapsed: this is a *negative* assertion, so a wrap splitting the
        # phrase would make it pass while the phantom sat on screen.
        assert "job from slurmwatch import slurm" not in " ".join(out.split())


class TestAMixedOutcomeArrayAggregates:
    """A 4-task array with two tasks OOM-killed and two completed.

    Verified on a second cluster and reported as correct -- one workload, each
    task a run, the completed/flagged split right:

        4 jobs in 1 workload · 50.0% completed
        1  mixedarr  build  RUNS 4  COMPLETED 2  FLAGGED 2

    It is correct. Nothing in this suite said so: the rollup's tests build
    separate submissions, and no test anywhere folded array *tasks* of one array
    into a workload and checked the split. An array whose tasks disagree is the
    ordinary shape of a parameter sweep, and it is where a rollup that keyed on
    the array id rather than the task, or that took the first task's state for the
    group, would go wrong without anything failing.
    """

    def _history(self, outcomes):
        from slurmpast.index import History

        rows = [
            row(
                JobID="48819369_%d" % index,
                JobName="mixedarr",
                User="youzhi",
                Partition="build",
                State=state,
                ExitCode=code,
                Submit="2026-08-23T01:00:00",
                Start="2026-08-23T01:00:05",
                End="2026-08-23T01:01:05",
                ElapsedRaw="60",
                ReqMem="120M",
                ReqCPUS="1",
                NCPUS="1",
                AllocCPUS="1",
                NNodes="1",
                NodeList="midway2-0300",
            )
            for index, (state, code) in enumerate(outcomes, 1)
        ]
        return History(parse(make_text(*rows), fields=_FIELDS))

    MIXED = [
        ("OUT_OF_MEMORY", "0:125"),
        ("OUT_OF_MEMORY", "0:125"),
        ("COMPLETED", "0:0"),
        ("COMPLETED", "0:0"),
    ]

    def test_the_tasks_are_one_workload_and_four_runs(self):
        history = self._history(self.MIXED)
        (group,) = history.groups
        assert group.name == "mixedarr"
        assert group.total == 4, "each task is a run, not the array one run"

    def test_the_split_follows_the_tasks_not_the_array(self):
        (group,) = self._history(self.MIXED).groups
        assert (group.completed, group.problems) == (2, 2)

    def test_the_headline_counts_the_failed_tasks(self):
        assert "2 of 4 jobs failed" in self._history(self.MIXED).headline()

    def test_an_array_that_all_succeeded_flags_nothing(self):
        """The control. A split of 2/2 must come from the tasks, not from the
        shape -- an all-COMPLETED array has to read as clean."""
        (group,) = self._history([("COMPLETED", "0:0")] * 4).groups
        assert (group.total, group.completed, group.problems) == (4, 4, 0)


class TestArraySiblingsAlreadyCountAsEvidence:
    """A portability round observed that two OOM tasks inside one array did not
    trip the memory rule while three separate submissions did, and wondered
    whether the rule should "ever count array siblings", weighting them
    differently if it did.

    The premise is off, and worth pinning rather than arguing: siblings are
    already counted. Two does not clear the bar because the bar is three, not
    because they are siblings -- the grouping key is `(folded name, partition,
    kind, user)`, which an array's tasks all share.

    Left at three deliberately. The suggestion that two *simultaneous* identical
    tasks are stronger evidence than three sequential ones is reasonable and is
    not a defect: the report filed it as an observation, and acting on it would
    mean a second, lower threshold whose only justification is an intuition
    nobody has data for. Recorded in `issues.md` rather than implemented.
    """

    def _siblings(self, count):
        from slurmpast.patterns import find_memory_search

        text = make_text(
            *(
                row(
                    JobID="48819369_%d" % index,
                    JobName="mixedarr",
                    User="youzhi",
                    Partition="build",
                    State="OUT_OF_MEMORY",
                    ExitCode="0:125",
                    Submit="2026-08-23T01:00:00",
                    Start="2026-08-23T01:00:05",
                    End="2026-08-23T01:01:05",
                    ElapsedRaw="60",
                    ReqMem="120M",
                    ReqCPUS="1",
                    NCPUS="1",
                    AllocCPUS="1",
                    NNodes="1",
                    NodeList="midway2-0300",
                )
                for index in range(1, count + 1)
            )
        )
        return [f.code for f in find_memory_search(parse(text, fields=_FIELDS))]

    def test_three_siblings_at_one_request_is_a_pattern(self):
        assert self._siblings(3) == ["memory-unchanged"]

    def test_two_is_below_the_bar_which_is_the_only_reason_it_is_silent(self):
        """The control that identifies *why* the reported case was quiet. If a
        future change exempted arrays, this would still pass while the test above
        started failing -- so both are needed to say "the threshold, not the
        shape"."""
        assert self._siblings(2) == []


class TestTheOnlyEnvironmentVariableIsValidated:
    """`SLURMPAST_TIMEOUT` accepted anything and silently used the default.

    One variable is a small surface, but it is the whole of this package's
    environment surface, and nothing in this suite touched it. Measured on a
    second cluster:

        SLURMPAST_TIMEOUT=garbage  -> rc=0, query runs normally
        SLURMPAST_TIMEOUT=-5       -> rc=0, query runs normally
        SLURMPAST_TIMEOUT=0        -> rc=0, query runs normally

    `0` is the one that stings: a reader writes it meaning *no timeout* and gets
    300 seconds, with nothing said either way. `garbage` was indistinguishable
    from leaving the variable unset. The sibling package rejects the same class of
    input by name, which is the standard being matched here.
    """

    def test_a_non_number_is_refused_by_name(self, monkeypatch):
        from slurmpast.sacct import SacctError, _timeout

        monkeypatch.setenv("SLURMPAST_TIMEOUT", "garbage")
        with pytest.raises(SacctError) as caught:
            _timeout()
        assert "SLURMPAST_TIMEOUT" in str(caught.value)
        assert "garbage" in str(caught.value), "the value has to be quoted back"

    @pytest.mark.parametrize("value", ["0", "-5", "0.0", "1e999"])
    def test_a_non_positive_or_infinite_budget_is_refused(self, monkeypatch, value):
        """`0` and `-5` from the report, plus infinity, which `float` accepts and
        `communicate` would take as "wait forever" -- the unbounded wait this tool
        has already had to be fixed for once."""
        from slurmpast.sacct import SacctError, _timeout

        monkeypatch.setenv("SLURMPAST_TIMEOUT", value)
        with pytest.raises(SacctError) as caught:
            _timeout()
        assert "positive" in str(caught.value)

    def test_a_usable_value_is_honoured(self, monkeypatch):
        """The control. A large budget is honoured rather than capped: the
        variable exists so a site whose accounting takes an hour can say so, and
        silently overriding that is the same fault in the other direction."""
        from slurmpast.sacct import _timeout

        monkeypatch.setenv("SLURMPAST_TIMEOUT", "999999")
        assert _timeout() == 999999.0

    def test_a_bad_value_is_refused_before_anything_is_spawned(self, monkeypatch):
        """Where the check happens, not just that it happens.

        `_timeout` is read inside `_run`, and reading it *after* `Popen` left a
        real `sacct` running with nothing to reap it: the only cleanup in that
        function is the TimeoutExpired branch, which a SacctError skips straight
        past. Refusing a setting is also no reason to have started a query.
        """
        import subprocess as sp

        from slurmpast.sacct import SacctError, _run

        spawned = []
        monkeypatch.setattr(sp, "Popen", lambda *a, **k: spawned.append(a) or None)
        monkeypatch.setenv("SLURMPAST_TIMEOUT", "0")
        with pytest.raises(SacctError):
            _run(["sacct", "--noheader"])
        assert spawned == [], "the child was started before the setting was checked"

    def test_unset_is_the_default_and_says_nothing(self, monkeypatch):
        """The other control: validation must not turn the ordinary case into an
        error, and the empty string is what an exported-but-blank variable is."""
        from slurmpast.sacct import DEFAULT_TIMEOUT, _timeout

        monkeypatch.delenv("SLURMPAST_TIMEOUT", raising=False)
        assert _timeout() == DEFAULT_TIMEOUT
        monkeypatch.setenv("SLURMPAST_TIMEOUT", "  ")
        assert _timeout() == DEFAULT_TIMEOUT


class TestASubSecondTimeoutSaysWhatItWas:
    """The timeout message formatted the budget with `%.0f`, so every sub-second
    value printed as `0s`:

        $ SLURMPAST_TIMEOUT=0.05 slurmpast --overview
        slurmpast: sacct did not answer within 0s — ...  Narrow the window with
        -S, or raise SLURMPAST_TIMEOUT.

    That reads as *the tool used a zero timeout* -- its own defect -- rather than
    *your 50 ms budget was too small*. The advice is to raise the variable, and
    the reader cannot act on it without seeing what it currently is.

    Driven through the real subprocess path with a command that genuinely
    outlasts its budget, because the formatting sits in the except branch and a
    test that builds the string by hand would pin the wrong thing.
    """

    def _timed_out(self, monkeypatch, budget):
        from slurmpast.sacct import SacctError, _run

        monkeypatch.setenv("SLURMPAST_TIMEOUT", budget)
        with pytest.raises(SacctError) as caught:
            _run(["sleep", "5"])
        return str(caught.value)

    def test_a_fractional_budget_is_shown_as_itself(self, monkeypatch):
        message = self._timed_out(monkeypatch, "0.05")
        assert "within 0.05s" in message, message
        assert "within 0s" not in message

    def test_a_whole_budget_keeps_its_plain_spelling(self, monkeypatch):
        """The control: `%g` must not turn 2 seconds into `2.0s`."""
        assert "within 2s" in self._timed_out(monkeypatch, "2")

    def test_the_advice_still_names_the_way_out(self, monkeypatch):
        message = self._timed_out(monkeypatch, "0.05")
        assert "SLURMPAST_TIMEOUT" in message and "-S" in message


@pytest.mark.skipif(
    subprocess.run(["which", "sacct"], capture_output=True).returncode != 0,
    reason="no Slurm on this machine",
)
class TestTheFieldProbeAgreesWithTheLocalSacct:
    """Differential test of the field negotiation against a real `sacct`.

    The same shape as `test_agrees_with_the_local_scheduler` above, which checks
    the nodelist expander against `scontrol show hostnames` and skips where there
    is no scheduler. This is the other half: the negotiation that decides *which*
    of the 80-odd fields to ask for, which is the thing that breaks first on a
    Slurm nobody here has seen.

    Worth adding because a portability pass across four packages concluded that a
    green suite says nothing about portability -- *"every finding here lives at a
    boundary the tests mock"* -- and the sacct boundary is the one this package's
    worst defect came through. Every other test of the parser hands it a fixture.
    None of them can notice that `SubmitLine` does not exist before Slurm 21.08,
    or that `Reserved` became `Planned` in 23.02; only asking the local scheduler
    can.

    Skips rather than fails wherever the scheduler is present but cannot answer:
    on a login node with an unreachable accounting database, an unanswerable query
    is the environment's state, not this package's defect.
    """

    def _sacct(self):
        from slurmpast.sacct import Sacct

        return Sacct()

    def _skip_if_unreachable(self, exc):
        from slurmpast.sacct import SacctError

        assert isinstance(exc, SacctError)
        text = str(exc).lower()
        if "did not answer" in text or "unreachable" in text or "cannot execute" in text:
            pytest.skip("Slurm is present but not answering: %s" % exc)
        raise exc

    def test_every_negotiated_field_is_one_this_sacct_knows(self):
        """The probe must not ask for a spelling the local release dropped or has
        not added yet."""
        fields = self._sacct().fields
        known = {
            word.strip().lower()
            for word in subprocess.run(
                ["sacct", "--helpformat"], capture_output=True, text=True
            ).stdout.split()
        }
        if not known:
            pytest.skip("this sacct does not implement --helpformat")
        unknown = [f for f in fields if f.lower() not in known]
        assert unknown == [], "asked for fields this sacct does not list: %s" % unknown

    def test_the_negotiated_query_is_actually_accepted(self):
        """The assertion that matters, and the one a fixture cannot make: issue the
        real query and let the real sacct judge it. `Invalid field requested` is
        how this fails on a release the negotiation guessed wrong about."""
        from slurmpast.sacct import SacctError

        try:
            self._sacct().history(since="now-5minutes")
        except SacctError as exc:
            self._skip_if_unreachable(exc)

    def test_the_safe_delimiter_is_accepted(self):
        """`--delimiter` has been in sacct since 17.11 and the code falls back
        without it. Which branch this cluster takes is a fact about the cluster, so
        assert only that one of them was reached and that the choice is recorded."""
        from slurmpast.sacct import SAFE_DELIMITER, SacctError

        sacct = self._sacct()
        try:
            sacct.history(since="now-5minutes")
        except SacctError as exc:
            self._skip_if_unreachable(exc)
        assert sacct._delimiter in (SAFE_DELIMITER, "|")


class TestAMisMatchedLogCannotInventAGpuCause:
    """The log-matching heuristic guesses, and a guess can be wrong loudly.

    Reported from a second cluster: a job on a GPU-less partition failed with
    `disk quota exceeded`, and a decoy file in the search directory -- unrelated
    name, `touch -r`'d to the same mtime -- was matched by timing. The tool then
    printed, at its highest severity and as a statement of fact:

        [FAIL] GPU ran out of memory
              Device-side allocation failure in the log. This is NOT host memory

    for a job that allocated no GPU. The `matched by timing, not by name` hedge
    was there, but one dim line does not balance a `[FAIL]` followed by four
    specific remediations, and the real cause never appeared.

    The guard is free: `AllocTRES` carries no `gres` entry, so the whole class of
    finding is ruled out by evidence the tool already holds. This does not make a
    mis-attached log right -- it is still the wrong file -- it stops the tool
    asserting a cause it can disprove.
    """

    CUDA = "DECOY CAUSE: CUDA error: out of memory\n"

    def _job(self, alloc_tres):
        text = make_text(
            row(
                JobID="48819449",
                JobName="quotajob",
                User="youzhi",
                Partition="build",
                State="FAILED",
                ExitCode="3:0",
                Submit="2026-08-23T08:00:00",
                Start="2026-08-23T08:00:05",
                End="2026-08-23T08:00:41",
                ElapsedRaw="36",
                ReqMem="4G",
                ReqCPUS="1",
                NCPUS="1",
                AllocCPUS="1",
                NNodes="1",
                NodeList="midway2-0300",
                AllocTRES=alloc_tres,
            )
        )
        return parse(text, fields=_FIELDS)[0]

    def test_a_gpuless_job_gets_no_gpu_finding(self):
        from slurmpast.diagnose import diagnose

        job = self._job("billing=1,cpu=1,mem=4G,node=1")
        assert job.gpu_count == 0
        codes = {f.code for f in diagnose(job, log_text=self.CUDA).findings}
        assert "cuda-oom" not in codes, codes

    def test_a_job_that_did_hold_a_gpu_still_gets_it(self):
        """The control, and the one that matters: this must not silence the
        finding for the jobs it was written for."""
        from slurmpast.diagnose import diagnose

        job = self._job("billing=1,cpu=1,gres/gpu=1,mem=4G,node=1")
        assert job.gpu_count == 1
        codes = {f.code for f in diagnose(job, log_text=self.CUDA).findings}
        assert "cuda-oom" in codes, codes

    def test_a_failure_with_an_unrecognised_log_is_still_flagged(self):
        """The other control. Suppressing the wrong cause must not leave a failed
        job reading "nothing to flag" -- which is what it did, because no rule
        matched the text and nothing showed the reader the file it had found."""
        from slurmpast.diagnose import diagnose

        job = self._job("billing=1,cpu=1,mem=4G,node=1")
        verdict = diagnose(job, log_text="REAL CAUSE: disk quota exceeded on /scratch\n")
        assert verdict.findings, "a failed job with a log must say something"
        assert "disk quota exceeded" in verdict.findings[0].evidence


class TestTheFailurePostMortemPrefersStderr:
    """With both real logs present it chose the empty `--output` and then said no
    log explained the failure.

    Slurm touches an unused stdout at job end, so on a failed job the 0-byte
    `.out` is routinely *closer* to End than the `.err` written moments earlier
    when the error happened. Ranking on distance alone therefore picks the empty
    one, and the advice that follows -- "Pass --log-dir" -- is advice the user had
    already taken.
    """

    def _pick(self, tmp_path, err_mtime, out_mtime, err_text="REAL CAUSE: quota\n"):
        import os

        from slurmpast.logs import find_log_by_time

        (tmp_path / "realname-A.err").write_text(err_text)
        (tmp_path / "realname-A.out").write_text("")
        os.utime(tmp_path / "realname-A.err", (err_mtime, err_mtime))
        os.utime(tmp_path / "realname-A.out", (out_mtime, out_mtime))
        job = parse(
            make_text(
                row(
                    JobID="48819449",
                    JobName="quotajob",
                    User="youzhi",
                    State="FAILED",
                    ExitCode="3:0",
                    Submit="2026-08-23T08:00:00",
                    Start="2026-08-23T08:00:05",
                    End="2026-08-23T08:00:41",
                    ElapsedRaw="36",
                )
            ),
            fields=_FIELDS,
        )[0]
        picked = find_log_by_time(job, extra_dirs=[str(tmp_path)])
        return os.path.basename(picked) if picked else None

    @staticmethod
    def _stamp(text):
        from datetime import datetime

        return datetime.fromisoformat(text).timestamp()

    def test_an_empty_candidate_loses_to_a_written_one(self):
        """Even when the empty file is nearer the end. This is the reported case:
        stderr at 08:00:38, the touched-at-exit stdout at 08:00:41 = End."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            picked = self._pick(
                pathlib.Path(tmp),
                self._stamp("2026-08-23T08:00:38"),
                self._stamp("2026-08-23T08:00:41"),
            )
        assert picked == "realname-A.err", picked

    def test_stderr_wins_an_exact_tie(self):
        """`touch -r` gives both files one mtime, which is how the report built
        it. Nothing but the suffix can decide, and a post-mortem wants stderr."""
        import tempfile

        stamp = self._stamp("2026-08-23T08:00:41")
        with tempfile.TemporaryDirectory() as tmp:
            picked = self._pick(pathlib.Path(tmp), stamp, stamp, err_text="cause\n")
        assert picked == "realname-A.err", picked

    def test_timing_still_decides_between_two_written_files(self):
        """The control. Emptiness and the suffix are tie-breaks; the signal this
        function exists for is the mtime, and it must still be the signal -- the
        docstring's 135-of-148 result came from it."""
        import os
        import tempfile

        from slurmpast.logs import find_log_by_time

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            (tmp_path / "far.out").write_text("something\n")
            (tmp_path / "near.out").write_text("something\n")
            os.utime(tmp_path / "far.out", (self._stamp("2026-08-23T08:00:10"),) * 2)
            os.utime(tmp_path / "near.out", (self._stamp("2026-08-23T08:00:41"),) * 2)
            job = parse(
                make_text(
                    row(
                        JobID="48819449",
                        JobName="q",
                        User="youzhi",
                        State="FAILED",
                        ExitCode="3:0",
                        Submit="2026-08-23T08:00:00",
                        Start="2026-08-23T08:00:05",
                        End="2026-08-23T08:00:41",
                        ElapsedRaw="36",
                    )
                ),
                fields=_FIELDS,
            )[0]
            picked = find_log_by_time(job, extra_dirs=[str(tmp_path)])
            assert os.path.basename(picked) == "near.out", picked


class TestACollectiveFaultNeedsADeviceAndAPeer:
    """`nccl` was a pure text match, so a mis-attached log drew a *critical*
    "Collective communication fault" for a job whose entire allocation read
    `billing=1,cpu=1,mem=200M,node=1`. No GPU for NCCL to run on, and no peer rank
    to block on -- the finding's own explanation ("one rank diverged, died, or is
    slow, and the others block on it") describes a topology the job did not have.

    An audit of all eight rule families found this and `cuda-oom` are the only two
    that can contradict the allocation; every metric-derived family already guards
    its preconditions. So the fix is two guards in one function, sharing the tests
    the neighbouring families use.

    **A rank is not a task**, and this is where the report's own suggestion --
    `nodes > 1 or ntasks > 1` -- would have been wrong. The suite's `healthy_job`
    is `gres/gpu=3` on `node=1` with no NTasks recorded, and three GPUs on one node
    do collectives across each other. Taking that suggestion literally suppressed
    five real fault shapes this suite already pins; the existing tests caught it on
    the first run. Whichever of GPUs, tasks and nodes is largest is the rank count.
    """

    LOG = (
        "CUDA error: out of memory\n"
        "[E ProcessGroupNCCL.cpp:828] [Rank 3] Watchdog caught collective operation timeout\n"
    )

    def _codes(self, alloc_tres, nodes="1"):
        from slurmpast.diagnose import diagnose

        job = parse(
            make_text(
                row(
                    JobID="48819454",
                    JobName="j",
                    User="youzhi",
                    State="FAILED",
                    ExitCode="1:0",
                    Submit="2026-08-23T08:00:00",
                    Start="2026-08-23T08:00:00",
                    End="2026-08-23T08:01:00",
                    ElapsedRaw="60",
                    NNodes=nodes,
                    NCPUS="1",
                    AllocCPUS="1",
                    AllocTRES=alloc_tres,
                )
            ),
            fields=_FIELDS,
        )[0]
        return {f.code for f in diagnose(job, log_text=self.LOG).findings}

    def test_the_reported_job_gets_neither_finding(self):
        codes = self._codes("billing=1,cpu=1,mem=200M,node=1")
        assert "nccl" not in codes and "cuda-oom" not in codes, codes

    def test_one_gpu_alone_can_oom_but_cannot_collective(self):
        """The discriminating middle case. A single GPU is a device, so the OOM
        stands; it is not a peer, so the collective does not."""
        codes = self._codes("billing=1,cpu=1,gres/gpu=1,mem=8G,node=1")
        assert "cuda-oom" in codes
        assert "nccl" not in codes, codes

    def test_several_gpus_on_one_node_are_peers(self):
        """The control the report's suggestion would have broken."""
        assert "nccl" in self._codes("billing=4,cpu=4,gres/gpu=3,mem=200G,node=1")

    def test_gpus_across_nodes_are_peers_too(self):
        assert "nccl" in self._codes("billing=2,cpu=2,gres/gpu=2,mem=16G,node=2", nodes="2")


class TestANameMatchBeatsATimingDecoy:
    """The narrowing the report made to its own finding, kept honest.

    A decoy with a matching mtime only wins when nothing matches by *name*. Given
    a log named with `%j` in the job's WorkDir, that path is found first and the
    decoy is never considered -- so the fabrication needs a fixed log name
    (`train.err`, `logs/run.err`) rather than the Slurm default.

    Pinned because it is load-bearing for how far the finding reaches, and because
    the candidate ranking was changed in the same round for a different reason:
    an assertion that name beats timing is what stops that change quietly widening
    the blast radius later.
    """

    def test_the_job_named_log_wins_and_is_not_marked_a_guess(self, tmp_path):
        from slurmpast.logs import assign_logs

        work = tmp_path / "work"
        decoy = tmp_path / "decoy"
        work.mkdir()
        decoy.mkdir()
        (work / "gpuless-48819454.err").write_text("real: quota exceeded\n")
        (decoy / "x.err").write_text("DECOY: CUDA error: out of memory\n")
        stamp = 1787000441
        for path in (work / "gpuless-48819454.err", decoy / "x.err"):
            os.utime(path, (stamp, stamp))

        job = parse(
            make_text(
                row(
                    JobID="48819454",
                    JobName="gpuless",
                    User="youzhi",
                    State="FAILED",
                    ExitCode="3:0",
                    Submit="2026-08-23T08:00:00",
                    Start="2026-08-23T08:00:05",
                    End="2026-08-23T08:00:41",
                    ElapsedRaw="36",
                    NCPUS="1",
                    AllocCPUS="1",
                    NNodes="1",
                    WorkDir=str(work),
                    AllocTRES="billing=1,cpu=1,mem=200M,node=1",
                )
            ),
            fields=_FIELDS,
        )[0]
        path, inferred = assign_logs([job], extra_dirs=[str(decoy)])[job.job_id]
        assert os.path.basename(path) == "gpuless-48819454.err", path
        assert inferred is False, "a name match is certain and must not carry the timing hedge"


class TestARefusedRowIsCounted:
    """The one part of SP-1 this round first declined, reopened by the reporter.

    The original ask was "count what you rejected instead of silently binning it
    into `open_ended`". The binning half was fixed by the parser; the counting
    half was recorded as not-done, on the stated grounds that there was no channel
    from `parse` to a front end. The reporter's feedback answered that -- `--json`
    is a channel that already exists, and it needs no change to `parse`'s
    signature. It was right, so the count now ships.

    `parse` fills an optional dict; `Sacct` holds the last query's; `--json` emits
    it **only when non-zero**, so a well-formed cluster's payload is byte-identical
    to before and no existing consumer moves.

    One counter, not the two first written. A "first field is not a JobID" counter
    cannot fire: `_records` only opens a record on a line whose head is already
    JobID-shaped, and JobID is field 0, so the in-`parse` test re-asks a settled
    question. It was removed rather than shipped reading a permanent 0, which
    would read as evidence of soundness.
    """

    def _clean(self):
        return make_text(
            row(
                JobID="1",
                JobName="j",
                User="u",
                State="COMPLETED",
                Start="2026-08-23T09:00:00",
                End="2026-08-23T09:01:00",
                ElapsedRaw="60",
            )
        )

    def test_a_clean_history_counts_nothing(self):
        stats = {}
        parse(self._clean(), fields=_FIELDS, stats=stats)
        assert stats["dropped_rows"] == {"shifted": 0}

    def test_a_shifted_row_is_counted(self):
        """A value holding the delimiter gives the row more fields than were
        asked for, so every column after it is misaligned. Refusing it is what
        this module has always done; saying so is the new part."""
        stats = {}
        text = self._clean().rstrip("\n") + "\nnot-a-job|x\n"
        parse(text, fields=_FIELDS, stats=stats)
        assert stats["dropped_rows"]["shifted"] == 1

    def test_noise_without_a_delimiter_costs_nothing(self):
        """The control. A line that is merely not a record is a continuation of
        the one above it, not a loss, and must not inflate the count -- the whole
        point of the reassembly is that such lines belong to the record above."""
        stats = {}
        text = self._clean().rstrip("\n") + "\nplain noise line\n"
        jobs = parse(text, fields=_FIELDS, stats=stats)
        assert stats["dropped_rows"]["shifted"] == 0
        assert [j.job_id for j in jobs] == ["1"]

    def test_the_payload_is_unchanged_when_nothing_was_dropped(self, capsys):
        """The other control, and the one that protects every existing consumer:
        the key appears only when it has something to say."""
        from slurmpast import cli

        cli.main(["--demo", "--overview", "--json", "--no-color"])
        assert "dropped_rows" not in json.loads(capsys.readouterr().out)


class TestTheCpuFigureCarriesItsOwnLimits:
    """`TotalCPU` is summed over the *step's process tree*, and a whole class of
    parallel runtime leaves that tree on purpose.

    `parallelly::makeClusterPSOCK`, which backs R's `plan(multisession)` and is
    that ecosystem's default recommendation, reparents every worker to PID 1.
    Reported from a second cluster on a real job: eight workers genuinely running,
    24 minutes of wall time against ~4 hours of serial work, and slurmpast saying
    `0.1 of 8 cores busy` with `→ Try --cpus-per-task=1`. Taking that advice
    serialises the fan-out.

    The shape of the fix is the one this codebase already uses twice. `sizing.py`
    documents four rules that keep advice honest, two of which are about a
    measurement that lies in a known direction — `Elapsed` on a TIMEOUT bounds
    runtime from below, `MaxRSS` under `jobacct_gather/linux` bounds memory from
    above, and the second is *worded from the cluster* via `site.maxrss_caveat()`.
    `TotalCPU` is the third such measurement and had no equivalent. It is also the
    only one whose absence points at **shrinking** an allocation that was in use.

    **Caveated, not suppressed.** `_CPU_TIME_ALREADY_EXPLAINED` is the wrong
    instrument: that set is for states where the number is garbage, and here the
    number is real work really done — it is just not all of it.
    """

    def _job(self):
        return parse(
            make_text(
                row(
                    JobID="48728837",
                    JobName="rcchelp",
                    User="youzhi",
                    Partition="broadwl",
                    State="COMPLETED",
                    ExitCode="0:0",
                    Submit="2026-08-01T09:00:00",
                    Start="2026-08-01T09:00:00",
                    End="2026-08-01T09:24:22",
                    ElapsedRaw="1462",
                    Timelimit="04:00:00",
                    TimelimitRaw="240",
                    NCPUS="8",
                    AllocCPUS="8",
                    NNodes="1",
                    ReqMem="57G",
                    AllocTRES="billing=8,cpu=8,mem=57G,node=1",
                ),
                row(
                    JobID="48728837.batch",
                    JobName="batch",
                    State="COMPLETED",
                    ElapsedRaw="1462",
                    TotalCPU="02:13.700",
                    NCPUS="8",
                    AllocCPUS="8",
                    MaxRSS="206028K",
                ),
            ),
            fields=_FIELDS,
        )[0]

    def _finding(self, monkeypatch, gather):
        from slurmpast import site
        from slurmpast.diagnose import diagnose

        monkeypatch.setattr(site, "site", lambda: site.Site(jobacct_gather_type=gather))
        for f in diagnose(self._job()).findings:
            if f.code == "cpu-overrequest":
                return f
        raise AssertionError("the finding under test did not fire")

    def test_the_finding_says_the_figure_is_a_lower_bound(self, monkeypatch):
        finding = self._finding(monkeypatch, "jobacct_gather/linux")
        assert "lower bound" in finding.evidence, finding.evidence
        assert "reparented" in finding.evidence

    def test_the_action_names_the_second_reading(self, monkeypatch):
        """The bare `Try --cpus-per-task=1` is what gets acted on, so the hedge has
        to reach it and not only the evidence above it."""
        finding = self._finding(monkeypatch, "jobacct_gather/linux")
        assert "detached worker pool" in finding.action, finding.action

    def test_a_cgroup_cluster_is_told_its_figure_is_sound(self, monkeypatch):
        """The control that makes this a *cluster* property rather than a
        universal disclaimer. Reparenting moves a process in the tree but not out
        of its cgroup, so a cgroup-gathering site counts those workers and has
        nothing to apologise for."""
        finding = self._finding(monkeypatch, "jobacct_gather/cgroup")
        assert "lower bound" not in finding.evidence, finding.evidence
        assert "are counted" in finding.evidence

    def test_an_unknown_cluster_hedges_rather_than_asserting(self, monkeypatch):
        """`site`'s own rule: None is not False, so the pessimistic wording is
        only justified when `jobacct_gather/linux` is confirmed."""
        finding = self._finding(monkeypatch, "")
        assert "may miss" in finding.evidence, finding.evidence

    def test_the_finding_is_not_suppressed(self, monkeypatch):
        """The other control. The reported figure is a lower bound, not garbage:
        0.1 of 8 cores really was accounted, and a reader with a genuinely idle
        allocation still needs to be told."""
        assert self._finding(monkeypatch, "jobacct_gather/linux") is not None

    def test_the_paste_ready_advice_carries_it_too(self, monkeypatch):
        """The highest-value half: these `#SBATCH` lines were verified on a second
        cluster to be pasted into a script verbatim and accepted by `sbatch`
        unmodified, so an un-caveated undercount here is executed, not just read."""
        from slurmpast import site
        from slurmpast.sizing import recommend

        monkeypatch.setattr(
            site, "site", lambda: site.Site(jobacct_gather_type="jobacct_gather/linux")
        )
        jobs = [self._job()._replace(job_id=str(60000 + i)) for i in range(5)]
        cpu = [a for a in recommend(jobs) if a.flag == "--cpus-per-task"]
        assert cpu, "the workload should draw CPU advice"
        assert cpu[0].verdict == "lower", cpu[0].verdict
        assert "lower bound" in cpu[0].caution, cpu[0].caution

    def test_advice_that_does_not_shrink_is_not_caveated(self, monkeypatch):
        """The control on scope. The caveat is about under-counting, so it belongs
        only on the verdict that would cut an allocation; a `keep` or `raise` is
        not put at risk by a figure that is too low."""
        from slurmpast import site
        from slurmpast.sizing import recommend

        monkeypatch.setattr(
            site, "site", lambda: site.Site(jobacct_gather_type="jobacct_gather/linux")
        )
        busy = self._job()
        jobs = [busy._replace(job_id=str(61000 + i), ncpus=1, alloc_cpus=1) for i in range(5)]
        for advice in recommend(jobs):
            if advice.flag == "--cpus-per-task" and advice.verdict != "lower":
                assert "lower bound" not in advice.caution, advice.caution


class TestANonUtf8StdoutStillProducesOutput:
    """Under a valid non-UTF-8 locale every text mode emitted **zero bytes**.

    Not degraded output — none. `rc=1` and a `UnicodeEncodeError` traceback, on
    three of the six locales installed on the reporting host. `LC_ALL=C` is *not*
    the case that bites: PEP 538/540 coerce `C`/`POSIX` to UTF-8, so the setting
    people type in job scripts is rescued. A real 8-bit locale — `en_US`,
    `en_US.iso88591`, and `LANG=en_US` is ordinary in a site profile — gets no
    coercion because it is legitimate and Python honours it.

    Two layers, and `--ascii` only ever fixed the first:

    * the package's own glyphs (box, block, arrow, em dash), which `--ascii`
      switches — but only if the user knows to pass it;
    * **the data**, which it cannot touch. A job name is arbitrary user-controlled
      text arriving from Slurm, and one job named `\u30d5\u30a1\u30a4\u30eb` in the queried
      window took down every text mode for every user querying that window,
      including users who did not submit it once `--all-users` is in play.

    So `reconfigure(errors="backslashreplace")` is the fix that closes both, and
    auto-selecting `--ascii` from the encoding is what stops the reader needing to
    know about the first.
    """

    MODES = ("--plain", "--overview", "--patterns", "--sizing", "--nodes")

    def _run(self, *argv):
        # Bytes. The child writes latin-1 by construction, so `text=True` decodes
        # its stdout as UTF-8 and raises in the *harness* -- which looks exactly
        # like a tool failure and is not one. That mistake made this test appear
        # to prove something it does not; see the ascii test below.
        return subprocess.run(
            [sys.executable, "-m", "slurmpast", "--demo", "--no-color", *argv],
            capture_output=True,
            env={
                **os.environ,
                "PYTHONIOENCODING": "iso8859-1",
                "PYTHONPATH": str(pathlib.Path(__file__).resolve().parent.parent / "src"),
            },
            timeout=120,
        )

    @pytest.mark.parametrize("mode", MODES)
    def test_every_text_mode_still_emits_something(self, mode):
        done = self._run(mode)
        stderr = done.stderr.decode("utf-8", "replace")
        # 0 or 1: the post-mortem paths exit 1 when they have a critical finding,
        # which the demo history does. The defect was rc=1 *with no output at all*.
        assert done.returncode in (0, 1), stderr[-400:]
        assert done.stdout, "zero bytes is the defect"
        assert "UnicodeEncodeError" not in stderr

    # A job name from the reporting cluster's real accounting, not a synthetic
    # string: `48819177|\u00fcn\u00ef \u30d5\u30a1\u30a4\u30eb job`.
    _DATA_CASE = r"""
import sys
from slurmpast import cli, sacct
FIELDS = sacct.Sacct().fields
row = {"JobID": "48819177", "User": "youzhi",
       "JobName": "\u00fcn\u00ef \u30d5\u30a1\u30a4\u30eb job",
       "State": "COMPLETED", "Submit": "2026-08-23T09:00:00",
       "Start": "2026-08-23T09:00:00", "End": "2026-08-23T09:10:00",
       "ElapsedRaw": "600", "NCPUS": "1", "AllocCPUS": "1", "NNodes": "1"}
def fake(args):
    if "--helpformat" in args:
        return " ".join(FIELDS)
    if args and args[0] in ("squeue", "scontrol", "sinfo"):
        return ""
    return "\x1f".join(row.get(f, "") for f in FIELDS) + "\n"
sacct._run = fake
sys.exit(cli.main(["--overview", "--plain", "--no-color", "-S", "now-1days"]))
"""

    def test_a_job_name_outside_the_encoding_does_not_abort_the_report(self):
        """The layer `--ascii` cannot reach, and the one the cases above miss.

        Those run `--demo`, whose job names are all ASCII, so auto-`--ascii` alone
        carries them and they pass with the encode-safety removed -- the same
        blind spot the tool had. A job name is arbitrary user-controlled text
        arriving from Slurm, and it is the answer rather than the chrome: no flag
        can substitute it away.
        """
        # Bytes, not text: the child writes latin-1 by construction, so decoding
        # its stdout as UTF-8 raises in the *test*. That failure is itself a
        # demonstration that the child produced output at all.
        done = subprocess.run(
            [sys.executable, "-c", self._DATA_CASE],
            capture_output=True,
            env={
                **os.environ,
                "PYTHONIOENCODING": "iso8859-1",
                "PYTHONPATH": str(pathlib.Path(__file__).resolve().parent.parent / "src"),
            },
            timeout=120,
        )
        stderr = done.stderr.decode("utf-8", "replace")
        assert "UnicodeEncodeError" not in stderr, stderr[-400:]
        assert done.stdout, "zero bytes is the defect"
        # The overview lists job *names*. `ünï` is representable in latin-1 and
        # survives as itself; the Katakana is not and comes through escaped, which
        # is the whole point of `backslashreplace` -- ugly, reversible, and never
        # the difference between a report and nothing.
        assert "\u00fcn\u00ef".encode("iso8859-1") in done.stdout, done.stdout[:200]
        assert b"\\u30d5" in done.stdout, "the unencodable name should be escaped, not fatal"

    def test_ascii_is_selected_from_the_encoding_without_the_flag(self):
        """The reader should not have to know `--ascii` exists to get output from
        a terminal that cannot draw. The flag stays as an override."""
        from slurmpast.cli import _encoding_cannot_draw

        assert _encoding_cannot_draw(io.TextIOWrapper(io.BytesIO(), encoding="iso8859-1"))
        assert not _encoding_cannot_draw(io.TextIOWrapper(io.BytesIO(), encoding="utf-8"))

    def test_what_the_auto_ascii_half_actually_buys_is_legibility(self):
        """Stated precisely, because it is easy to overclaim.

        The report says the encode-safety "alone closes every case", and it is
        right: with `backslashreplace` in place, removing the auto-`--ascii`
        selection leaves every mode exiting 0 with output. What it leaves is
        output whose box drawing has become `\\u2502` escapes -- present, honest
        and unreadable.

        So this half is not a correctness fix and should not be tested as one. It
        is tested for what it does: no escaped box glyphs on a terminal that
        cannot encode them.
        """
        # The single-job screen, because that is where the gauges are -- the list
        # views' non-ASCII is all latin-1-representable, so they look identical
        # either way and would make this test pass for no reason.
        rendered = self._run("5100057").stdout
        assert rendered
        assert rb"\\u2588" not in rendered, "the gauge bar came through as escapes"
        assert rb"\\u25cf" not in rendered, "the bullet came through as escapes"
        assert b"#" in rendered, "the ASCII gauge should have been substituted"


class TestTheUserIsResolvableWithoutAnEnvironment:
    """`sbatch --export=NONE` leaves no identity, and three of the four modes
    aborted with an unhandled `OSError` traceback — the three a script would use.

    `getpass.getuser()` reads the environment and then `pwd`, and raises when both
    fail. That is reachable with a documented, unmodified Slurm flag, and some
    sites set `SBATCH_EXPORT=NONE` cluster-wide. It degrades that far because the
    reporting cluster's compute nodes carry no passwd entry for the user — `id -un`
    answers "cannot find name for user ID 940740146" — so the whole class of
    failure is invisible on the login node where the tool was written.

    The uid is not a consolation prize: `sacct -u 940740146` returns that user's
    rows, verified on a live cluster. It is the identity the accounting database
    keyed on.
    """

    def _blank_environment(self, monkeypatch):
        import pwd

        for var in ("USER", "LOGNAME", "LNAME", "USERNAME", "HOME", "SLURM_JOB_USER"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(
            pwd, "getpwuid", lambda uid: (_ for _ in ()).throw(KeyError("uid not found"))
        )

    def test_the_uid_is_used_when_nothing_else_answers(self, monkeypatch):
        from slurmpast.sacct import current_user

        self._blank_environment(monkeypatch)
        assert current_user() == str(os.getuid())

    def test_slurms_own_variable_is_preferred_to_the_bare_uid(self, monkeypatch):
        """`SLURM_JOB_USER` survives `--export=NONE`, because Slurm re-exports its
        own variables, and a name reads better than a number."""
        from slurmpast.sacct import current_user

        self._blank_environment(monkeypatch)
        monkeypatch.setenv("SLURM_JOB_USER", "youzhi")
        assert current_user() == "youzhi"

    def test_the_ordinary_environment_is_unchanged(self, monkeypatch):
        """The control: none of this may alter who the tool asks about normally.

        `LOGNAME` as well as `USER`, because `getpass.getuser()` reads LOGNAME
        first and leaving it set was enough to make this test pass for the wrong
        reason on a developer machine.
        """
        from slurmpast.sacct import current_user

        monkeypatch.setenv("LOGNAME", "alice")
        monkeypatch.setenv("USER", "alice")
        assert current_user() == "alice"

    def test_no_traceback_reaches_the_scriptable_modes(self, monkeypatch, capsys):
        """The defect as filed was a traceback on `--plain`/`--json`/`--overview`
        while the TUI printed one clean line."""
        from slurmpast import cli

        self._blank_environment(monkeypatch)
        monkeypatch.setattr("slurmpast.sacct._run", lambda args: "")
        code = cli.main(["--overview", "--plain", "--no-color", "-S", "now-1hours"])
        assert code in (0, 2), code
        assert "Traceback" not in capsys.readouterr().err


class TestAnUnreadableLogIsNotReportedAsDeleted:
    """`os.path.isfile` answers False for ENOENT and EACCES alike, so a log behind
    a mode-700 home was reported as "moved or deleted".

    Not a corner case on a shared cluster and impossible to see on a single-user
    machine, which is where the message was written: over 12 hours of other users'
    jobs, 104 of the 106 records naming a log path were unreadable rather than
    absent, so the claim was wrong 98% of the time it appeared about a foreign job.
    The file may well be exactly where the record says.

    Same shape as two findings elsewhere in this family -- a failed call's own
    explanation discarded and the gap filled with a guess -- and the errno was
    available the whole time.
    """

    def _job(self, tmp_path, path):
        return parse(
            make_text(
                row(
                    JobID="48781550",
                    JobName="arr",
                    User="trabbani",
                    State="FAILED",
                    ExitCode="1:0",
                    Submit="2026-08-23T09:00:00",
                    Start="2026-08-23T09:00:00",
                    End="2026-08-23T09:10:00",
                    ElapsedRaw="600",
                    NCPUS="1",
                    AllocCPUS="1",
                    NNodes="1",
                    StdOut=str(path),
                )
            ),
            fields=_FIELDS,
        )[0]

    @staticmethod
    def _blocked(tmp_path):
        private = tmp_path / "private"
        (private / "logs").mkdir(parents=True)
        target = private / "logs" / "job.out"
        target.write_text("real content\n")
        private.chmod(0o000)
        return target, private

    def _render(self, job):
        """Rendered, with whitespace collapsed.

        The report wraps prose around a path, so "moved or deleted" splits across
        two lines the moment the path is long enough -- which a local `tmp_path`
        is not and CI's `/tmp/pytest-of-runner/pytest-0/...` is. Asserting on the
        raw text passed locally and failed on every CI job. `" ".join(split())`
        is the idiom the rest of this suite already uses for wrapped output.
        """
        from slurmpast import report

        text, _verdict = report.render_job(job, style=report.Style(enabled=False))
        return " ".join(text.split())

    def test_an_unreadable_log_is_not_reported_as_deleted(self, tmp_path):
        """The test the report asks for by name."""
        target, private = self._blocked(tmp_path)
        try:
            rendered = self._render(self._job(tmp_path, target))
        finally:
            private.chmod(0o700)
        assert "moved" not in rendered and "deleted" not in rendered, rendered
        assert "not readable by you" in rendered
        assert "trabbani" in rendered, "the owner is on the record and should be named"

    def test_a_genuinely_absent_log_keeps_the_old_wording(self, tmp_path):
        """The control. ENOENT really does mean moved or deleted, and that
        sentence is right -- the fix must not cost it."""
        rendered = self._render(self._job(tmp_path, tmp_path / "gone.out"))
        assert "moved or deleted" in rendered, rendered

    def test_the_probe_tells_the_three_apart(self, tmp_path):
        from slurmpast.logs import probe_path

        target, private = self._blocked(tmp_path)
        try:
            assert probe_path(str(target)) == "unreadable"
        finally:
            private.chmod(0o700)
        assert probe_path(str(tmp_path / "nope")) == "absent"
        assert probe_path(str(target)) == "found"

    def test_an_errno_that_is_neither_is_not_guessed_at(self, tmp_path):
        """The third state, which shipped without a test of its own.

        `absent` and `unreadable` cover the two errnos anyone thinks of; the
        `unknown` branch exists so a stat that fails for some other reason is
        reported rather than folded into one of them, and an untested branch that
        only fires on an exotic errno is exactly the kind that rots.

        Two real triggers rather than a patched `os.stat`, so this tests the errno
        handling rather than the mock: a path component over `NAME_MAX`
        (ENAMETOOLONG, errno 36) and a symlink pointing at itself (ELOOP).
        """
        import os

        from slurmpast.logs import probe_path

        assert probe_path(str(tmp_path / ("x" * 300) / "j.out")) == "unknown"

        loop = tmp_path / "loop"
        os.symlink(loop, loop)
        assert probe_path(str(loop)) == "unknown"

    def test_the_unknown_state_names_the_refusal_rather_than_a_cause(self, tmp_path):
        """And the sentence it produces, which had no test at all. It must not
        borrow either of the other two claims -- the whole point is that the tool
        does not know which is true."""
        job = self._job(tmp_path, tmp_path / ("x" * 300) / "j.out")
        rendered = self._render(job)
        assert "could not be checked" in rendered, rendered
        for borrowed in ("moved", "deleted", "not readable by you"):
            assert borrowed not in rendered, borrowed

    def test_the_payload_carries_the_path_and_the_reason(self, tmp_path):
        """Secondary half: `--json` collapsed every miss to `null`, so a consumer
        could not see which path was tried, let alone why it failed."""
        from slurmpast.cli import _job_json
        from slurmpast.diagnose import diagnose

        target, private = self._blocked(tmp_path)
        job = self._job(tmp_path, target)
        try:
            payload = _job_json(job, None, diagnose(job))
        finally:
            private.chmod(0o700)
        assert payload["log"] is None
        assert payload["log_expected"] == {"path": str(target), "status": "unreadable"}

    def test_no_logs_still_stats_nothing(self, tmp_path):
        """The guard the report singles out as already correct, and which the
        first version of this fix broke: computing a status means stat-ing the
        path, and under `--no-logs` the filesystem is not to be touched at all."""
        import os

        from slurmpast.cli import _job_json
        from slurmpast.diagnose import diagnose

        target, private = self._blocked(tmp_path)
        job = self._job(tmp_path, target)
        seen = []
        real = os.stat
        os.stat = lambda path, *a, **k: seen.append(str(path)) or real(path, *a, **k)
        try:
            payload = _job_json(job, None, diagnose(job), no_logs=True)
        finally:
            os.stat = real
            private.chmod(0o700)
        # Present but empty, not absent: the key is unconditional so the per-job
        # value count stays fixed, and `null` is the honest answer for a question
        # that was deliberately not asked.
        assert payload["log_expected"] == {"path": None, "status": None}
        assert not [s for s in seen if "private" in s], seen


class TestNoLogsTouchesNoFilesystem:
    """`--no-logs` promises the filesystem is not consulted, and one new field
    broke it while looking strictly more informative.

    The sibling guard to `TestTheDemoAsksTheRealClusterNothing`. Both leaks that
    have happened here were additions to a payload that quietly reached outside
    the process -- `--sizing` running `sinfo` under `--demo`, and `--json`
    stat-ing a recorded log path under `--no-logs` -- and neither showed in the
    output. Counting the calls is the only way to see it, so every mode is counted
    rather than the one that broke.
    """

    MODES = (
        ("--plain",),
        ("--json",),
        ("--failed",),
        ("--overview",),
        ("900002",),
        ("900002", "--json"),
    )

    def _runner(self, recorded):
        text = make_text(
            row(
                JobID="900002",
                JobName="j",
                User="u",
                State="FAILED",
                ExitCode="1:0",
                Submit="2026-08-23T09:00:00",
                Start="2026-08-23T09:00:00",
                End="2026-08-23T09:10:00",
                ElapsedRaw="600",
                NCPUS="1",
                AllocCPUS="1",
                NNodes="1",
                StdOut=str(recorded),
            )
        ).replace("|", SAFE_DELIMITER)

        def run_sacct(args):
            if "--helpformat" in args:
                return " ".join(_FIELDS)
            if args and args[0] in ("squeue", "scontrol", "sinfo"):
                return ""
            return text

        return run_sacct

    @pytest.mark.parametrize("mode", MODES, ids=[" ".join(m) for m in MODES])
    def test_the_recorded_path_is_never_stat_ed(self, monkeypatch, capsys, tmp_path, mode):
        from slurmpast import cli

        recorded = tmp_path / "sentinel-dir" / "job.out"
        monkeypatch.setattr("slurmpast.sacct._run", self._runner(recorded))
        seen = []
        real = os.stat
        monkeypatch.setattr(
            os, "stat", lambda path, *a, **k: seen.append(str(path)) or real(path, *a, **k)
        )
        cli.main([*mode, "--no-logs", "--no-color", "-S", "now-1days"])
        capsys.readouterr()
        assert not [s for s in seen if "sentinel-dir" in s], seen

    def test_without_the_flag_it_does_look(self, monkeypatch, capsys, tmp_path):
        """The control, and the one that stops this passing for the wrong reason:
        if nothing ever stat'd the recorded path, the tests above would be
        vacuous."""
        from slurmpast import cli

        recorded = tmp_path / "sentinel-dir" / "job.out"
        monkeypatch.setattr("slurmpast.sacct._run", self._runner(recorded))
        seen = []
        real = os.stat
        monkeypatch.setattr(
            os, "stat", lambda path, *a, **k: seen.append(str(path)) or real(path, *a, **k)
        )
        cli.main(["900002", "--json", "--no-color"])
        capsys.readouterr()
        assert [s for s in seen if "sentinel-dir" in s], "the probe should have run here"


class TestARecycledJobIdIsNotARequeue:
    """`sacct -D -j <id>` carries no window, so it answers with every job that
    has *ever* held the id.

    Measured on Mercury (UChicago Booth), Slurm 25.11.3, RHEL 9.8: all 40 ids
    sampled from three recent days came back with a second row, seven years
    older and belonging to somebody else. The counter had wrapped and slurmdbd
    still held the 2019 records::

        509531|mercury|aranda   |standard|dsa-3-20                          |2019-03-03
        509531|mercury|cmbrennan|highmem |did_bigquery_priority_general_2026|2026-08-19

    `_fold_incarnations` keyed on the id alone, so every per-job view on that
    cluster printed `requeued 1x` -- and the incarnation it attributed to the
    reader was a stranger's job. Windowed queries were never affected: `-S/-E`
    filters the old rows out at sacct, so only the per-job path, which has no
    window to pass, ever saw them.
    """

    def _jobs(self, *incarnations):
        return parse(
            make_text(
                *[
                    row(
                        JobID="509531",
                        Cluster=cluster,
                        User=user,
                        UID=uid,
                        JobName=name,
                        State="COMPLETED",
                        ExitCode="0:0",
                        Submit=stamp,
                        Start=stamp,
                        End=stamp,
                        ElapsedRaw="60",
                    )
                    for cluster, user, uid, name, stamp in incarnations
                ]
            ),
            fields=_FIELDS,
        )

    MERCURY_2019 = ("mercury", "aranda", "5101", "dsa-3-20", "2019-03-03T18:35:08")
    MERCURY_2026 = ("mercury", "cmbrennan", "7742", "did_bigquery", "2026-08-19T22:21:07")

    def test_the_stranger_is_not_folded_in_as_a_requeue(self):
        (job,) = self._jobs(self.MERCURY_2019, self.MERCURY_2026)
        assert job.earlier == (), "a recycled id is not this job's history"
        assert job.user == "cmbrennan", "the newest incarnation is still the job"

    def test_a_genuine_requeue_still_folds(self):
        """The control. Without it the fix above passes by never folding at all,
        which would delete the requeue reporting this file exists to protect."""
        first = ("mercury", "cmbrennan", "7742", "did_bigquery", "2026-08-19T22:21:07")
        second = ("mercury", "cmbrennan", "7742", "did_bigquery", "2026-08-19T23:40:00")
        (job,) = self._jobs(first, second)
        assert len(job.earlier) == 1, "a real requeue keeps its earlier attempt"
        assert job.submit == "2026-08-19T23:40:00"

    def test_a_different_cluster_sharing_the_id_is_not_folded(self):
        """One slurmdbd can serve several clusters, and ids are per-cluster.

        The two rows need distinct `Submit` values to reach the fold at all:
        `parse` keys allocations on `(JobID, Submit)`, so same-id same-instant
        rows collapse a step earlier and this would assert nothing.
        """
        other = ("midway3", "cmbrennan", "7742", "did_bigquery", "2026-08-18T04:00:00")
        (job,) = self._jobs(other, self.MERCURY_2026)
        assert job.earlier == ()
        assert job.cluster == "mercury"

    def test_only_the_stranger_and_what_is_behind_it_is_dropped(self):
        """The trailing run is the job's own history. An attempt between the
        stranger and the newest row is a real requeue and has to survive."""
        middle = ("mercury", "cmbrennan", "7742", "did_bigquery", "2026-08-19T20:00:00")
        (job,) = self._jobs(self.MERCURY_2019, middle, self.MERCURY_2026)
        assert len(job.earlier) == 1
        assert job.earlier[0].submit == "2026-08-19T20:00:00"

    def test_a_blank_identity_folds_as_before(self):
        """Conservative on missing data: sacct leaves these blank often enough
        that a blank must not split a requeue that really happened."""
        blank_a = ("", "", "", "work", "2026-08-19T22:21:07")
        blank_b = ("", "", "", "work", "2026-08-19T23:40:00")
        (job,) = self._jobs(blank_a, blank_b)
        assert len(job.earlier) == 1

    def test_the_id_still_yields_exactly_one_job(self):
        """`logs.resolve` and `cli` both key dicts on `job_id`, so the
        one-Job-per-id contract in `_fold_incarnations` is load-bearing: two Jobs
        sharing an id would hand one of them the other's log."""
        jobs = self._jobs(self.MERCURY_2019, self.MERCURY_2026)
        assert len(jobs) == 1


class TestTheMemorySlackCaveatIsWordedFromTheCluster:
    """The `memory-slack` finding hardcoded a sentence about MaxRSS that is only
    true under `jobacct_gather/linux`.

    `site.maxrss_caveat()` exists so this is asked of the cluster rather than
    assumed, and `diagnose` already used it for the two findings immediately
    above this one -- `host-oom` and `rss-above-limit`. This one was missed, so
    on Mercury (`jobacct_gather/cgroup`) a single run of the tool printed both
    "MaxRSS comes from the cgroup peak here" under `--sizing` and "MaxRSS
    over-reports multi-process jobs" in the per-job view, about the same figure.
    """

    def _finding(self, monkeypatch, gather):
        from slurmpast.diagnose import diagnose

        monkeypatch.setattr("slurmpast.site._CACHE", [Site(jobacct_gather_type=gather)])
        job = parse(
            make_text(
                row(
                    JobID="700100",
                    JobName="slack",
                    User="youzhi",
                    State="COMPLETED",
                    ExitCode="0:0",
                    Submit="2026-08-01T09:00:00",
                    Start="2026-08-01T09:00:00",
                    End="2026-08-01T11:00:00",
                    ElapsedRaw="7200",
                    Timelimit="04:00:00",
                    TimelimitRaw="240",
                    NCPUS="4",
                    AllocCPUS="4",
                    NNodes="1",
                    ReqMem="128G",
                    AllocTRES="billing=4,cpu=4,mem=128G,node=1",
                    TotalCPU="02:00:00",
                ),
                row(
                    JobID="700100.batch",
                    JobName="batch",
                    State="COMPLETED",
                    ElapsedRaw="7200",
                    MaxRSS="19660800K",
                    TotalCPU="02:00:00",
                ),
            ),
            fields=_FIELDS,
        )[0]
        for f in diagnose(job).findings:
            if f.code == "memory-slack":
                return f
        raise AssertionError("the finding under test did not fire")

    def test_a_cgroup_cluster_is_not_told_the_figure_over_reports(self, monkeypatch):
        finding = self._finding(monkeypatch, "jobacct_gather/cgroup")
        assert "cgroup peak" in finding.action, finding.action
        assert "over-report" not in finding.action, finding.action

    def test_a_linux_gathering_cluster_still_gets_the_warning(self, monkeypatch):
        """The control. The caveat is a *cluster* property, not a sentence that
        was simply deleted -- under the process-tree gatherer it still holds."""
        finding = self._finding(monkeypatch, "jobacct_gather/linux")
        assert "sums RSS" in finding.action, finding.action
        assert "upper bound" in finding.action, finding.action

    def test_the_advice_flag_survives_the_rewording(self, monkeypatch):
        """`format_mem_flag`, not `format_bytes`: the pasteable spelling is the
        reason this action reads the way it does, and a reworded sentence must
        not quietly take it back to `--mem=25.0 GiB`."""
        finding = self._finding(monkeypatch, "jobacct_gather/cgroup")
        assert "--mem=25G" in finding.action, finding.action

    def test_it_agrees_with_what_sizing_says_on_the_same_cluster(self, monkeypatch):
        """The defect was not the wording on its own but that two surfaces
        contradicted each other about one number in one run."""
        monkeypatch.setattr(
            "slurmpast.site._CACHE", [Site(jobacct_gather_type="jobacct_gather/cgroup")]
        )
        finding = self._finding(monkeypatch, "jobacct_gather/cgroup")
        assert maxrss_caveat() in finding.action


class TestSubMegabyteFiguresCarryAUnit:
    """`format_bytes` fell from MiB straight to raw bytes, so the two figures a
    reader most wants to compare arrived in units that cannot be compared by eye.

    Both seen on Mercury in one job detail: `read 9.5 GiB` beside
    `rate 488928 B/s`, and a step table with `612794 B` in the same column as
    `79.0 MiB`.
    """

    def test_a_sub_megabyte_figure_reads_in_kib(self):
        from slurmpast.duration import format_bytes

        assert format_bytes(488928) == "477.5 KiB"
        assert format_bytes(612794) == "598.4 KiB"

    def test_the_byte_floor_survives(self):
        """The control. Below 1 KiB bytes are the honest unit, and `0` must not
        start rendering as `0.0 KiB` -- `format_bytes` promises `n/a` for None
        and a real `0 B` for zero, and a test already pins that."""
        from slurmpast.duration import format_bytes

        assert format_bytes(0) == "0 B"
        assert format_bytes(1023) == "1023 B"
        assert format_bytes(1024) == "1.0 KiB"

    def test_the_larger_tiers_are_untouched(self):
        from slurmpast.duration import format_bytes

        assert format_bytes(1024**2) == "1.0 MiB"
        assert format_bytes(1024**3) == "1.0 GiB"
        assert format_bytes(1024**4) == "1.0 TiB"
        assert format_bytes(None) == "n/a"
