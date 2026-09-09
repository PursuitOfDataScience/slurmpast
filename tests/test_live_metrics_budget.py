"""The live `sstat` enrichment waited on the accounting database's budget.

`merge_live_metrics` is built around a cost it names outright -- "the 18-second
call this exists to avoid" -- and `read_live_metrics` already batches into one
`sstat` rather than one per job. What neither did was bound the wait. Measured on
midway3 with **60 running array tasks**:

    sstat --allsteps --parsable2 --jobs=<60 ids> --format=...
      -> 119.76s, 2,160 rows

`sstat` contacts each job's `slurmstepd`, so its cost scales with how many jobs
the reader has RUNNING, not with the window. The only bound was
`DEFAULT_TIMEOUT = 300.0`, which is the *accounting database's* budget, so
`slurmpast --plain` sat for two minutes before printing anything.

`read_live_metrics` already documents the right answer: "the caller's fallback is
to report the field as unmeasured, which is the correct answer and not a
degradation." So the query gets `LIVE_METRICS_TIMEOUT_S` and lands there.

Three boundaries are pinned below because each is a decision, not an accident:

* `SLURMPAST_TIMEOUT` stays "the package's only environment variable" -- no new
  one. It is honoured as a **ceiling**: lowering it lowers this too, raising it
  does not extend an enrichment;
* `_timeout()` is still read *before* any spawn, so a bad setting is refused
  rather than reached past -- which is what `_run`'s own comment requires;
* the budget reaches `_run` **directly, not through `runner`**. All 48 injected
  runners in this package are one-argument callables and a test double has no
  wait to bound, so the protocol is untouched. `TestControls` proves a
  one-argument runner still works.

What this does NOT fix: the end-to-end `--plain` run is still ~171s, because the
bulk is the window's own parse and the tool already says so on its first screen
("37,784 rows parsed, about 36.9 MiB held ... narrow it with -S").
"""

from __future__ import annotations

import os
import time
from typing import Any
from unittest import mock

import pytest

from slurmpast import sacct


class TestTheLiveQueryHasItsOwnBudget:
    def test_the_budget_is_shorter_than_the_accounting_one(self) -> None:
        # The whole point: `sstat`'s cost has a different shape, so it cannot
        # inherit the database's patience.
        assert sacct.LIVE_METRICS_TIMEOUT_S < sacct.DEFAULT_TIMEOUT
        # And short enough to beat the number the module says it avoids.
        assert sacct.LIVE_METRICS_TIMEOUT_S <= 18.0

    def test_the_cap_is_in_force_while_the_query_runs(self) -> None:
        """Observed from inside the call, which is where it applies."""
        seen: dict[str, Any] = {}

        def fake_run(argv: list[str]) -> str:
            seen["argv"] = argv
            seen["cap"] = sacct._query_cap.value
            return ""

        with mock.patch.object(sacct, "_run", fake_run):
            sacct.read_live_metrics(["100", "101"])
        assert seen["argv"][0] == "sstat"
        assert seen["cap"] == sacct.LIVE_METRICS_TIMEOUT_S

    def test_the_cap_is_cleared_afterwards(self) -> None:
        # It must not leak into the next query on this thread, which is the
        # full-budget accounting read.
        with mock.patch.object(sacct, "_run", lambda argv: ""):
            sacct.read_live_metrics(["100"])
        assert getattr(sacct._query_cap, "value", None) is None

    def test_the_cap_really_shortens_a_real_wait(self) -> None:
        """Against a real slow child, not a mock -- the point is the wall clock."""
        started = time.time()
        sacct._query_cap.value = 1.0
        try:
            with pytest.raises(sacct.SacctError):
                sacct._run(["sleep", "30"])
        finally:
            sacct._query_cap.value = None
        elapsed = time.time() - started
        assert elapsed < 10.0, f"the cap was not enforced ({elapsed:.1f}s)"

    def test_a_timed_out_live_query_reads_as_unmeasured(self) -> None:
        # The documented fallback, reached by a timeout rather than by an error.
        def slow(argv: list[str]) -> str:
            raise sacct.SacctError("sstat did not answer within 15s")

        with mock.patch.object(sacct, "_run", slow):
            assert sacct.read_live_metrics(["100"]) == {}


class TestControls:
    """Behaviour that must not change. Each passes in BOTH states."""

    def test_a_lower_environment_budget_still_wins(self) -> None:
        """Passes in BOTH states -- verified by neutering, so it is a control.

        A lowered `SLURMPAST_TIMEOUT` bounded this call before the change too,
        because it was the *only* bound. What the change adds is a bound when the
        variable is unset or raised. Kept because the ceiling is the reason no new
        environment variable was introduced, and losing it would silently let an
        enrichment outlive a budget the reader deliberately shortened.
        """
        started = time.time()
        sacct._query_cap.value = sacct.LIVE_METRICS_TIMEOUT_S
        try:
            with (
                mock.patch.dict(os.environ, {"SLURMPAST_TIMEOUT": "1"}),
                pytest.raises(sacct.SacctError),
            ):
                sacct._run(["sleep", "30"])
        finally:
            sacct._query_cap.value = None
        assert time.time() - started < 10.0

    def test_a_bad_environment_setting_is_still_refused_before_the_spawn(self) -> None:
        # Pre-existing, and the reason `_timeout()` is still read first: `_run`'s
        # own comment requires the setting be refused BEFORE a child is started,
        # or the refusal leaves an orphaned query behind.
        with (
            mock.patch.dict(os.environ, {"SLURMPAST_TIMEOUT": "garbage"}),
            pytest.raises(sacct.SacctError),
        ):
            sacct._run(["true"])

    def test_a_one_argument_injected_runner_still_works(self) -> None:
        # The protocol every other test in this package relies on.
        calls: list[list[str]] = []

        def one_arg(argv: list[str]) -> str:
            calls.append(argv)
            return ""

        assert sacct.read_live_metrics(["100"], runner=one_arg) == {}
        assert len(calls) == 1
        assert calls[0][0] == "sstat"

    def test_the_query_is_still_one_call_for_every_job(self) -> None:
        # The module's stated design: "-j takes a comma-separated list".
        calls: list[list[str]] = []

        def one_arg(argv: list[str]) -> str:
            calls.append(argv)
            return ""

        sacct.read_live_metrics(["1", "2", "3", "4"], runner=one_arg)
        assert len(calls) == 1, "one call per job again"
        jobs = [a for a in calls[0] if a.startswith("--jobs=")]
        assert jobs == ["--jobs=1,2,3,4"], jobs

    def test_a_step_suffix_is_still_stripped_and_duplicates_collapsed(self) -> None:
        calls: list[list[str]] = []

        def one_arg(argv: list[str]) -> str:
            calls.append(argv)
            return ""

        sacct.read_live_metrics(["7.batch", "7", "8.0"], runner=one_arg)
        assert [a for a in calls[0] if a.startswith("--jobs=")] == ["--jobs=7,8"]

    def test_no_job_ids_still_asks_nothing(self) -> None:
        calls: list[list[str]] = []

        def one_arg(argv: list[str]) -> str:
            calls.append(argv)
            return ""

        assert sacct.read_live_metrics([], runner=one_arg) == {}
        assert calls == []

    def test_a_failing_query_still_reads_as_unmeasured(self) -> None:
        def boom(argv: list[str]) -> str:
            raise sacct.SacctError("Invalid user id")

        assert sacct.read_live_metrics(["100"], runner=boom) == {}

    def test_an_ordinary_query_still_uses_the_full_accounting_budget(self) -> None:
        # The history query must NOT inherit the enrichment's cap.
        assert getattr(sacct._query_cap, "value", None) is None
        sacct._run(["true"])  # a real, instant child: no cap, no raise

    def test_the_default_timeout_is_unchanged(self) -> None:
        assert sacct.DEFAULT_TIMEOUT == 300.0
        assert sacct._timeout() == 300.0
