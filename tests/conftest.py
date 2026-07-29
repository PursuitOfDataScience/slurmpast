"""Fixtures built from real Midway3 accounting records.

Every sample below is transcribed from live `sacct` output. They are the
regression corpus: each one caused a wrong number or a wrong diagnosis at some
point, so a change that breaks one is a change that reintroduces that bug.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from slurmpast.sacct import _FIELDS, parse  # noqa: E402
from slurmpast.site import Site, reset_cache  # noqa: E402

FIELDS = _FIELDS

# The cluster these fixtures were recorded on. Pinned for every test because
# several messages are worded from the site configuration -- MaxRSS means
# something different under jobacct_gather/cgroup -- and without this the suite
# would assert one thing on Midway3 and another on a CI runner with no scontrol
# at all. Tests that care about a different site override it explicitly.
RECORDED_SITE = Site(
    slurm_version="20.11.8",
    jobacct_gather_type="jobacct_gather/linux",
    accounting_storage_type="accounting_storage/slurmdbd",
    tres=("cpu", "mem", "energy", "node", "billing", "fs/disk", "vmem", "pages", "gres/gpu"),
)


@pytest.fixture(autouse=True)
def _pinned_site(monkeypatch):
    """No test may reach the local scheduler for its configuration."""
    reset_cache()
    monkeypatch.setattr("slurmpast.site._CACHE", [RECORDED_SITE])
    yield
    reset_cache()


def _row(**kw):
    """Build one sacct row by FIELD NAME, never by position.

    Hand-positioned rows silently mis-assign every value the moment the field
    list changes -- which it did when the reader was widened from 27 fields to
    the full measurement set. Building by name makes the fixtures immune.
    """
    unknown = set(kw) - set(FIELDS)
    assert not unknown, "not sacct fields: %s" % sorted(unknown)
    return "|".join(str(kw.get(name, "")) for name in FIELDS)


# Public alias: other test modules build rows with this too.
row = _row


def make_text(*rows):
    return "\n".join(rows)


# --- job 47865145: cot-exp. 30-minute limit, TIMEOUT, 0.539 CPU-seconds. -----
# The record that proves a TIMEOUT is not evidence the job needed more time.
COT_EXP = make_text(
    _row(
        JobID="47865145",
        JobName="cot-exp",
        User="youzhi",
        Account="rcc-staff",
        Partition="test",
        QOS="test",
        State="TIMEOUT",
        ExitCode="0:0",
        Submit="2026-04-14T09:12:03",
        Start="2026-04-14T09:12:04",
        End="2026-04-14T09:42:30",
        Elapsed="00:30:26",
        Timelimit="00:30:00",
        ReqMem="80Gn",
        ReqCPUS="6",
        AllocTRES="billing=6,cpu=6,gres/gpu=1,mem=80G,node=1",
        NodeList="midway3-0385",
        CPUTime="03:02:36",
    ),
    _row(
        JobID="47865145.batch",
        JobName="batch",
        State="CANCELLED",
        ExitCode="0:15",
        Elapsed="00:30:27",
        TotalCPU="00:00.539",
        CPUTime="03:02:42",
        AllocTRES="cpu=6,gres/gpu=1,mem=80G,node=1",
    ),
    _row(
        JobID="47865145.extern",
        JobName="extern",
        State="COMPLETED",
        ExitCode="0:0",
        Elapsed="00:30:26",
        TotalCPU="00:00:00",
        CPUTime="03:02:36",
    ),
)

# --- job 43742638: OOM, MaxRSS 51.25 GiB against a 40 GiB limit. -------------
# Proves MaxRSS sums shared pages across the process tree: a value above the
# hard limit cannot be a working set.
OOM_JOB = make_text(
    _row(
        JobID="43742638",
        JobName="rc-tok-github_code",
        State="OUT_OF_MEMORY",
        ExitCode="0:125",
        Start="2026-02-01T02:00:00",
        End="2026-02-01T05:54:24",
        Elapsed="03:54:24",
        Timelimit="08:00:00",
        ReqMem="40Gn",
        ReqCPUS="16",
        AllocTRES="billing=16,cpu=16,mem=40G,node=1",
        NodeList="midway3-0432",
        Partition="caslake",
    ),
    _row(
        JobID="43742638.batch",
        JobName="batch",
        State="OUT_OF_MEMORY",
        ExitCode="0:125",
        Start="2026-02-01T02:00:00",
        End="2026-02-01T05:54:24",
        Elapsed="03:54:24",
        TotalCPU="03:54:24",
        CPUTime="62:30:24",
        MaxRSS="53741792K",
        TRESUsageInTot="cpu=03:54:24,energy=0,fs/disk=67022736995,mem=53741792K,pages=0",
    ),
)

# --- job 51170455: midtrain. Healthy. The tool must stay silent here. --------
HEALTHY_JOB = make_text(
    _row(
        JobID="51170455",
        JobName="midtrain",
        State="COMPLETED",
        ExitCode="0:0",
        Start="2026-06-20T10:00:00",
        End="2026-06-20T11:52:49",
        Elapsed="01:52:49",
        Timelimit="02:00:00",
        ReqMem="200Gn",
        ReqCPUS="4",
        AllocTRES="billing=4,cpu=4,gres/gpu=3,mem=200G,node=1",
        NodeList="midway3-0372",
        Partition="test",
    ),
    _row(
        JobID="51170455.batch",
        JobName="batch",
        State="COMPLETED",
        ExitCode="0:0",
        Start="2026-06-20T10:00:00",
        End="2026-06-20T11:52:49",
        Elapsed="01:52:49",
        TotalCPU="05:31:39",
        CPUTime="07:31:16",
        MaxRSS="193517740K",
        TRESUsageInTot="cpu=05:31:14,energy=0,fs/disk=112710599158,mem=193517740K,pages=0",
    ),
)

# --- job 50108238: State=RUNNING, End=Unknown, months dead. -----------------
# sacct computes Elapsed as now-minus-start: 62 days. Summed into a GPU-hour
# total this single record was 65% of the figure.
STALE_JOB = make_text(
    _row(
        JobID="50108238",
        JobName="node-evaluation",
        State="RUNNING",
        Elapsed="62-22:51:15",
        Timelimit="36:00:00",
        Start="2026-05-25T17:06:09",
        End="Unknown",
        ReqMem="200Gn",
        ReqCPUS="4",
        AllocTRES="billing=4,cpu=4,gres/gpu=3,mem=200G,node=1",
        NodeList="midway3-0385",
        Partition="test",
    ),
)

# --- job 51709094: MaxRSS 4108K on batch vs 16439052K on extern. ------------
# A 4000x spread on one job. Reading a single step is wrong by that factor.
STEP_SPREAD_JOB = make_text(
    _row(
        JobID="51709094",
        JobName="node-test",
        State="COMPLETED",
        ExitCode="0:0",
        Start="2026-07-01T00:00:00",
        End="2026-07-01T00:05:00",
        Elapsed="00:05:00",
        Timelimit="01:00:00",
        ReqMem="64Gn",
        ReqCPUS="8",
        AllocTRES="billing=8,cpu=8,mem=64G,node=1",
        NodeList="midway3-0602",
        Partition="test",
    ),
    _row(
        JobID="51709094.batch",
        JobName="batch",
        State="COMPLETED",
        Elapsed="00:05:00",
        TotalCPU="00:04:30",
        CPUTime="00:40:00",
        MaxRSS="4108K",
    ),
    _row(
        JobID="51709094.extern",
        JobName="extern",
        State="COMPLETED",
        Elapsed="00:05:00",
        TotalCPU="00:00:00",
        CPUTime="00:40:00",
        MaxRSS="16439052K",
    ),
    # A second *work* step: the spread that matters is between steps that ran
    # something, not the structural batch/.extern difference.
    _row(
        JobID="51709094.0",
        JobName="srun",
        State="COMPLETED",
        Elapsed="00:05:00",
        TotalCPU="00:04:00",
        CPUTime="00:40:00",
        MaxRSS="16439052K",
    ),
)


def _oom_series():
    """rc-tok-github_code: the real hand-bisection, in submit order.

    48G cancelled, then OOM at 32, 32, 17, 12, 12, 14, 16, 18 -- and finally
    COMPLETED at 32G, a value that had already failed twice.
    """
    spec = [
        ("52127670", "48Gn", "CANCELLED by 940740146"),
        ("52128458", "32Gn", "OUT_OF_MEMORY"),
        ("52128871", "32Gn", "OUT_OF_MEMORY"),
        ("52129280", "17Gn", "OUT_OF_MEMORY"),
        ("52130519", "12Gn", "OUT_OF_MEMORY"),
        ("52130755", "12Gn", "OUT_OF_MEMORY"),
        ("52135269", "14Gn", "OUT_OF_MEMORY"),
        ("52135758", "16Gn", "OUT_OF_MEMORY"),
        ("52135774", "18Gn", "OUT_OF_MEMORY"),
        ("52139773", "32Gn", "COMPLETED"),
    ]
    rows = []
    for job_id, mem, state in spec:
        rows.append(
            _row(
                JobID=job_id,
                JobName="rc-tok-github_code",
                State=state,
                ExitCode="0:0",
                Start="2026-07-10T00:00:00",
                End="2026-07-10T00:20:00",
                Elapsed="00:20:00",
                Timelimit="08:00:00",
                ReqMem=mem,
                ReqCPUS="16",
                AllocTRES="billing=16,cpu=16,mem=%s,node=1" % mem.rstrip("n"),
                NodeList="midway3-0432",
                Partition="caslake",
            )
        )
        rows.append(
            _row(
                JobID=job_id + ".batch",
                JobName="batch",
                State=state.split()[0],
                Elapsed="00:20:00",
                TotalCPU="00:19:00",
                CPUTime="05:20:00",
                MaxRSS="12000000K",
            )
        )
    return make_text(*rows)


def _repeat_timeout_series(count=12):
    """A cot-exp-shaped run of identical timeouts, all hung."""
    rows = []
    for index in range(count):
        job_id = str(47865100 + index)
        rows.append(
            _row(
                JobID=job_id,
                JobName="cot-exp",
                State="TIMEOUT",
                ExitCode="0:0",
                Start="2026-04-14T09:00:00",
                End="2026-04-14T09:30:%02d" % (5 + index),
                Elapsed="00:30:%02d" % (5 + index),
                Timelimit="00:30:00",
                ReqMem="80Gn",
                ReqCPUS="6",
                AllocTRES="billing=6,cpu=6,gres/gpu=1,mem=80G,node=1",
                NodeList="midway3-0385",
                Partition="test",
            )
        )
        rows.append(
            _row(
                JobID=job_id + ".batch",
                JobName="batch",
                State="CANCELLED",
                Elapsed="00:30:%02d" % (5 + index),
                TotalCPU="00:00.5%02d" % index,
                CPUTime="03:02:36",
            )
        )
    return make_text(*rows)


@pytest.fixture
def cot_exp():
    return parse(COT_EXP)[0]


@pytest.fixture
def oom_job():
    return parse(OOM_JOB)[0]


@pytest.fixture
def healthy_job():
    return parse(HEALTHY_JOB)[0]


@pytest.fixture
def stale_job():
    return parse(STALE_JOB)[0]


@pytest.fixture
def step_spread_job():
    return parse(STEP_SPREAD_JOB)[0]


@pytest.fixture
def oom_series():
    return parse(_oom_series())


@pytest.fixture
def repeat_timeouts():
    return parse(_repeat_timeout_series())
