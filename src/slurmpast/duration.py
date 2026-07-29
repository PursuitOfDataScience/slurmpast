"""Parsers for the string formats Slurm accounting actually emits.

Every function here exists because a naive parse produced a wrong number on a
real Midway3 record. The docstrings name the record.
"""

# Sentinels sacct uses in place of a value. Each must yield None, never 0.0 --
# a 0.0 here silently becomes "this job used no time", which is a lie.
_NOT_A_DURATION = frozenset(
    ["", "unlimited", "invalid", "partition_limit", "unknown", "none", "n/a", "*"]
)

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
    if text is None:
        return None
    s = str(text).strip()
    if s.lower() in _NOT_A_DURATION:
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
    if text is None:
        return None
    s = str(text).strip().rstrip("nc")
    if not s or s.lower() in ("unknown", "none", "n/a", ""):
        return None
    mult = 1
    if s[-1:].lower() in _UNITS:
        mult = _UNITS[s[-1:].lower()]
        s = s[:-1]
    if not s:
        return None
    try:
        return int(float(s) * mult)
    except ValueError:
        return None


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
    tool exists to surface.
    """
    if seconds is None:
        return "n/a"
    seconds = float(seconds)
    if seconds < 1:
        return "%.2fs" % seconds
    if seconds < 60:
        return "%.1fs" % seconds
    total = int(round(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return "%d-%02d:%02d:%02d" % (days, hours, minutes, secs)
    return "%02d:%02d:%02d" % (hours, minutes, secs)


def format_bytes(value):
    """Bytes -> GiB/MiB string. ``None`` renders as ``n/a``, never ``0``."""
    if value is None:
        return "n/a"
    value = float(value)
    for unit, scale in (("TiB", 1024**4), ("GiB", 1024**3), ("MiB", 1024**2)):
        if value >= scale:
            return "%.1f %s" % (value / scale, unit)
    return "%d B" % int(value)


def format_percent(value):
    """Fraction -> percent string. ``None`` renders as ``n/a``, never ``0%``.

    Inherited from slurmwatch's number audit (finding A2): printing ``0%`` for a
    failed read is indistinguishable from a real measurement of zero.
    """
    if value is None:
        return "n/a"
    return "%.1f%%" % (100.0 * value)


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
    if hz is None:
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
