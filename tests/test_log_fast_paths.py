"""The shortcuts in `logs.py`, and the long way round they have to agree with.

Resolving logs for a whole history is the work the dashboard does in a thread
while the reader is using it, so it is also the work that decides whether a
keypress lands. Measured on a real seven-day history of 29,617 jobs before any
of this: `assign_logs` took **16.7 s**, and while it ran, moving the cursor one
row in the dashboard took between **0.85 s and 5.4 s**. With `--no-logs` the same
keypress took 5 ms — which is what identified it.

Three shortcuts got it to 1.2 s, and each one is only safe while a property
holds:

* the derived directory lists are cached, which is sound only because they are a
  pure function of (work directory, `--log-dir` set, cwd);
* a conventional filename is ruled out against the directory listing instead of
  being built into a path and split apart again;
* `_carries_ident` replaces a regex that was recompiled for every job.

So what is pinned here is that each shortcut answers what the long way round
answers. The whole-history check that actually caught the drift is not in this
file and could not be: it ran `assign_logs` over those 29,617 jobs against a
893-file tree, both before and after, and compared all 29,617 entries — 19,666
matched, 229 of them by timing, and the two agreed on every one.
"""

import os

import pytest

from slurmpast import logs
from slurmpast.logs import Scan, assign_logs, candidate_paths, find_log, find_log_by_name
from slurmpast.model import Job


def _job(job_id, work_dir, name="train", start=None, end=None, **kw):
    return Job(
        job_id=job_id,
        name=name,
        user="u",
        state="COMPLETED",
        submit=start,
        start=start,
        end=end,
        work_dir=work_dir,
        **kw,
    )


@pytest.fixture
def tree(tmp_path):
    """A work directory with logs in the places the resolver looks."""
    for sub in ("", "logs", "report", "out"):
        (tmp_path / sub).mkdir(exist_ok=True)
    (tmp_path / "slurm-100.out").write_text("a")
    (tmp_path / "logs" / "101.err").write_text("b")
    (tmp_path / "report" / "train-102.out").write_text("c")  # by id, not by spelling
    (tmp_path / "out" / "job-103.out").write_text("d")
    (tmp_path / "1104-other.out").write_text("e")  # must NOT match job 104
    return tmp_path


class TestTheScanShortcutFindsWhatAStatWouldHave:
    """`find_log` with a Scan rules a name out against the listing; without one it
    stats every candidate. They have to reach the same file."""

    @pytest.mark.parametrize("job_id", ["100", "101", "103", "104", "999"])
    def test_both_routes_agree(self, tree, job_id):
        job = _job(job_id, str(tree))
        slow = find_log(job)  # os.path.isfile on every candidate
        fast = find_log(job, exists=Scan().exists, scan=Scan())
        assert slow == fast, job_id

    def test_and_the_fixture_is_not_vacuous(self, tree):
        """CONTROL — at least one of those found something and one found nothing."""
        assert find_log(_job("100", str(tree))) is not None
        assert find_log(_job("999", str(tree))) is None

    def test_a_recorded_path_still_wins_over_a_conventional_one(self, tree):
        recorded = tree / "logs" / "recorded.out"
        recorded.write_text("r")
        job = _job("100", str(tree), std_out=str(recorded))
        assert find_log(job, exists=Scan().exists, scan=Scan()) == str(recorded)

    def test_a_dangling_symlink_is_still_refused(self, tree):
        """The listing settles absence, never presence -- and this is why."""
        link = tree / "slurm-200.out"
        os.symlink(str(tree / "nothing-here.out"), str(link))
        assert find_log(_job("200", str(tree)), exists=Scan().exists, scan=Scan()) is None


class TestCandidatePathsAreTheSamePaths:
    def test_the_parts_rejoin_to_the_paths(self, tree):
        job = _job("100", str(tree))
        rejoined = [os.path.join(base, name) for base, name in logs._candidate_parts(job)]
        assert candidate_paths(job)[-len(rejoined) :] == rejoined

    def test_every_path_is_already_normal(self, tree):
        """`normpath` was dropped from the join; it must have had nothing to do."""
        job = _job("100", str(tree) + "/./sub/..", name="x")
        for path in candidate_paths(job):
            assert path == os.path.normpath(path), path

    def test_a_recorded_path_leads(self, tree):
        job = _job("100", str(tree), std_out="/work/real.out")
        assert candidate_paths(job)[0] == "/work/real.out"

    def test_an_array_element_asks_for_the_master_too(self, tree):
        names = {os.path.basename(p) for p in candidate_paths(_job("60_4", str(tree)))}
        assert "slurm-60_4.out" in names
        assert "slurm-60.out" in names


class TestCarriesIdent:
    """The literal scan that replaced a regex compiled once per job."""

    @pytest.mark.parametrize(
        ("name", "ident", "expected"),
        [
            ("slurm-60.out", "60", True),
            ("1060-train.out", "60", False),  # the delimiting rule, in one line
            ("601-train.out", "60", False),
            ("train-60-1.out", "60", True),
            ("60.out", "60", True),
            ("out-60", "60", True),
            ("x60x.out", "60", True),  # letters are not digits, so they delimit
            ("slurm-60_4.out", "60_4", True),
            ("slurm-160_4.out", "60_4", False),
            ("nothing.out", "60", False),
            ("60-60.out", "60", True),
            ("160-60.out", "60", True),  # the second occurrence is delimited
        ],
    )
    def test_it_matches_the_regex_it_replaced(self, name, ident, expected):
        import re

        pattern = r"(?<!\d)%s(?!\d)" % re.escape(ident)
        assert logs._carries_ident(name, ident) is expected
        assert bool(re.search(pattern, name)) is expected  # the control it replaced

    def test_a_file_carrying_the_id_is_found_whatever_else_is_in_the_name(self, tree):
        assert find_log_by_name(_job("102", str(tree))) == str(tree / "report" / "train-102.out")

    def test_and_a_longer_number_containing_it_is_not(self, tree):
        """CONTROL — `1104-other.out` must not be handed to job 104."""
        assert find_log_by_name(_job("104", str(tree))) is None


class TestTheDirectoryCacheIsKeyedOnEverythingItDependsOn:
    def test_a_different_work_directory_gets_different_directories(self, tmp_path):
        one = logs._candidate_dirs(_job("1", str(tmp_path / "a")))
        two = logs._candidate_dirs(_job("1", str(tmp_path / "b")))
        assert one != two

    def test_a_different_log_dir_set_gets_different_directories(self, tmp_path):
        job = _job("1", str(tmp_path))
        assert logs._candidate_dirs(job, extra_dirs=["/x"]) != logs._candidate_dirs(
            job, extra_dirs=["/y"]
        )

    def test_a_chdir_is_honoured(self, tmp_path, monkeypatch):
        """The cwd is a search root, so it is part of the key rather than baked in."""
        job = _job("1", "")  # no work dir, so cwd is all there is
        monkeypatch.chdir(tmp_path)
        here = logs._candidate_dirs(job)
        elsewhere = tmp_path / "deeper"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        assert logs._candidate_dirs(job) != here

    def test_the_scanned_directories_are_keyed_the_same_way(self, tmp_path):
        job = _job("1", str(tmp_path))
        assert logs._log_dirs(job, ["/x"]) != logs._log_dirs(job, ["/y"])
        assert logs._log_dirs(job, ["/x"])[0] == (os.path.normpath("/x"), True)


class TestAssignLogsStillResolvesAcrossJobs:
    """The property the whole function exists for, unchanged by the shortcuts:
    two jobs cannot be handed the same guessed file."""

    def test_a_contested_file_goes_to_one_job(self, tmp_path):
        (tmp_path / "logs").mkdir()
        only = tmp_path / "logs" / "somebody.out"
        only.write_text("x" * 20)
        os.utime(str(only), (1_700_000_600, 1_700_000_600))
        stamp = "2023-11-14T22:23:20"  # 1700000600 UTC-ish; both jobs bracket it
        jobs = [
            _job("500", str(tmp_path), name="somebody", start=stamp, end=stamp),
            _job("501", str(tmp_path), name="somebody", start=stamp, end=stamp),
        ]
        resolved = assign_logs(jobs, extra_dirs=[str(tmp_path / "logs")])
        got = [path for path, _inferred in resolved.values() if path]
        assert len(got) <= 1, resolved

    def test_a_name_match_is_not_contested(self, tree):
        """CONTROL — two jobs with the SAME recorded path both keep it."""
        shared = str(tree / "slurm-100.out")
        jobs = [_job("700", str(tree), std_out=shared), _job("701", str(tree), std_out=shared)]
        resolved = assign_logs(jobs)
        assert resolved["700"] == (shared, False)
        assert resolved["701"] == (shared, False)
