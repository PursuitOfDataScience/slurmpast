"""Synthetic job history, for demos and for trying the tool without Slurm.

Every pattern here is modelled on a measured Midway3 history, so the dashboard
shows the shapes it was built to find rather than invented drama:

* a workload that hangs and times out repeatedly at an unchanged ``--time``
  (the real one did this 99 times out of 115, at 0.56s of CPU median)
* a ``--mem`` hand-search that ends by succeeding at a value which already OOM'd
* healthy training runs, so restraint is visible: they draw no findings
* one node with a markedly worse failure rate than its peers
* a long allocation that held GPUs and never computed

It is clearly labelled synthetic wherever it is used. Nobody should be able to
mistake a demo screenshot for a measurement.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .sacct import parse

# The synthetic cluster's own configuration, in `scontrol show config` form so it
# feeds site.site() exactly as a real cluster would. Pinned so `--demo` renders
# identically whether it runs on a login node or a laptop -- several messages are
# worded from JobAcctGatherType, and without this the demo changed by machine.
DEMO_SITE = """\
SLURM_VERSION           = 20.11.8
JobAcctGatherType       = jobacct_gather/linux
AccountingStorageType   = accounting_storage/slurmdbd
AccountingStorageTRES   = cpu,mem,energy,node,billing,fs/disk,vmem,pages,gres/gpu
"""

# The synthetic cluster's node sizes, pinned for the same reason DEMO_SITE is.
# `sizing.cpu_advice` clamps an upward recommendation to the partition's ceiling,
# which it learns by running `sinfo` -- so without this, `--demo --sizing` on a
# login node asks the *real* cluster how big its `test` nodes are and the demo
# changes by machine. Measured to be doing exactly that before this was added.
#
# Chosen well above anything the synthetic history requests (its largest ask is
# 16 cores), so the clamp never binds here and the demo's advice is unchanged.
# A demo that exercised the clamp would be worth having, but not at the cost of
# making this output a moving target for the CI check that reads it.
DEMO_PARTITIONS = {"test": (48, 196608)}

_FIELDS_ORDER = None  # resolved lazily from sacct._FIELDS


def _row(**kw) -> str:
    global _FIELDS_ORDER
    if _FIELDS_ORDER is None:
        from .sacct import _FIELDS

        _FIELDS_ORDER = _FIELDS
    unknown = set(kw) - set(_FIELDS_ORDER)
    if unknown:
        raise ValueError("not sacct fields: %s" % sorted(unknown))
    return "|".join(str(kw.get(name, "")) for name in _FIELDS_ORDER)


# The id the synthetic history counts up from; see :func:`history`.
FIRST_JOB_ID = 5100001
# Minutes between consecutive synthetic submissions. 58 jobs at this spacing span
# 00:00 to 12:35, so no series can run past midnight into the next day's records.
_SUBMIT_SPACING_MINUTES = 13
# What every synthetic job waited in the queue. Written into `Reserved` and used to
# place `Submit` before `Start`, so the two agree on screen.
_QUEUE_WAIT_SECONDS = 1


def _time_of_day(jid):
    """``HH:MM:SS`` that increases with the job id, without wrapping.

    Slurm hands out job ids in submission order, so a demo whose clock disagrees
    with its ids is a demo of something Slurm cannot produce. This was
    ``"0%d:00:00" % (jid % 9)``, which wrapped every ninth job: the ten runs of
    ``rc-tok-github_code`` all carry ``day=20``, so they listed 08:00, 07:00,
    06:00, 05:00, 05:00 -- the narrative backwards, with two runs sharing a
    timestamp.

    It fed a wrong number as well as a wrong order. ``sizing._latest`` picks the
    most recent run by ``start or submit`` to report what the workload currently
    asks for, so it picked 5100038 (17G) instead of the real last submission
    5100044 (32G) and the sizing screen advised "--mem raise to 42G (from 17.0
    GiB)". That is exactly the error ``_latest`` was introduced to fix, arriving
    through the demo's own fabricated timestamps rather than through the code
    under test.
    """
    total = (jid - FIRST_JOB_ID) * _SUBMIT_SPACING_MINUTES
    return "%02d:%02d:00" % divmod(total % (24 * 60), 60)


def _job(
    jid,
    name,
    state,
    elapsed,
    limit_min,
    cpu,
    *,
    mem="64G",
    rss="50000000K",
    cpus=8,
    gpus=0,
    node="midway3-0600",
    day=1,
    exit_code="0:0",
    read=None,
    write=None,
    system_cpu=None,
    pages=None,
    ntasks=None,
    ave_cpu=None,
    min_cpu=None,
):
    gres = ",gres/gpu=%d" % gpus if gpus else ""
    started = datetime.fromisoformat("2026-07-%02dT%s" % (min(day, 28), _time_of_day(jid)))
    stamp = started.isoformat()
    # Submit one second before Start, because `Reserved` below says the job waited
    # one second and a reader can subtract the two timestamps on screen. They were
    # the same string, so the job screen showed "submitted 03:54:00, started
    # 03:54:00, queued for 1.0s" -- three rows, two of which contradict the third.
    submitted = (started - timedelta(seconds=_QUEUE_WAIT_SECONDS)).isoformat()
    # End is Start plus Elapsed, which is the one thing it has to be. It was a flat
    # "23:59:00" on the job's own day, so every one of the 58 synthetic jobs carried
    # an End that its own ElapsedRaw contradicts -- job 5100019 read "started
    # 2026-07-19T03:54:00, ended 2026-07-19T23:59:00" two rows under a TIME gauge
    # saying it ran 00:30:26 of a 00:30:00 limit. Twenty hours on screen against
    # thirty minutes, in a demo whose whole claim is that nobody should be able to
    # mistake it for a measurement OR for something Slurm could not produce. It is
    # also baked into `assets/screenshot-job.svg`, which the README shows.
    ended = (started + timedelta(seconds=float(elapsed))).isoformat()
    alloc = _row(
        JobID=str(jid),
        JobName=name,
        User="youzhi",
        Account="rcc-staff",
        Cluster="midway3",
        Partition="test",
        QOS="test",
        State=state,
        ExitCode=exit_code,
        Flags="SchedBackfill" if jid % 7 == 0 else "SchedMain",
        Submit=submitted,
        Start=stamp,
        End=ended,
        ElapsedRaw=str(int(elapsed)),
        TimelimitRaw=str(limit_min),
        Reserved="00:00:%02d" % _QUEUE_WAIT_SECONDS,
        ReqMem="0n",
        ReqCPUS=str(cpus),
        AllocTRES="billing=%d,cpu=%d%s,mem=%s,node=1" % (cpus, cpus, gres, mem),
        AllocCPUS=str(cpus),
        AllocNodes="1",
        NCPUS=str(cpus),
        NNodes="1",
        NTasks=str(ntasks) if ntasks else "",
        NodeList=node,
        Priority="1137634",
        WorkDir="/home/youzhi/ArgonneAI",
        Constraints="H100" if gpus else "",
    )
    batch = _row(
        JobID="%d.batch" % jid,
        JobName="batch",
        State=state.split()[0],
        ExitCode=exit_code,
        ElapsedRaw=str(int(elapsed)),
        CPUTimeRAW=str(int(elapsed * cpus)),
        TotalCPU=cpu,
        UserCPU=cpu,
        # Blank when not given, rather than a flat "00:00:01". A fabricated one
        # second exceeded TotalCPU on the hung runs (0.5s), and SystemCPU can
        # never exceed it -- the job screen showed "KERNEL 200.0%". Not every step
        # reports SystemCPU anyway, so absent is also the more faithful default.
        SystemCPU=system_cpu or "",
        MaxRSS=rss,
        MaxRSSNode=node,
        MaxRSSTask="0",
        AveRSS=rss,
        MaxVMSize="1777525092K" if gpus else "",
        MaxPages=str(pages) if pages else "",
        NTasks=str(ntasks) if ntasks else "1",
        AveCPU=ave_cpu or "",
        MinCPU=min_cpu or "",
        MinCPUNode=node,
        MinCPUTask="3",
        TRESUsageInTot="fs/disk=%d" % read if read else "",
        TRESUsageOutTot="fs/disk=%d" % write if write else "",
    )
    extern = _row(
        JobID="%d.extern" % jid,
        JobName="extern",
        State="COMPLETED",
        ElapsedRaw=str(int(elapsed)),
        TotalCPU="00:00:00",
        MaxRSS="1956K",
    )
    return [alloc, batch, extern]


def history() -> list:
    """A synthetic history with every shape the dashboard is built to surface."""
    rows: list = []
    jid = FIRST_JOB_ID - 1  # every series below increments before it emits

    # A hung workload: same --time every run, essentially no CPU. 20 attempts,
    # 6 of which squeezed through -- and *which* six is the point.
    #
    # The hang is placed on midway3-0385: 12 placements there, all 12 hung, against
    # 8 on midway3-0602 of which 6 finished. That is the "one node that eats jobs"
    # shape demo.tape advertises and `--nodes` exists to find. It was spread evenly
    # before (`index % 3`), which gave 12/13 on one node against 6/7 on the other --
    # so with the workload held fixed, which is the only comparison `--nodes` will
    # make, the demo's own nodes screen answered "no node is worse than the rest;
    # nothing to exclude". The screen the README leads its "Failure, across runs"
    # section with did not contain the thing that section is about.
    #
    # It also makes the demo tell one story rather than two: a workload that hangs
    # AND a node that causes it, which is the inference the tool is for.
    for index in range(20):
        jid += 1
        on_bad_node = index % 5 not in (0, 4)
        # The two that hung elsewhere: without them midway3-0602 is a spotless 0/8
        # and the comparison is against a baseline no real fleet produces.
        state = "TIMEOUT" if on_bad_node or index in (0, 5) else "COMPLETED"
        cpu = "00:29:40" if state == "COMPLETED" else "00:00.5%02d" % index
        rows += _job(
            jid,
            "cot-exp",
            state,
            1826,
            30,
            cpu,
            mem="80G",
            rss="2000000K",
            cpus=6,
            gpus=1,
            node="midway3-0385" if on_bad_node else "midway3-0602",
            day=index + 1,
        )

    # Healthy training runs -- these must draw no findings.
    for index in range(14):
        jid += 1
        rows += _job(
            jid,
            "midtrain",
            "COMPLETED",
            6769,
            120,
            "05:31:39",
            mem="200G",
            rss="193517740K",
            cpus=4,
            gpus=3,
            node="midway3-0600",
            day=index + 5,
            read=112710599158,
            write=139565725797,
            system_cpu="15:35.996",
        )

    # A --mem hand-search that ends by succeeding at a value that already OOM'd.
    for mem, state in (
        ("48G", "CANCELLED by 940740146"),
        ("32G", "OUT_OF_MEMORY"),
        ("32G", "OUT_OF_MEMORY"),
        ("17G", "OUT_OF_MEMORY"),
        ("12G", "OUT_OF_MEMORY"),
        ("12G", "OUT_OF_MEMORY"),
        ("14G", "OUT_OF_MEMORY"),
        ("16G", "OUT_OF_MEMORY"),
        ("18G", "OUT_OF_MEMORY"),
        ("32G", "COMPLETED"),
    ):
        jid += 1
        rows += _job(
            jid,
            "rc-tok-github_code",
            state,
            1200,
            480,
            "00:19:00",
            mem=mem,
            rss="%dK" % (int(mem[:-1]) * 1024 * 1024 + 500000),
            cpus=16,
            node="midway3-0432",
            day=20,
            read=67022736995,
            exit_code="0:125",
        )

    # A parameter sweep -- exercises the name-pattern rollup (att-speed-#).
    for step in (11, 17, 23, 28, 34, 40, 51):
        jid += 1
        rows += _job(
            jid,
            "att-speed-%d" % step,
            "COMPLETED",
            2400,
            60,
            "05:00:00",
            mem="96G",
            rss="40000000K",
            cpus=12,
            gpus=1,
            node="midway3-0606",
            day=12,
        )

    # Kernel-heavy: mostly system time, the signal nothing else reports.
    for index in range(4):
        jid += 1
        rows += _job(
            jid,
            "tokenize-shards",
            "COMPLETED",
            3600,
            120,
            "02:00:00",
            mem="32G",
            rss="12000000K",
            cpus=16,
            node="midway3-0601",
            day=index + 2,
            system_cpu="01:20:00",
            read=340 * 1024**3,
            write=90 * 1024**3,
        )

    # A multi-task job with one lagging rank.
    jid += 1
    rows += _job(
        jid,
        "ddp-pretrain",
        "FAILED",
        5400,
        180,
        "08:00:00",
        mem="160G",
        rss="90000000K",
        cpus=32,
        gpus=4,
        ntasks=8,
        node="midway3-0372",
        day=22,
        exit_code="1:0",
        ave_cpu="01:00:00",
        min_cpu="00:12:00",
    )

    # A long allocation that held GPUs and never computed.
    jid += 1
    rows += _job(
        jid,
        "node-evaluation",
        "CANCELLED by 940740146",
        151200,
        2160,
        "00:00.540",
        mem="64G",
        rss="1956K",
        cpus=8,
        gpus=2,
        node="midway3-0385",
        day=26,
    )

    # A job that paged heavily.
    jid += 1
    rows += _job(
        jid,
        "soup-merge",
        "COMPLETED",
        4200,
        120,
        "01:05:00",
        mem="48G",
        rss="47000000K",
        cpus=8,
        node="midway3-0605",
        day=9,
        pages=820000,
    )

    return parse("\n".join(rows))
