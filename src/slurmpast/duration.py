"""Parsers for the string formats Slurm accounting actually emits.

Every function here exists because a naive parse produced a wrong number on a
real Midway3 record. The docstrings name the record.
"""

import math

# Sentinels sacct uses in place of a value. Each must yield None, never 0.0 --
# a 0.0 here silently becomes "this job used no time", which is a lie.
_NOT_A_DURATION = frozenset(
    ["", "unlimited", "invalid", "partition_limit", "unknown", "none", "n/a", "*"]
)

# The same rule reaches values that are numeric but not finite. ``float("NaN")``
# and ``float("1e999")`` are built happily by Python and are not measurements, so
# every parser here returns None for them and every formatter renders them as the
# absent value rather than raising -- see parse_duration.

_UNITS = {"k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4, "p": 1024**5}


def parse_duration(text):
    """Slurm duration -> seconds, or None if not a duration.

    Handles every shape observed in accounting output:

      ``01:52:49``     HH:MM:SS
      ``1-12:00:00``   D-HH:MM:SS       (``--time=1-12:00:00``)
      ``62-22:51:15``  DD-HH:MM:SS      (stale record, job 50108238)
      ``30:30.919``    MM:SS.mmm        (TotalCPU under an hour, job 46893309)
      ``00:00.539``    MM:SS.mmm        (TotalCPU of a hung job, job 47865145)
      ``UNLIMITED``    -> None          (partition MaxTime on all 86 partitions)

    The MM:SS.mmm form is the trap: read as HH:MM it turns 0.539 seconds of CPU
    into 30 minutes, which inverts the diagnosis of a hung job entirely.
    """
    if text is None or text == "":
        # The two absent forms, taken without building a string or lowering one.
        # This is the hottest parser in the package -- 445,815 calls parsing a
        # single seven-day history -- so the cheap exits come first. NOT
        # `if not text`: a numeric 0 is falsy and is a duration of zero, which
        # this has always returned as 0.0 and must keep returning as 0.0.
        return None
    s = text.strip() if type(text) is str else str(text).strip()
    # Every sentinel in `_NOT_A_DURATION` starts with a letter or `*`, and every
    # real duration starts with a digit, so a leading digit answers the question
    # without allocating a lowered copy of the string. Same trick, same reason,
    # as the sentinel test in `sacct.parse`.
    if not s[:1].isdigit() and s.lower() in _NOT_A_DURATION:
        return None

    days = 0
    if "-" in s:
        head, _, s = s.partition("-")
        try:
            days = int(head)
        except ValueError:
            return None

    parts = s.split(":")
    if len(parts) > 3:
        return None
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None

    if not all(map(math.isfinite, nums)):
        # "NaN" and "inf" are floats Python is happy to build and this module must
        # not return: a None is a missing measurement and everything downstream is
        # written for it, while a NaN is a number that poisons whatever it touches.
        # One record with an unparseable Elapsed turned `gpu_hours_total` and
        # `core_hours_total` for a whole history into `nan` -- destroying every
        # OTHER job's figure -- and then raised ValueError out of `format_duration`
        # on the job screen. Same rule as the sentinel table at the top of this
        # module, for the same reason: "a 0.0 here silently becomes 'this job used
        # no time', which is a lie." A NaN is the same lie, told about every job at
        # once.
        return None

    if len(parts) == 3:
        hours, minutes, seconds = nums
    elif len(parts) == 2:
        # Ambiguous by shape. Slurm writes MM:SS(.mmm) for sub-hour CPU totals
        # and HH:MM:SS otherwise, so a 2-field value is always MM:SS.
        hours, minutes, seconds = 0.0, nums[0], nums[1]
    elif len(parts) == 1:
        hours, minutes, seconds = 0.0, 0.0, nums[0]
    else:
        return None

    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def parse_bytes(text):
    """Slurm memory string -> bytes, or None.

    Handles ``53741792K`` (MaxRSS), ``40Gn`` (ReqMem per node), ``3810Mc``
    (ReqMem per CPU -- DefMemPerCPU on this cluster), ``80G``, and bare digits.

    The trailing ``n``/``c`` is a *scope* marker, not a unit: ``40Gn`` means
    40 GiB per node and ``3810Mc`` means 3810 MiB per CPU. Callers that need a
    job-level total must multiply the ``c`` form by the core count themselves;
    this function only decodes the magnitude.
    """
    if text is None or text == "":
        return None  # not `if not text`: a numeric 0 is zero bytes, not absent
    s = (text if type(text) is str else str(text)).strip().rstrip("nc")
    # As in `parse_duration`: a leading digit rules out every sentinel, and this
    # runs 624,987 times on one seven-day history.
    if not s or (not s[0].isdigit() and s.lower() in ("unknown", "none", "n/a")):
        return None
    mult = 1
    if s[-1:].lower() in _UNITS:
        mult = _UNITS[s[-1:].lower()]
        s = s[:-1]
    if not s:
        return None
    try:
        value = float(s) * mult
    except ValueError:
        return None
    # `int(float("inf"))` raises OverflowError, which is not a ValueError, so an
    # "inf" or a "1e999" in any byte field came out of here as a traceback rather
    # than as a missing reading.
    return int(value) if math.isfinite(value) else None


def parse_mem_limit(text):
    """A Slurm memory *limit* -> bytes, or None. A unit-less number is MiB.

    Same spellings as :func:`parse_bytes`, one difference: what a bare integer
    means. Slurm's memory options are documented in megabytes -- ``sbatch(1)``,
    ``--mem=<size>[units]``: *"Default units are megabytes"* -- so ``ReqMem=16``
    is 16 MiB, and reading it as 16 bytes is wrong by 1,048,576x and silent. A
    memory ceiling a millionth of its real size makes every job look catastrophically
    over its limit.

    Kept separate from :func:`parse_bytes` rather than changing it, because that
    function also decodes fields where a bare integer is *not* a memory size and
    the MiB rule would be actively wrong. ``MaxPages`` is a page count and this
    cluster emits it bare (``0``); ``MaxDiskRead``/``MaxDiskWrite`` are byte
    counters. Only a limit gets the limit convention.

    Reported as a cross-package divergence rather than against this tool: on the
    same inputs slurmate read ``16`` as 16 MB while slurmpast and slurmwatch both
    read it as 16 bytes. slurmate was right.

    Latent on both clusters checked -- Slurm 23.02 and 20.11.8 alike write an
    explicit unit into ``ReqMem`` (``4Gn``, ``3810Mc``), and a sweep of 30 days of
    Midway3 accounting found no unit-less row. Fixed anyway: the spelling that
    reaches this is a site's Slurm version and submit style, which is exactly the
    axis this tool cannot see from here.
    """
    if text is None:
        return None
    s = str(text).strip().rstrip("nc")
    if not s or s.lower() in ("unknown", "none", "n/a"):
        return None
    if s[-1:].lower() not in _UNITS:
        # Unit-less. Anchor it to MiB by appending the unit rather than
        # multiplying afterwards, so there is one conversion table, not two.
        try:
            float(s)
        except ValueError:
            return None
        s += "m"
    return parse_bytes(s)


def mem_scope(text):
    """Return ``'node'``, ``'cpu'`` or None for a ReqMem string's scope suffix."""
    if text is None:
        return None
    s = str(text).strip()
    if s.endswith("n"):
        return "node"
    if s.endswith("c"):
        return "cpu"
    return None


def format_duration(seconds):
    """Seconds -> a Slurm-shaped duration. ``None`` renders as ``n/a``.

    ``HH:MM:SS``, or ``D-HH:MM:SS`` past a day -- the notation sacct prints and
    ``--time=`` accepts. "57m54s" was this tool's own invention, so a reader had
    to translate it back into the format they actually type; the sizing advice was
    already emitting ``--time=09:45:00`` while the display said ``9h45m00s``.

    Fixed width is a second benefit: ``00:57:54`` right-aligns in a column where
    ``57m54s`` / ``2h53m27s`` / ``1d18h00m`` do not.

    Under a minute the value stays in seconds, deliberately. A hung job's evidence
    is "0.52s of CPU", and ``00:00:00`` would erase the single number this whole
    tool exists to surface. Two decimals below a second and one below a minute,
    for the same reason: the sub-second tier exists to carry "0.52s", and a
    tenth is all the resolution the tier above it needs.

    **Each tier is chosen for the value as PRINTED, not as stored.** This is the
    rule :func:`format_bytes` states in this same module -- and `_ROUNDS_UP_AT`
    exists there to enforce -- and this function did not follow it. Measured: a
    59.95s elapsed printed "60.0s" and 59.99 printed "60.0s", naming the boundary
    in the unit below it exactly as "1024.0 MiB" did before that fix, and 0.999
    printed "1.00s" out of the tier reserved for values that are not yet a
    second. Rounding is what the boundary has to be tested against, because
    rounding is what the reader is shown.
    """
    if seconds is None or not math.isfinite(float(seconds)):
        return "n/a"
    seconds = float(seconds)
    if round(seconds, 2) < 1:
        return "%.2fs" % seconds
    if round(seconds, 1) < 60:
        return "%.1fs" % seconds
    total = int(round(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return "%d-%02d:%02d:%02d" % (days, hours, minutes, secs)
    return "%02d:%02d:%02d" % (hours, minutes, secs)


#: Where ``"%.1f"`` starts reading ``1024.0`` instead of ``1023.9``, as a fraction
#: of a unit. The threshold for promoting to the next unit; see `format_bytes`.
_ROUNDS_UP_AT = 1023.95 / 1024.0


def format_bytes(value):
    """Bytes -> PiB/TiB/GiB/MiB/KiB string. ``None`` renders as ``n/a``, never ``0``.

    The KiB tier is not decoration. Without it the ladder fell from MiB straight
    to raw bytes, so a job detail printed ``read 9.5 GiB`` and ``rate 488928 B/s``
    in the same block, and a step table put ``612794 B`` beside ``79.0 MiB`` in
    one column -- the two figures a reader most wants to compare, in units that
    cannot be compared by eye.

    Bytes remain the floor below 1 KiB, where they are the honest unit and where
    ``0`` must keep rendering as ``0 B`` rather than ``0.0 KiB``.
    """
    if value is None or not math.isfinite(float(value)):
        return "n/a"
    value = float(value)
    # The unit is chosen for the value as PRINTED, not as stored. Comparing the raw
    # value against the scale picked MiB for anything below 1 GiB -- including
    # values that `%.1f` then rounds to `1024.0`, and "1024.0 MiB" means the ladder
    # failed: the whole point of taking the largest unit above 1 is to stay below
    # 1024. Measured on real records rather than argued: MaxRSS 1073692672, one of
    # 13,426 distinct byte values in a 90-day window here, printed "1024.0 MiB"
    # where it should read "1.0 GiB".
    #
    # `slurmwatch.units.format_bytes` documents the same case as its A5 and fixes
    # it by comparing the rounded figure; the ladder here descends and keeps a
    # `%d B` floor, so the equivalent is to promote as soon as the figure would
    # round up into the unit. `%.1f` flips to `1024.0` at 1023.95, so the boundary
    # is `scale * 1023.95 / 1024` -- which leaves "1000 B" and "1023 B" exactly
    # where they were, below 1 KiB, as the docstring above requires.
    # PiB is the same defect at the ceiling: with TiB as the top tier there was no
    # unit to promote INTO, so anything from ~1024 TiB up printed "1024.0 TiB",
    # "2048.0 TiB" and so on. Not a memory figure -- no job has a petabyte of RAM --
    # but `read_bytes`/`write_bytes`/`io_rate` come through here too, and the
    # largest real value in a 90-day window on this cluster is 30.9 TiB of disk
    # read, which puts 1 PiB a factor of 33 away rather than out of reach.
    for unit, scale in (
        ("PiB", 1024**5),
        ("TiB", 1024**4),
        ("GiB", 1024**3),
        ("MiB", 1024**2),
        ("KiB", 1024),
    ):
        if value >= scale * _ROUNDS_UP_AT:
            return "%.1f %s" % (value / scale, unit)
    return "%d B" % int(value)


def format_mem_flag(value):
    """Bytes -> the whole-GiB spelling ``--mem=`` accepts. ``None`` -> ``None``.

    The counterpart of :func:`format_duration`'s ``HH:MM:SS``, and closing the
    same defect: :func:`format_bytes` is a *display* formatter, so advice built on
    it emitted ``--mem=52.0 GiB`` -- which ``sbatch`` rejects outright, a flag the
    reader could read but not paste. ``sizing.memory_advice`` had the right
    spelling (``52G``) all along, so the tool's two sizing surfaces disagreed about
    the same flag.

    Rounded *up* to whole GiB, matching ``sizing._round_gib``: the value is always
    a "give it at least this much" figure, and rounding a 52.4 GiB requirement down
    to 52G would hand back a request the evidence says is too small. A sub-GiB
    result floors at ``1G`` rather than the ``0G`` Slurm reads as "no limit".
    """
    if value is None or not math.isfinite(float(value)):
        return None
    return "%dG" % max(1, int(math.ceil(float(value) / float(1024**3))))


def plural(count, word: str) -> str:
    """``word`` with an ``s`` unless ``count`` *prints* as one.

    Agreement follows the digit the reader sees rather than the float behind it:
    1.4 GPU-hours renders as "1" through ``%.0f``, so it takes the singular. Same
    rule ``bar_cells`` applies to a gauge -- "prints as" is the only definition
    under which the word and the number beside it cannot disagree.

    Here rather than in ``render`` because three of the four sites that needed it
    are in ``index`` and ``patterns``, which may not import ``render`` (it pulls in
    rich). ``duration`` is where the other formatters already live and imports
    nothing outside the stdlib.
    """
    return word if round(count or 0) == 1 else word + "s"


def format_rate_range(low, high):
    """Two rates as a percentage range: ``24.6 – 57.7%``.

    **One spelling for one interval, and this is its third home.** `render.ci_range`
    was created because `report` wrote ``"%.1f - %.1f%%"`` and `tui` wrote
    ``"%.1f – %.1f%%"``, so a hyphen and an en dash stood in the same table cell
    depending on which screen you were on. The node note then spelled it a third
    way -- ``95% CI 84.7-99.5%``, hyphenated and unspaced -- because `nodes` is an
    analysis module and may not import `render`.

    Round forty-eight recorded that and left it, reading the options as "duplicate
    the format, re-creating exactly the drift `ci_range` prevents" or "move the
    sentence out, a four-file change". There is a third: put the rule where both
    can reach it. `duration` imports nothing but ``math``, `render` already imports
    from it, and `nodes` may -- so the format lives here and both call it.

    An en dash is what a numeric range takes, and ``render.ascii_fold`` maps it to
    a hyphen, so ``--ascii`` and piped output are byte-identical to what they were.
    `report._fold` applies that once per view over the finished text, which is how
    the note gets folded too.

    **Each end goes through :func:`format_percent`**, so the interval is spelled
    the way every other percentage in this tool is. Its own ``%.1f`` flipped an
    interior value to a boundary it had not reached -- the defect `format_percent`
    was fixed for, one helper over: ``format_rate_range(0.9996, 1.0)`` read
    ``100.0 – 100.0%``, presenting [99.96%, 100%] as a degenerate interval, and a
    range whose two ends print identically says the measurement was exact when it
    was not. Round fifty-six recorded this and left it open, reading the choice as
    ``>99.9 – 100.0%`` against widening the precision; the first is what this
    package already decided for a single value at the same boundary, and reusing
    it invents no precision and adds no third spelling.

    The exact ends are untouched -- 0.0 is ``0.0%`` and 1.0 is ``100.0%``, both
    true -- so every pinned string (``75.7 – 100.0%``, ``95% CI 72.2 – 100.0%``)
    is byte-identical. Only the strictly interior band moves, which is the band
    `format_percent` already governs.
    """
    return "%s – %s" % (format_percent(low).rstrip("%"), format_percent(high))


def format_percent(value):
    """Fraction -> percent string. ``None`` renders as ``n/a``, never ``0%``.

    Inherited from slurmwatch's number audit (finding A2): printing ``0%`` for a
    failed read is indistinguishable from a real measurement of zero.

    **The figure is chosen for the value as PRINTED, not as stored** -- the rule
    :func:`format_bytes` states in this module and ``_ROUNDS_UP_AT`` exists there
    to enforce, and the one :func:`format_duration` was fixed for. ``%.1f`` flips
    to ``100.0`` at 99.95 and to ``0.0`` anywhere below 0.05, so an interior value
    was printed as a boundary it had not reached -- the same defect as
    ``1024.0 MiB`` and ``60.0s``, and here the boundary is a *claim*:

    * ``report`` and ``tui`` print ``format_percent(completion_rate)`` followed by
      the word "completed". From **2000 jobs with a single failure** the rate is
      0.9995 and the line read "100.0% completed"; at the 13,051 parent jobs a
      30-day window holds on this cluster, one failure gives 0.999923 and the
      same "100.0% completed". A reader is told nothing failed by the tool whose
      job is to say what did.
    * The other end is the docstring's own case one step in. One failure in
      13,051 is 0.0077%, which printed ``0.0%`` -- so that string meant both
      "none" and "some, but under a tenth", which is exactly the ambiguity the
      ``n/a`` rule above exists to refuse for a failed read.
    * ``walltime_used`` at 99.96% of the limit printed "100.0%" for a job that
      did NOT hit the wall, and distinguishing those two is what a TIMEOUT
      diagnosis turns on.

    So an interior value is given a BOUND rather than a wrong figure. That is the
    spelling the sibling tools already use for "nonzero but below the resolution"
    -- ``rapidu.fmt`` returns ``<0.01x`` and ``nodetop.core.duration`` returns
    ``<1m`` -- and it invents no precision, which printing ``0.1%`` for 0.0077%
    would (13x).

    **The exact boundaries still print as boundaries**: 0.0 is ``0.0%`` and 1.0 is
    ``100.0%``, because those are true and two tests pin them. Only the strictly
    interior band moves. Values above 1.0 are untouched -- MEM% legitimately reads
    ``102.6%`` when a job exceeded its request -- and so is anything negative.
    """
    if value is None or not math.isfinite(float(value)):
        return "n/a"
    figure = 100.0 * float(value)
    if 0.0 < figure < 0.05:
        return "<0.1%"
    if 99.95 <= figure < 100.0:
        return ">99.9%"
    return "%.1f%%" % figure


# Plausible sustained CPU clock range. Below the floor a value is not a clock
# this hardware could have run at; above the ceiling it is a unit error.
_FREQ_FLOOR_HZ = 400e6
_FREQ_CEILING_HZ = 6e9
_FREQ_SUFFIX = {"k": 1e3, "m": 1e6, "g": 1e9, "t": 1e12}


def parse_cpu_freq(text):
    """``AveCPUFreq`` -> hertz, or None when the value cannot be trusted.

    This field is not reliably interpretable as printed. On one cluster the same
    3.1 GHz part reports ``3.10M`` on 935 records and ``3.10G`` on 342 -- Slurm's
    magnitude suffix is applied to a kHz base in some code paths and a Hz base in
    others, so the string alone is ambiguous by a factor of 1000.

    Rather than print an uninterpretable number, both readings are tried and the
    one that lands in a plausible clock range wins. Values that fit neither (a
    reported ``14K``, i.e. 14 MHz or 14 kHz) return None and are omitted from the
    display entirely -- an absent figure is honest, a wrong one is not.

    A genuine low reading survives and is informative: ``800K`` resolves to
    800 MHz, which is a core that spent its time downclocked.
    """
    if text is None:
        return None
    raw = str(text).strip()
    if not raw or raw in ("0", "Unknown", "None", "N/A"):
        return None

    multiplier = 1.0
    if raw[-1:].lower() in _FREQ_SUFFIX:
        multiplier = _FREQ_SUFFIX[raw[-1:].lower()]
        raw = raw[:-1]
    try:
        value = float(raw) * multiplier
    except ValueError:
        return None

    # Candidate interpretations: the number is already hertz, or it is kilohertz.
    for hz in (value, value * 1e3):
        if _FREQ_FLOOR_HZ <= hz <= _FREQ_CEILING_HZ:
            return hz
    return None


def format_cpu_freq(hz):
    """Hertz -> ``3.10 GHz`` / ``800 MHz``. ``None`` renders as ``n/a``."""
    if hz is None or not math.isfinite(float(hz)):
        return "n/a"
    if hz >= 1e9:
        return "%.2f GHz" % (hz / 1e9)
    return "%.0f MHz" % (hz / 1e6)


_WINDOW_UNITS = {
    "second": "seconds",
    "minute": "minutes",
    "hour": "hours",
    "day": "days",
    "week": "weeks",
    "month": "months",
}


def humanize_window(since, until=None):
    """A sacct time spec, in English.

    "now-7days → now" is the machine's phrasing showing through; a reader should
    not have to parse the tool's own arguments back out of its title bar.

        now-7days           -> last 7 days
        now-1day            -> last 24 hours
        2026-01-01          -> since 2026-01-01
        now-30days, 07-15   -> 30 days ago to 07-15
    """
    import re

    since = (since or "").strip()
    until = (until or "").strip()
    ended = until and until.lower() != "now"

    match = re.match(r"^now-\s*(\d+)\s*([a-z]+?)s?$", since, re.IGNORECASE)
    if match:
        count, unit = int(match.group(1)), match.group(2).lower()
        plural = _WINDOW_UNITS.get(unit, unit + "s")
        if ended:
            # "last N days" would claim the range reaches now, and an explicit
            # -E says it does not. Without this branch the raw "now-30days" fell
            # through to the display -- the machine's own argument syntax, which
            # is the one thing this function exists to keep off the screen.
            if unit == "day" and count == 1:
                span = "24 hours"
            else:
                span = "1 %s" % unit if count == 1 else "%d %s" % (count, plural)
            return "%s ago to %s" % (span, until.split("T")[0])
        if unit == "day" and count == 1:
            return "last 24 hours"
        if count == 1:
            return "last %s" % unit
        return "last %d %s" % (count, plural)

    if not since:
        return "all time" if not ended else "up to %s" % until

    # Slurm accepts these bare keywords; "since today" reads worse than "today".
    keyword = {
        "today": "today",
        "yesterday": "since yesterday",
        "midnight": "since midnight",
        "noon": "since noon",
        "now": "just now",
    }.get(since.lower())
    if keyword and not ended:
        return keyword

    label = since.split("T")[0]
    if ended:
        return "%s to %s" % (label, until.split("T")[0])
    return "since %s" % label
