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

from .sacct import parse

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
    stamp = "2026-07-%02dT0%d:00:00" % (min(day, 28), jid % 9)
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
        Submit=stamp,
        Start=stamp,
        End="2026-07-%02dT23:59:00" % min(day, 28),
        ElapsedRaw=str(int(elapsed)),
        TimelimitRaw=str(limit_min),
        Reserved="00:00:01",
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
        SystemCPU=system_cpu or "00:00:01",
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
    jid = 5100000

    # A hung workload: same --time every run, essentially no CPU. 20 attempts,
    # 2 of which happened to squeeze through.
    for index in range(20):
        jid += 1
        state = "COMPLETED" if index in (7, 15) else "TIMEOUT"
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
            node="midway3-0385" if index % 3 else "midway3-0602",
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
