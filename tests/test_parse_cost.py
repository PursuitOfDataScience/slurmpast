"""The parser's hot path, and the equivalences the speedups rest on.

A 30-day window on one user is 43,643 rows and 31.5 MB of `sacct` output.  Where
that time went, measured:

    subprocess   7.41 s   (sacct itself; 71%)
    parse        2.66 s   (Python)
    index/group  0.34 s

`get` -- one call per field per row, **1,975,028 of them** -- lowercased its
`name` argument every time and then handed the same string to `_clean`, which
lowercased it again to test `_FREE_TEXT`.  The names are a fixed set of 85
compile-time constants, so that was recomputing a constant 7,095,157 times.
Resolving each name once per parse took 2.71 s -> 2.18 s; a regex for
`_looks_like_job_id` and a digit pre-filter on the sentinel test took it to
2.10 s.  **22% off the Python half**, and nothing about the output changes.

The two equivalences below are the ones worth pinning rather than the timings.
`_looks_like_job_id` in particular is the guard that stops SP-1 -- `sacct` fields
legitimately contain newlines, and a shell fragment reaching the record-opening
test is how 41 real records became 56.
"""

from __future__ import annotations

import sys

import pytest

from slurmpast import sacct as sacctmod
from slurmpast.sacct import _UNSET, _WHITESPACE_RE, _looks_like_job_id, parse


class TestTheWhitespaceRegexIsTheOldPredicate:
    """`re.search(r"\\s", v)` replaced `any(ch.isspace() for ch in v)`.

    They have to agree on every character, not merely on ASCII: `sacct` carries
    job names and work directories, and a site's data is not the author's to
    guess at.
    """

    def test_they_agree_on_every_code_point(self):
        disagree = [
            hex(c)
            for c in range(sys.maxunicode + 1)
            if bool(chr(c).isspace()) != bool(_WHITESPACE_RE.search(chr(c)))
        ]
        assert not disagree, f"{len(disagree)} code points differ, e.g. {disagree[:10]}"

    @pytest.mark.parametrize(
        "value,accepted",
        [
            # Every JobID spelling Slurm emits.
            ("123", True),
            ("123_4", True),
            ("123_[1-20%10]", True),
            ("123+0", True),
            ("123.batch", True),
            ("123.extern", True),
            ("12345678.0", True),
            # The shell fragments that used to reach this point. This is SP-1:
            # `sacct`'s SubmitLine contains real newlines, so a continuation
            # line can look like the start of a record.
            ('echo "--- m ---"', False),
            ("2>&1 | tail -1", False),
            ("123 456", False),
            ("123\tx", False),
            ("123\nx", False),
            ("123\x0bx", False),
            ("123\xa0x", False),
            ("", False),
            ("abc", False),
        ],
    )
    def test_the_loose_contract_is_unchanged(self, value, accepted):
        assert _looks_like_job_id(value) is accepted


class TestTheSentinelPreFilterIsSound:
    """A value starting with a digit is tested without lowering the string.

    Sound only while no member of `_UNSET` starts with a digit -- so that is
    asserted rather than assumed, because adding one would silently stop the
    sentinel being blanked.
    """

    def test_no_sentinel_starts_with_a_digit(self):
        offenders = [w for w in _UNSET if w and w[0].isdigit()]
        assert not offenders, (
            f"{offenders} would slip past the digit pre-filter in `get`; drop the "
            f"pre-filter or spell the sentinel differently"
        )

    @pytest.mark.parametrize("sentinel", sorted(w for w in _UNSET if w))
    def test_every_sentinel_is_still_blanked(self, sentinel):
        # Through the real parser, in a field that is not free text.
        head = "JobID|State|NodeList"
        rows = f"{head}\n1|COMPLETED|{sentinel}\n"
        jobs = parse(rows, fields=["JobID", "State", "NodeList"], delimiter="|")
        assert jobs[0].node_list == "", sentinel

    @pytest.mark.parametrize("sentinel", sorted(w for w in _UNSET if w))
    def test_a_free_text_field_keeps_it(self, sentinel):
        # The control, and the reason `_FREE_TEXT` exists: a job really can be
        # named `None`, which is what an f-string over an unset variable makes.
        head = "JobID|State|JobName"
        rows = f"{head}\n1|COMPLETED|{sentinel}\n"
        jobs = parse(rows, fields=["JobID", "State", "JobName"], delimiter="|")
        assert jobs[0].name == sentinel

    def test_a_numeric_field_is_unaffected(self):
        head = "JobID|State|Priority|ElapsedRaw"
        rows = f"{head}\n1|COMPLETED|4294901759|600\n"
        jobs = parse(rows, fields=["JobID", "State", "Priority", "ElapsedRaw"], delimiter="|")
        assert jobs[0].priority == 4294901759
        assert jobs[0].elapsed == 600


class TestTheFieldPlanIsPerParseNotPerAccess:
    def test_a_field_absent_from_a_short_format_still_reads_empty(self):
        """The contract `index.get(...) -> None` carried before.

        Callers pass literal field names that a narrow `--format` may not
        contain, so the plan has to be filled lazily rather than from `fields`.
        """
        head = "JobID|State"
        jobs = parse(f"{head}\n1|COMPLETED\n", fields=["JobID", "State"], delimiter="|")
        assert jobs[0].partition == ""
        assert jobs[0].work_dir == ""
        assert jobs[0].req_mem_raw == ""

    def test_two_parses_do_not_share_a_plan_or_a_string_table(self):
        # Both are scoped to one parse. The string table especially: a global
        # one would accumulate every job id and timestamp the process ever saw.
        head = "JobID|State|Account"
        first = parse(
            f"{head}\n1|COMPLETED|rcc-staff\n", fields=["JobID", "State", "Account"], delimiter="|"
        )
        second = parse(
            f"{head}\n2|COMPLETED|rcc-staff\n", fields=["JobID", "State", "Account"], delimiter="|"
        )
        assert first[0].account == second[0].account == "rcc-staff"
        assert id(first[0].account) != id(second[0].account)

    def test_repeated_values_within_one_parse_are_one_object(self):
        head = "JobID|State|Account"
        rows = "\n".join(f"{i}|COMPLETED|rcc-staff" for i in range(1, 51))
        jobs = parse(f"{head}\n{rows}\n", fields=["JobID", "State", "Account"], delimiter="|")
        assert len({id(j.account) for j in jobs}) == 1

    def test_the_hot_helper_no_longer_scales_with_the_field_count(self):
        """`_clean` is inlined into `get`, not reimplemented.

        It is still the shared implementation for `_int`, `_seconds` and the
        `sstat` parser, and those run once per ROW for a fixed set of numeric
        fields -- so the count is not zero. What must be gone is the *per field
        read* call: 2,263,954 of them over a 30-day window.

        Asserted as an invariance rather than a threshold, because a threshold
        would need recalibrating every time a numeric field is added, and would
        pass for the wrong reason if `get` started calling `_clean` again on a
        narrow format.
        """

        def clean_calls(fields):
            calls = []
            real = sacctmod._clean

            def counting(*a, **k):
                calls.append(a)
                return real(*a, **k)

            sacctmod._clean = counting
            try:
                head = "|".join(fields)
                rows = "\n".join(
                    "|".join(_sample_value(f, i) for f in fields) for i in range(1, 21)
                )
                jobs = parse(f"{head}\n{rows}\n", fields=list(fields), delimiter="|")
            finally:
                sacctmod._clean = real
            assert len(jobs) == 20, fields
            return len(calls)

        narrow = ("JobID", "State", "Partition")
        wide = narrow + (
            "Account",
            "User",
            "Group",
            "QOS",
            "Cluster",
            "JobName",
            "WCKey",
            "Reservation",
            "WorkDir",
            "Comment",
            "NodeList",
            "Flags",
            "Reason",
        )
        assert clean_calls(narrow) == clean_calls(wide), (
            "the number of `_clean` calls changed with the field count, so "
            "something in the row loop is calling it per field read again"
        )


def _sample_value(field, index):
    """A plausible value for one sacct field, for the invariance test above."""
    if field == "JobID":
        return str(1000 + index)
    if field == "State":
        return "COMPLETED"
    return {
        "Partition": "caslake",
        "Account": "rcc-staff",
        "User": "youzhi",
        "Group": "youzhi",
        "QOS": "normal",
        "Cluster": "midway3",
        "JobName": "train",
        "WCKey": "",
        "Reservation": "",
        "WorkDir": "/home/youzhi",
        "Comment": "",
        "NodeList": "midway3-0200",
        "Flags": "SchedBackfill",
        "Reason": "None",
    }.get(field, "")
