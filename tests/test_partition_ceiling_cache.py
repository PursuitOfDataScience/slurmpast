"""A failed `sinfo` was memoised as a measured ceiling.

`partition_ceiling` exists to keep `--sizing` honest, and its docstring says why:

    `--sizing` read a saturated workload correctly -- "the busiest run used 27.9
    of 28 cores per task" -- and advised `--cpus-per-task=34` on a partition
    whose nodes have 28, which `sbatch` refuses outright with *"Requested node
    configuration is not available"*. The reading was right; nothing checked it
    against the hardware.

It is also explicit that a failure returns `(None, None)`: "Never raises and
never guesses. No `sinfo`, an unknown partition, or output that will not parse
all give `(None, None)`". That part was right. What it did **not** say is that
the failure was then written into `_PARTITION_CEILING`, and the cache is checked
before the query. Measured:

    first call, `sinfo` raises      -> (None, None), cached
    second call, `sinfo` WORKS and
      returns `128 256000`          -> (None, None), and sinfo is never run again

So one transient failure -- no `sinfo` on PATH yet, a timeout, an EINTR --
permanently disabled the clamp for the rest of the process, reintroducing exactly
the defect the function was written to prevent.

The fix withholds only the memo: the return contract is untouched (still
`(None, None)`, still never raises), and output that ANSWERED but would not parse
still caches, because that is a measurement about the partition. The distinction
is the query, not the verdict -- which is the same line this package draws
everywhere else between a zero and an absence.
"""

from __future__ import annotations

from typing import Any

import pytest

from slurmpast import site
from slurmpast.sacct import SacctError

#: A two-node heterogeneous partition, which is the shape `-N` exists to expose.
GOOD_OUTPUT = "128 256000\n64 128000\n"


class _Runner:
    """A stand-in `sinfo` that counts how often it was actually consulted."""

    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, argv: list[str]) -> str:
        self.calls += 1
        outcome = self.outcomes[min(self.calls - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return str(outcome)


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    site._PARTITION_CEILING.clear()
    yield
    site._PARTITION_CEILING.clear()


class TestAFailedQueryIsNotRemembered:
    def test_a_failure_is_not_written_into_the_cache(self) -> None:
        run = _Runner(SacctError("sinfo is not on PATH"))
        assert site.partition_ceiling("amd", runner=run) == (None, None)
        assert "amd" not in site._PARTITION_CEILING, dict(site._PARTITION_CEILING)

    def test_the_next_caller_gets_another_look(self) -> None:
        """The defect, end to end: a working `sinfo` after a failing one."""
        run = _Runner(SacctError("transient"), GOOD_OUTPUT)
        assert site.partition_ceiling("amd", runner=run) == (None, None)
        assert site.partition_ceiling("amd", runner=run) == (128, 256000)
        assert run.calls == 2, "the second call never re-ran sinfo"

    @pytest.mark.parametrize("exc", [SacctError("boom"), OSError("EINTR")])
    def test_both_failure_kinds_are_treated_the_same(self, exc: BaseException) -> None:
        run = _Runner(exc, GOOD_OUTPUT)
        assert site.partition_ceiling("p", runner=run) == (None, None)
        assert site.partition_ceiling("p", runner=run) == (128, 256000)

    def test_the_clamp_comes_back_rather_than_staying_off(self) -> None:
        # Stated as the consequence rather than the mechanism: the ceiling is
        # what a recommendation is checked against, and it must not be lost for
        # the life of the process because one query blinked.
        run = _Runner(OSError("blink"), GOOD_OUTPUT)
        site.partition_ceiling("amd", runner=run)
        cores, _mb = site.partition_ceiling("amd", runner=run)
        assert cores == 128, "no ceiling to clamp against after a transient failure"


class TestControls:
    """Behaviour that must not change. Each passes in BOTH states."""

    def test_a_successful_query_is_still_memoised(self) -> None:
        run = _Runner(GOOD_OUTPUT)
        assert site.partition_ceiling("amd", runner=run) == (128, 256000)
        assert site.partition_ceiling("amd", runner=run) == (128, 256000)
        assert run.calls == 1, "a cached ceiling was re-queried"

    def test_output_that_answered_but_would_not_parse_is_still_memoised(self) -> None:
        # The boundary the fix draws: the query ANSWERED, so `(None, None)` is a
        # measurement about this partition and caching it is right.
        run = _Runner("not numbers at all\n")
        assert site.partition_ceiling("x", runner=run) == (None, None)
        assert site.partition_ceiling("x", runner=run) == (None, None)
        assert run.calls == 1, "an answered query was re-run"
        assert site._PARTITION_CEILING["x"] == (None, None)

    def test_an_empty_but_successful_answer_is_still_memoised(self) -> None:
        run = _Runner("")
        assert site.partition_ceiling("empty", runner=run) == (None, None)
        assert site.partition_ceiling("empty", runner=run) == (None, None)
        assert run.calls == 1

    def test_a_failure_still_returns_the_documented_pair_and_never_raises(self) -> None:
        run = _Runner(SacctError("no sinfo"))
        assert site.partition_ceiling("amd", runner=run) == (None, None)

    def test_no_partition_is_still_answered_without_a_query(self) -> None:
        run = _Runner(GOOD_OUTPUT)
        assert site.partition_ceiling("", runner=run) == (None, None)
        assert run.calls == 0

    def test_the_maximum_across_nodes_is_still_what_is_reported(self) -> None:
        # `-N` per node, and the answer is the max -- the reason the flag is there.
        run = _Runner("28 64000\n128 256000\n64 128000\n")
        assert site.partition_ceiling("het", runner=run) == (128, 256000)

    def test_a_trailing_plus_is_still_read_as_its_digits(self) -> None:
        run = _Runner("32+ 64000+\n")
        assert site.partition_ceiling("plus", runner=run) == (32, 64000)
