"""Reusing a finished job's record, and every reason not to.

A job that has finished cannot change, so re-reading it from `sacct` on every
run is work nobody needs. Measured on midway3 over one user's last seven days --
29,624 jobs, 89,163 rows -- `slurmpast --plain` went from **5.5 s cold to 2.1 s
warm**, with byte-identical output.

The whole safety argument rests on the FINGERPRINT: every run asks sacct for
`JobID,State,End` over its window -- a query it was already making to partition
the read -- and a stored record is reused only when what sacct says right now is
exactly what it said when the record was filed. So the tests that matter here are
the ones where it must NOT be reused, and each is a way a record can stop being
the record that was stored:

    still running          never stored, so a live job is always re-read
    requeued after ending  `-D` lists both incarnations; the sequence differs
    state edited           same
    a different field list the columns behind the record are not these columns
    a different version    the record's class may not mean the same thing

The cost of getting this wrong is a post-mortem of a job that is not the job on
screen, which is why the checks are conservative and why a damaged file is
treated as no cache rather than as something to salvage.
"""

import pickle

import pytest

from slurmpast import cache, sacct
from slurmpast.model import Job
from slurmpast.sacct import Sacct
from tests.conftest import row


@pytest.fixture(autouse=True)
def _own_cache_dir(tmp_path, monkeypatch):
    """No test may touch the caller's real cache."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.delenv(cache.DISABLE_ENV, raising=False)
    yield


def _job(job_id="100", state="COMPLETED", end="2026-01-01T00:10:00", **kw):
    return Job(
        job_id=job_id,
        name="w",
        user="u",
        state=state,
        submit="2026-01-01T00:00:00",
        start="2026-01-01T00:00:00",
        end=end,
        elapsed=600.0,
        **kw,
    )


FIELDS = ("JobID", "State", "End")
MARK = (("COMPLETED", "2026-01-01T00:10:00"),)


class TestWhatIsWorthStoring:
    def test_a_finished_job_is(self):
        assert cache.is_storable(_job())

    def test_a_running_one_is_not(self):
        assert not cache.is_storable(_job(state="RUNNING", end=""))

    def test_and_neither_is_an_open_ended_record(self):
        """Trap 3 at the top of `sacct.py`: RUNNING with `End=Unknown` months on.

        Its Elapsed is "now minus start" and grows every time anybody asks, so it
        is the one record that must never be frozen. `open_ended` is a FIELD, set
        by `cli._mark_open_records` once squeue has been asked -- so it is checked
        on its own rather than inferred, and a record carrying it is refused even
        if its state were somehow terminal.
        """
        assert not cache.is_storable(_job(state="RUNNING", end="", open_ended=True))
        assert not cache.is_storable(_job(open_ended=True))

    def test_a_store_refuses_to_file_one(self, tmp_path):
        store = cache.Store(("t", "u"), FIELDS)
        store.put(_job(state="RUNNING", end=""), MARK)
        assert store.save() is False
        assert store.load() == {}


class TestTheFingerprintDecides:
    def _store(self):
        store = cache.Store(("t", "u"), FIELDS)
        store.put(_job(), MARK)
        store.save()
        return cache.Store(("t", "u"), FIELDS)  # a fresh reader of the same file

    def test_an_unchanged_job_comes_back(self):
        assert self._store().get("100", MARK) is not None

    def test_a_requeue_after_the_fact_does_not(self):
        """`-D` lists every incarnation, so a second one changes the sequence."""
        requeued = (("NODE_FAIL", "2026-01-01T00:10:00"), ("COMPLETED", "2026-01-01T02:00:00"))
        assert self._store().get("100", requeued) is None

    def test_an_edited_state_does_not(self):
        assert self._store().get("100", (("CANCELLED", "2026-01-01T00:10:00"),)) is None

    def test_a_moved_end_does_not(self):
        assert self._store().get("100", (("COMPLETED", "2026-01-01T09:99:99"),)) is None

    def test_an_unknown_job_does_not(self):
        assert self._store().get("999", MARK) is None


class TestTheFileIsRefusedWhenItCannotBeTrusted:
    def _written(self):
        store = cache.Store(("t", "u"), FIELDS)
        store.put(_job(), MARK)
        store.save()
        return store._path

    def test_a_different_field_list_reads_as_empty(self):
        self._written()
        assert cache.Store(("t", "u"), ("JobID", "State")).load() == {}

    def test_a_different_scope_reads_as_empty(self):
        """A different user or cluster is a different file, not a shared one."""
        self._written()
        assert cache.Store(("t", "someone-else"), FIELDS).load() == {}

    def test_a_different_package_version_reads_as_empty(self, monkeypatch):
        path = self._written()
        with open(path, "rb") as handle:
            payload = pickle.load(handle)
        payload["version"] = "0.0.0-not-this-one"
        with open(path, "wb") as handle:
            pickle.dump(payload, handle)
        assert cache.Store(("t", "u"), FIELDS).load() == {}

    def test_a_truncated_file_reads_as_empty(self):
        path = self._written()
        with open(path, "r+b") as handle:
            handle.truncate(12)
        assert cache.Store(("t", "u"), FIELDS).load() == {}

    def test_rubbish_reads_as_empty(self):
        path = self._written()
        with open(path, "wb") as handle:
            handle.write(b"this is not a pickle")
        assert cache.Store(("t", "u"), FIELDS).load() == {}

    def test_a_missing_file_reads_as_empty(self):
        assert cache.Store(("t", "never-written"), FIELDS).load() == {}

    def test_an_unwritable_directory_is_not_an_error(self, monkeypatch, tmp_path):
        """A full quota or a read-only home costs the reader nothing but time."""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "nope"))
        (tmp_path / "nope").mkdir()
        (tmp_path / "nope").chmod(0o500)
        store = cache.Store(("t", "u"), FIELDS)
        store.put(_job(), MARK)
        try:
            assert store.save() is False
        finally:
            (tmp_path / "nope").chmod(0o700)


class TestTheSwitches:
    def test_the_environment_variable_turns_it_off(self, monkeypatch):
        monkeypatch.setenv(cache.DISABLE_ENV, "1")
        assert not cache.enabled()

    def test_an_empty_value_does_not(self):
        assert cache.enabled({"SLURMPAST_NO_CACHE": "  "})

    def test_sacct_honours_it(self, monkeypatch):
        monkeypatch.setenv(cache.DISABLE_ENV, "1")
        assert Sacct()._store() is None

    def test_sacct_honours_the_constructor(self):
        assert Sacct(cache=False)._store() is None

    def test_an_injected_runner_never_caches(self):
        """Canned text is not this cluster's accounting database.

        The one way this could hand back a job that never existed, so it is shut
        off by the runner rather than by anything a caller has to remember.
        """
        assert Sacct(runner=lambda args: "", probe="JobID")._store() is None

    def test_the_default_does(self):
        """CONTROL — without which every test above passes vacuously."""
        assert Sacct()._store() is not None


class TestTheCliFlag:
    def _built(self, monkeypatch, capsys, argv):
        from slurmpast import cli

        built = []

        def spy(**kw):
            built.append(kw)
            return Sacct(runner=lambda a: "", probe="JobID")

        monkeypatch.setattr(cli, "Sacct", spy)
        cli.main(argv)
        capsys.readouterr()
        return built

    def test_no_cache_reaches_sacct(self, monkeypatch, capsys):
        built = self._built(monkeypatch, capsys, ["--plain", "--no-cache", "--demo", "--no-color"])
        assert built and built[0].get("cache") is False

    def test_and_without_it_the_cache_is_asked_for(self, monkeypatch, capsys):
        """CONTROL — the flag is what turns it off, not the demo path."""
        built = self._built(monkeypatch, capsys, ["--plain", "--demo", "--no-color"])
        assert built and built[0].get("cache") is True


class TestEviction:
    def test_the_oldest_records_go_first(self, monkeypatch):
        monkeypatch.setattr(cache, "MAX_ENTRIES", 3)
        store = cache.Store(("t", "u"), FIELDS)
        for n in range(6):
            end = "2026-01-0%dT00:00:00" % (n + 1)
            store.put(_job(job_id=str(n), end=end), ((("COMPLETED", end)),))
        store.save()
        kept = sorted(cache.Store(("t", "u"), FIELDS).load())
        assert kept == ["3", "4", "5"], kept


class TestTheWindowListingCarriesIt:
    """The fingerprint has to come off the same query that partitions the read."""

    def _listing(self, text):
        client = Sacct(runner=lambda args: text, probe=" ".join(sacct._FIELDS), delimiter="|")
        return client._window_listing(["-u", "u"])

    def test_one_incarnation(self):
        assert self._listing("100|COMPLETED|2026-01-01T00:10:00") == [
            ("100", (("COMPLETED", "2026-01-01T00:10:00"),))
        ]

    def test_two_incarnations_are_one_entry_in_order(self):
        text = "100|NODE_FAIL|2026-01-01T00:10:00\n100|COMPLETED|2026-01-01T02:00:00"
        assert self._listing(text) == [
            (
                "100",
                (
                    ("NODE_FAIL", "2026-01-01T00:10:00"),
                    ("COMPLETED", "2026-01-01T02:00:00"),
                ),
            )
        ]

    def test_a_truncated_state_is_folded_first(self):
        """`OUT_OF_ME+` and `OUT_OF_MEMORY` are the same claim, so the same mark.

        Otherwise a cluster whose sacct truncates in the listing but not in the
        read would miss on every job, for ever.
        """
        assert self._listing("100|OUT_OF_ME+|2026-01-01T00:10:00")[0][1] == (
            ("OUT_OF_MEMORY", "2026-01-01T00:10:00"),
        )

    def test_a_line_that_is_not_a_record_is_dropped(self):
        assert self._listing("not a job id|x|y\n100|COMPLETED|2026-01-01T00:10:00") == [
            ("100", (("COMPLETED", "2026-01-01T00:10:00"),))
        ]

    def test_the_ids_keep_sacct_s_spelling(self):
        """`queryable_job_id` is applied when ASKING, not here: the record will be
        keyed by what sacct printed."""
        listed = self._listing("900_[5-10]|PENDING|Unknown")
        assert listed[0][0] == "900_[5-10]"


class TestAWholeReadIsTheSameEitherWay:
    """The property the whole feature is judged on, in miniature.

    The real check is not here and could not be: it ran `slurmpast --plain` over
    a fixed window on 29,624 real jobs cold, warm and with `--no-cache`, and all
    three were byte-identical.
    """

    def _rows(self, count):
        return [
            row(
                JobID=str(1000 + i),
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

    def test_a_second_read_returns_the_same_jobs(self, monkeypatch, tmp_path):
        rows = self._rows(sacct.PARALLEL_MIN_JOBS + 50)
        table = {r.split("|")[0]: r for r in rows}
        calls = []

        def runner(args):
            calls.append(list(args))
            if "--helpformat" in args:
                return " ".join(sacct._FIELDS)
            wanted = list(table)
            for at, arg in enumerate(args):
                if arg == "-j":
                    asked = set(args[at + 1].split(","))
                    wanted = [i for i in table if i in asked]
            if "-X" in args and "--format=JobID,State,End" in args:
                return "\n".join("%s\x1fCOMPLETED\x1f2026-01-01T00:10:00" % i for i in wanted)
            return "\n".join(table[i] for i in wanted).replace("|", "\x1f")

        # The runner is injected, so `Sacct` refuses to cache -- which is the
        # point of that rule. Force a store in, to exercise the merge itself.
        def client():
            each = Sacct(runner=runner, probe=" ".join(sacct._FIELDS))
            each._store_cache = cache.Store(("test", "u"), tuple(each.fields))
            each._store = lambda: each._store_cache
            return each

        first = client().history(user="u", since="now-7days")
        reads = sum(1 for c in calls if "-j" in c)
        assert reads > 0
        calls.clear()
        second = client().history(user="u", since="now-7days")
        assert {j.job_id: j for j in first} == {j.job_id: j for j in second}
        assert sorted(j.job_id for j in first) == sorted(j.job_id for j in second)
        # And it did not go back to sacct for any of them.
        assert not [c for c in calls if "-j" in c], calls
