"""Parsers for the string formats Slurm accounting actually emits.

Every function here exists because a naive parse produced a wrong number on a
real Midway3 record. The docstrings name the record.
"""

# Sentinels sacct uses in place of a value. Each must yield None, never 0.0 --
# a 0.0 here silently becomes "this job used no time", which is a lie.
_NOT_A_DURATION = frozenset(
    ["", "unlimited", "invalid", "partition_limit", "unknown", "none", "n/a", "*"]
)

_UNITS = {"k": 1024, "m": 1024 ** 2, "g": 1024 ** 3, "t": 1024 ** 4, "p": 1024 ** 5}


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
    """Seconds -> compact human duration. ``None`` renders as ``n/a``."""
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
        return "%dd%02dh%02dm" % (days, hours, minutes)
    if hours:
        return "%dh%02dm%02ds" % (hours, minutes, secs)
    return "%dm%02ds" % (minutes, secs)


def format_bytes(value):
    """Bytes -> GiB/MiB string. ``None`` renders as ``n/a``, never ``0``."""
    if value is None:
        return "n/a"
    value = float(value)
    for unit, scale in (("TiB", 1024 ** 4), ("GiB", 1024 ** 3), ("MiB", 1024 ** 2)):
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
