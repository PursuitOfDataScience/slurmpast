"""Every assumption about "the cluster" that turned out to be about *one* cluster.

This tool was written against Slurm 20.11.8 on Midway3, and each case below is a
place where that showed through -- verified against the Slurm documentation, the
release notes that changed the behaviour, or `scontrol show hostnames` itself.
None of them fail on Midway3, which is exactly why they need pinning.
"""

import os
import pathlib
import subprocess
from datetime import datetime

import pytest

from slurmpast import logs, model
from slurmpast import sacct as sacct_mod
from slurmpast.duration import parse_bytes
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

from .conftest import row

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
