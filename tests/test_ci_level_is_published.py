"""The node table publishes the two thresholds its rendered form states.

`--nodes` prints a `95% CI` column header and a verdict paragraph that says the
correction is "after correcting for N nodes tested". The payload carried
`ci_low`, `ci_high`, `p_value` and `verdict` and neither threshold, so a
consumer of `--nodes --json`:

* held two interval bounds with no way to learn what level they are an interval
  OF -- a 95% and a 99% interval are different claims about the same two
  numbers; and
* held a p-value beside a verdict with no way to learn which threshold produced
  it, so it could neither re-derive the verdicts under its own alpha nor see
  how close a `same` row came to tripping.

Found by the rendered-vs-`--json` sweep, run across all four text views. After
crediting rounded renderings of stored floats -- `105` is how `105.2955` prints
-- exactly one rendered integer in the four views was unreachable from its own
payload, and it was this column header's `95`.

`CONFIDENCE_LEVEL` is derived from `Z` rather than written down again, so the
payload cannot disagree with the arithmetic that produced the interval. The
label text is a separate matter and is checked here against the derived value
rather than assumed to match it.
"""

import math

import pytest

from slurmpast.nodes import (
    CONFIDENCE_LEVEL,
    FDR_ALPHA,
    Z,
    _bh_reject,
    node_table,
    wilson_interval,
)
from slurmpast.render import NODE_COLUMNS

from .test_nodes import _placements


@pytest.fixture
def table():
    """One clearly-worse node against a healthy one -- test_nodes' own shape."""
    jobs = _placements("midway3-0385", 19, 36) + _placements(
        "midway3-0600", 12, 218, job_id_base=5000
    )
    return node_table(jobs, workload="node-evaluation")


class TestTheThresholdsReachTheReader:
    def test_the_confidence_level_is_published(self, table):
        assert table["confidence_level"] == 0.95

    def test_the_false_discovery_rate_is_published(self, table):
        assert table["fdr_alpha"] == FDR_ALPHA

    def test_the_published_alpha_is_the_one_actually_applied(self, table):
        """`_bh_reject`'s default is what decides a verdict, so that is the
        number a consumer needs -- not a second constant that agrees today."""
        import inspect

        default = inspect.signature(_bh_reject).parameters["alpha"].default
        assert table["fdr_alpha"] == default

    def test_the_level_is_derived_from_z_not_written_down(self):
        """Change `Z` and the published level follows. A hand-written 0.95 would
        keep saying 95% while the interval stopped being one.

        A GUARD on the derivation, not a control and not a publication test:
        it reads the constant rather than the payload, so it stays green under
        the neuter that removes both keys. Without it every assertion above
        would hold against a hardcoded 0.95.
        """
        assert math.erf(Z / math.sqrt(2.0)) == CONFIDENCE_LEVEL
        assert round(CONFIDENCE_LEVEL, 2) == 0.95
        # The next conventional critical value, to show the derivation moves.
        assert round(math.erf(2.5758293035489004 / math.sqrt(2.0)), 2) == 0.99

    def test_the_column_label_agrees_with_the_published_level(self, table):
        """The two surfaces of one threshold, compared against each other.

        The header is literal text in `render.py`; the payload is derived from
        `Z`. Nothing made them agree, so this is where they are held together.
        """
        labels = [c.label for c in NODE_COLUMNS if "CI" in c.label]
        assert labels, [c.label for c in NODE_COLUMNS]
        percent = int(labels[0].split("%")[0])
        assert percent == round(table["confidence_level"] * 100)


class TestControls:
    """Each reads only what the payload carried before this round.

    Verified by neutering: with both new keys removed, all of these pass and
    only the tests above redden.
    """

    def test_the_interval_still_brackets_the_observed_rate(self, table):
        rows = {r["node"]: r for r in table["rows"]}
        row = rows["midway3-0385"]
        assert row["ci_low"] <= row["rate"] <= row["ci_high"]

    def test_the_verdict_and_p_value_are_still_there(self, table):
        rows = {r["node"]: r for r in table["rows"]}
        assert rows["midway3-0385"]["verdict"] == "worse"
        assert 0.0 <= rows["midway3-0385"]["p_value"] <= 1.0

    def test_the_pre_existing_table_keys_are_all_still_present(self, table):
        """The fix is additive; nothing was renamed or moved to make room."""
        for key in (
            "rows",
            "baseline",
            "trials",
            "hits",
            "metric",
            "workload",
            "workload_user",
            "tested_nodes",
            "held_back",
            "skipped_nodes",
        ):
            assert key in table, key

    def test_wilson_still_answers_for_a_perfect_record(self):
        """Untouched arithmetic, asserted directly rather than through a key."""
        low, high = wilson_interval(12, 12)
        assert high == 1.0
        assert 0.0 < low < 1.0
