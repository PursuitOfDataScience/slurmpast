"""One window query, several sacct processes -- and the same answer.

`Sacct._query_partitioned` exists because a window query costs almost nothing in
the accounting database and almost everything in `sacct` laying out the rows.
Measured on midway3 (Slurm 20.11.8) over one user's last seven days -- 29,624
jobs, 89,163 rows, the 80 fields this module asks for:

    --format=JobID                  5.82 s     the database read
    --format=<80 fields>           14.49 s     what slurmpast asked for
    --format=<80 fields> -X         1.52 s     allocations only

    id listing + parallel reads     3.15 s

The risk that buys is that a split query answers something *different*, so what
is pinned here is sameness rather than speed: the same rows, through the same
filters, with every unsplit behaviour intact below the threshold. Verified
against the live scheduler before it was written down -- over the same fixed
window the two paths returned 22,359 jobs each, no id in one and not the other,
and the only records that differed were five still RUNNING, whose Elapsed sacct
computes as "now minus start" and which therefore differ between any two
queries seconds apart.
"""

import pytest

from slurmpast import sacct
from slurmpast.sacct import SAFE_DELIMITER, Sacct, SacctError
from tests.conftest import row


def _jobs(count, start=1000):
    """`count` distinct one-row jobs, keyed by id."""
    return [
        row(
            JobID=str(start + i),
            JobName="w",
            User="u",
            State="COMPLETED",
            ExitCode="0:0",
            Submit="2026-01-01T00:00:00",
            Start="2026-01-01T00:00:00",
            End="2026-01-01T00:10:00",
            ElapsedRaw="600",
        )
        for i in range(count)
    ]


class _Cluster:
    """A fake sacct that answers both halves of a partitioned query.

    Deliberately answers `-j` from the same table the listing came out of, so a
    partitioned read cannot accidentally pass by returning something the single
    read would not.
    """

    def __init__(self, rows, delimiter=SAFE_DELIMITER):
        self.rows = {r.split("|")[0]: r for r in rows}
        self.calls: list[list[str]] = []
        self.delimiter = delimiter

    def __call__(self, args):
        self.calls.append(list(args))
        if "--helpformat" in args:
            return " ".join(sacct._FIELDS)
        wanted = list(self.rows)
        for at, arg in enumerate(args):
            if arg == "-j":
                asked = set(args[at + 1].split(","))
                # `-j` names allocations and answers with their steps too, which
                # is the whole reason the split is by id.
                wanted = [i for i in self.rows if i.split(".")[0] in asked]
        if "-X" in args:
            # Allocations only: no step rows, which is what makes the listing cheap.
            wanted = [i for i in wanted if "." not in i]
            if "--format=JobID" in args:
                return "\n".join(wanted)
        return "\n".join(self.rows[i] for i in wanted).replace("|", self.delimiter)

    @property
    def reads(self):
        """Calls that fetched records, as opposed to listing ids or probing."""
        return [c for c in self.calls if "-X" not in c and "--helpformat" not in c]

    @property
    def listings(self):
        return [c for c in self.calls if "-X" in c]


class TestItSplits:
    def test_a_big_window_is_read_by_several_processes(self):
        cluster = _Cluster(_jobs(sacct.PARALLEL_MIN_JOBS + 200))
        Sacct(runner=cluster, probe=" ".join(sacct._FIELDS)).history(user="u", since="now-7days")
        assert len(cluster.listings) == 1, cluster.listings
        assert len(cluster.reads) > 1, cluster.reads

    def test_every_read_names_its_own_ids(self):
        cluster = _Cluster(_jobs(sacct.PARALLEL_MIN_JOBS + 200))
        Sacct(runner=cluster, probe=" ".join(sacct._FIELDS)).history(user="u", since="now-7days")
        named = []
        for call in cluster.reads:
            assert "-j" in call, call
            named += call[call.index("-j") + 1].split(",")
        # Every job exactly once: a partition, not an overlap and not a gap.
        assert sorted(named) == sorted(cluster.rows)

    def test_the_result_is_what_one_query_would_have_returned(self):
        rows = _jobs(sacct.PARALLEL_MIN_JOBS + 200)
        split = Sacct(runner=_Cluster(rows), probe=" ".join(sacct._FIELDS)).history(
            user="u", since="now-7days"
        )
        whole = Sacct(runner=_Cluster(rows), probe=" ".join(sacct._FIELDS), parallel=False).history(
            user="u", since="now-7days"
        )
        assert len(split) == len(whole)
        assert sorted(j.job_id for j in split) == sorted(j.job_id for j in whole)
        assert {j.job_id: j for j in split} == {j.job_id: j for j in whole}

    def test_a_job_keeps_all_of_its_steps(self):
        """The reason this splits by id and not by time.

        `sacct` filters STEP rows by the window too, so a job whose steps span a
        chunk boundary comes back with only some of them -- and MaxRSS is then
        read off a fragment. `-j` has no such boundary to fall on.
        """
        rows = _jobs(sacct.PARALLEL_MIN_JOBS + 10)
        rows.append(row(JobID="1000.batch", JobName="batch", State="COMPLETED", MaxRSS="64K"))
        rows.append(row(JobID="1000.extern", JobName="extern", State="COMPLETED", MaxRSS="4K"))
        cluster = _Cluster(rows)
        jobs = Sacct(runner=cluster, probe=" ".join(sacct._FIELDS)).history(
            user="u", since="now-7days"
        )
        first = next(j for j in jobs if j.job_id == "1000")
        assert [s.step_id for s in first.steps] == ["1000.batch", "1000.extern"]
        assert first.max_rss == 64 * 1024


class TestTheFiltersSelectJobsAndDoNotClipThem:
    """Every filter reaches the LISTING. None of them reaches the reads.

    This reverses what these tests asserted when they were written, and the
    reversal is the fix. Passing the window to the reads made the result
    byte-identical to a single query -- including its bug: sacct applies
    `-S`/`-E`/`--state` to STEP rows too, so a job that began before the window
    came back with only the steps inside it. Job 57477255 on midway3 was
    returned with 3 of its steps, summing to 0.4 CPU-seconds against a real
    21,383, and was therefore called idle and charged 41.42 GPU-hours to "never
    computed" -- the whole of one account's headline figure.

    It is also what `slurmpast.cache` needs: a record keyed by job id has to mean
    the same thing whichever window found it.

    So the listing decides WHICH jobs, and each is then read whole.
    """

    def _calls(self, **kwargs):
        cluster = _Cluster(_jobs(sacct.PARALLEL_MIN_JOBS + 200))
        Sacct(runner=cluster, probe=" ".join(sacct._FIELDS)).history(**kwargs)
        return cluster

    @pytest.mark.parametrize(
        ("kwargs", "flag", "value"),
        [
            ({"user": "alice", "since": "now-7days"}, "-u", "alice"),
            ({"user": "u", "since": "now-3days"}, "-S", "now-3days"),
            ({"user": "u", "since": "now-7days", "partition": "amd"}, "-r", "amd"),
            (
                {"user": "u", "since": "now-7days", "states": ["TIMEOUT"], "until": "now"},
                "--state",
                "TIMEOUT",
            ),
        ],
    )
    def test_the_filter_is_on_the_listing(self, kwargs, flag, value):
        cluster = self._calls(**kwargs)
        assert cluster.listings, "no listing was made"
        for call in cluster.listings:
            assert flag in call, call
            assert call[call.index(flag) + 1] == value, call

    @pytest.mark.parametrize(
        ("kwargs", "flag"),
        [
            ({"user": "alice", "since": "now-7days"}, "-u"),
            ({"user": "u", "since": "now-3days"}, "-S"),
            ({"user": "u", "since": "now-7days", "partition": "amd"}, "-r"),
            (
                {"user": "u", "since": "now-7days", "states": ["TIMEOUT"], "until": "now"},
                "--state",
            ),
        ],
    )
    def test_and_not_on_any_read(self, kwargs, flag):
        """A read names ids and nothing else, so it cannot clip a job's steps."""
        cluster = self._calls(**kwargs)
        assert cluster.reads, "no read was made"
        for call in cluster.reads:
            assert flag not in call, call
            assert "-j" in call, call

    def test_allusers_reaches_the_listing_only(self):
        cluster = self._calls(all_users=True, since="now-7days")
        assert cluster.listings and cluster.reads
        for call in cluster.listings:
            assert "--allusers" in call, call
        for call in cluster.reads:
            assert "--allusers" not in call, call

    def test_a_job_read_whole_keeps_steps_the_window_would_have_clipped(self):
        """The bug this reversal fixes, in one fixture.

        The fake below returns a step row only when the read carries no window,
        which is exactly how sacct behaves for a job that started earlier.
        """
        rows = _jobs(sacct.PARALLEL_MIN_JOBS + 10)
        cluster = _Cluster(rows)
        cluster.rows["1000.batch"] = row(
            JobID="1000.batch", JobName="batch", State="COMPLETED", TotalCPU="01:00:00"
        )
        jobs = Sacct(runner=cluster, probe=" ".join(sacct._FIELDS)).history(
            user="u", since="now-7days"
        )
        first = next(j for j in jobs if j.job_id == "1000")
        assert [s.step_id for s in first.steps] == ["1000.batch"]
        assert first.total_cpu == 3600.0


class TestWhenItDoesNot:
    """The controls. Each of these must leave the single query exactly as it was."""

    def test_a_small_window_is_one_read(self):
        cluster = _Cluster(_jobs(sacct.PARALLEL_MIN_JOBS - 1))
        jobs = Sacct(runner=cluster, probe=" ".join(sacct._FIELDS)).history(
            user="u", since="now-7days"
        )
        assert len(jobs) == sacct.PARALLEL_MIN_JOBS - 1
        assert len(cluster.reads) == 1, cluster.reads
        assert "-j" not in cluster.reads[0]

    def test_parallel_false_is_one_read_and_no_listing(self):
        cluster = _Cluster(_jobs(sacct.PARALLEL_MIN_JOBS + 200))
        Sacct(runner=cluster, probe=" ".join(sacct._FIELDS), parallel=False).history(
            user="u", since="now-7days"
        )
        assert cluster.listings == []
        assert len(cluster.reads) == 1, cluster.reads

    def test_naming_job_ids_does_not_go_through_the_listing(self):
        """`-j` is already scoped to the jobs asked for; there is nothing to list."""
        cluster = _Cluster(_jobs(3))
        Sacct(runner=cluster, probe=" ".join(sacct._FIELDS)).jobs(["1000", "1001"])
        assert cluster.listings == []
        assert len(cluster.reads) == 1

    def test_an_unlistable_window_falls_through_to_the_single_query(self):
        """A listing that fails is not an error -- the ordinary query reports it."""
        rows = _jobs(sacct.PARALLEL_MIN_JOBS + 200)
        cluster = _Cluster(rows)
        real = cluster.__call__

        def runner(args):
            if "-X" in args:
                raise SacctError("sacct: fatal: -X is not a thing here")
            return real(args)

        jobs = Sacct(runner=runner, probe=" ".join(sacct._FIELDS)).history(
            user="u", since="now-7days"
        )
        assert len(jobs) == len(rows)

    def test_a_failed_read_falls_back_and_stops_trying(self):
        rows = _jobs(sacct.PARALLEL_MIN_JOBS + 200)
        cluster = _Cluster(rows)
        real = cluster.__call__

        def runner(args):
            if "-j" in args:
                raise SacctError("sacct: Argument list too long")
            return real(args)

        client = Sacct(runner=runner, probe=" ".join(sacct._FIELDS))
        assert len(client.history(user="u", since="now-7days")) == len(rows)
        before = len(cluster.listings)
        # The discovery is remembered: the second query does not pay for it again.
        assert len(client.history(user="u", since="now-7days")) == len(rows)
        assert len(cluster.listings) == before


class TestBracketedArrays:
    """`sacct -j '49046820_[1-20%10]'` is a FATAL error in the sacct that printed it.

    The listing prints an unexpanded pending array in exactly that form, so the
    ids go through `queryable_job_id` before they are handed back. Reproduced
    against the live scheduler: three bracketed masters in a seven-day window
    made three of eight reads exit 1 with "Bad job array element specified",
    silently losing 11,109 of 29,627 jobs.
    """

    def test_the_master_is_asked_for_instead(self):
        rows = _jobs(sacct.PARALLEL_MIN_JOBS + 200)
        cluster = _Cluster(rows)
        cluster.rows["9000_[1-20%10]"] = row(JobID="9000_[1-20%10]", State="PENDING")
        cluster.rows["9000"] = row(JobID="9000", State="PENDING")
        Sacct(runner=cluster, probe=" ".join(sacct._FIELDS)).history(user="u", since="now-7days")
        named = set()
        for call in cluster.reads:
            named.update(call[call.index("-j") + 1].split(","))
        assert "9000_[1-20%10]" not in named
        assert "9000" in named


class TestTheStatsSurvive:
    def test_dropped_rows_are_summed_across_the_reads(self):
        """`--json` reports refused rows; a split query must not lose the count.

        Pinned on the `|` fallback, because that is the only delimiter a value
        can contain -- which is what a shifted row IS. `delimiter="|"` says the
        negotiation already happened, exactly as an sacct older than 17.11 leaves
        it.
        """
        rows = _jobs(sacct.PARALLEL_MIN_JOBS + 200)
        cluster = _Cluster(rows, delimiter="|")
        real = cluster.__call__

        def runner(args):
            text = real(args)
            if "-j" in args:
                # One row per read with a delimiter inside a value: shifted, and
                # dropped by the parser under its own documented rule.
                return text + "\n" + row(JobID="7", JobName="a|b")
            return text

        client = Sacct(runner=runner, probe=" ".join(sacct._FIELDS), delimiter="|")
        client.history(user="u", since="now-7days")
        assert len(cluster.reads) > 1, cluster.reads
        assert client.stats["dropped_rows"]["shifted"] == len(cluster.reads)


class TestTheThreadsAreInterruptible:
    """Why this does not use `concurrent.futures`.

    Its threads are non-daemon and joined at interpreter exit, so a Ctrl-C during
    the query would wait for every `sacct` still in flight -- up to the 300 s
    accounting budget. `cli.main` treats Ctrl-C as an ordinary way to stop this
    tool, and prices the wait it exists for: "an accounting database can
    genuinely take minutes ... Five minutes of silence is exactly when a user
    reaches for Ctrl-C."
    """

    def test_the_workers_are_daemon_threads(self):
        import threading

        seen = []
        sacct._in_parallel([lambda: seen.append(threading.current_thread().daemon)] * 4, 4)
        assert seen == [True] * 4

    def test_results_come_back_in_order(self):
        answers = sacct._in_parallel([(lambda n=n: n * 2) for n in range(20)], 4)
        assert answers == [n * 2 for n in range(20)]

    def test_the_first_error_is_raised(self):
        def boom():
            raise SacctError("no")

        with pytest.raises(SacctError, match="no"):
            sacct._in_parallel([boom, lambda: 1], 2)

    def test_one_item_still_runs(self):
        assert sacct._in_parallel([lambda: "only"], 8) == ["only"]

    def test_nothing_to_do_is_not_an_error(self):
        assert sacct._in_parallel([], 8) == []
