"""The command line: argument handling, exit codes, and the JSON contract.

`--demo` carries these tests, because it is the one path that needs no scheduler
-- the same reason CI can run them on a runner with no Slurm installed.
"""

import json

import pytest

from slurmpast import cli
from slurmpast.sacct import SacctError


def run(*argv):
    return cli.main(list(argv))


class TestRelativeTimeSpecs:
    """sacct rejects a bare `-7days` outright, but it is the obvious thing to
    type and argparse would meanwhile read it as an unknown option."""

    @pytest.mark.parametrize(
        "spec,expected",
        [
            ("-7days", "now-7days"),
            ("-1day", "now-1day"),
            ("- 3 weeks", "now-3weeks"),
            ("now-7days", "now-7days"),
            ("2026-01-01", "2026-01-01"),
            ("", ""),
        ],
    )
    def test_normalize(self, spec, expected):
        assert cli.normalize_time_spec(spec) == expected

    def test_none_is_left_alone(self):
        assert cli.normalize_time_spec(None) is None

    @pytest.mark.parametrize("flag", ["-S", "--since", "-E", "--until"])
    def test_a_leading_dash_value_is_glued_to_its_flag(self, flag):
        assert cli._glue_negative_values([flag, "-7days"]) == ["%s=-7days" % flag]

    def test_a_long_option_is_not_swallowed_as_a_value(self):
        assert cli._glue_negative_values(["-S", "--plain"]) == ["-S", "--plain"]

    def test_the_glued_form_survives_argparse_and_is_rewritten(self):
        argv = cli._glue_negative_values(["-S", "-7days", "--overview"])
        args = cli.build_parser().parse_args(argv)
        assert cli.normalize_time_spec(args.since) == "now-7days"

    def test_a_trailing_flag_with_no_value_does_not_crash(self):
        assert cli._glue_negative_values(["-S"]) == ["-S"]


class TestExitCodes:
    """The exit status is the only thing a script can read, so it has to mean
    something: 2 could not answer, 1 answered and it is bad, 0 answered."""

    def test_unreachable_sacct_is_a_clean_two(self, monkeypatch, capsys):
        def boom(*_a, **_kw):
            raise SacctError("cannot execute sacct: No such file or directory")

        monkeypatch.setattr(cli.Sacct, "history", boom)
        assert run("--overview", "--plain", "--no-color") == 2
        assert "slurmpast:" in capsys.readouterr().err

    def test_no_traceback_leaks_on_that_path(self, monkeypatch, capsys):
        def boom(*_a, **_kw):
            raise SacctError("nope")

        monkeypatch.setattr(cli.Sacct, "history", boom)
        run("--overview", "--plain", "--no-color")
        assert "Traceback" not in capsys.readouterr().err

    def test_critical_cross_run_findings_exit_one(self, capsys):
        """The demo history contains a workload that failed 18 of 20 runs."""
        assert run("--demo", "--plain", "--no-color") == 1
        assert capsys.readouterr().out

    def test_a_view_that_only_reports_exits_zero(self, capsys):
        assert run("--demo", "--overview", "--plain", "--no-color") == 0
        assert "JOB NAME" in capsys.readouterr().out


class TestTextViews:
    @pytest.mark.parametrize("view", ["--overview", "--patterns", "--nodes", "--sizing"])
    def test_every_view_renders_without_a_scheduler(self, view, capsys):
        assert run("--demo", view, "--no-color") == 0
        assert capsys.readouterr().out.strip()

    def test_the_window_is_named_as_synthetic_in_demo_mode(self, capsys):
        run("--demo", "--overview", "--plain", "--no-color")
        assert "synthetic demo data" in capsys.readouterr().out

    def test_no_machine_time_syntax_reaches_the_output(self, capsys):
        """Not "now-7days" -- the reader should not have to parse the tool's own
        arguments back out of its output."""
        run("--demo", "--overview", "--plain", "--no-color")
        assert "now-" not in capsys.readouterr().out


class TestJobIds:
    def test_an_explicit_id_selects_only_that_job(self, capsys):
        assert run("--demo", "5100057", "--no-color") in (0, 1)
        out = capsys.readouterr().out
        assert "5100057" in out
        assert "5100056" not in out

    def test_an_unknown_id_is_a_clean_error(self, capsys):
        assert run("--demo", "999999999", "--no-color") == 2
        assert "no demo job matches" in capsys.readouterr().err


class TestJsonPayload:
    def _payload(self, capsys, *argv):
        run("--demo", "--json", "--no-color", *argv)
        return json.loads(capsys.readouterr().out)

    def test_job_payload_is_valid_json_with_a_version(self, capsys):
        payload = self._payload(capsys, "5100056")
        assert payload["slurmpast"]
        assert payload["jobs"]

    def test_unread_values_are_null_never_zero(self, capsys):
        """A fabricated 0 is indistinguishable from a real measurement."""
        job = self._payload(capsys, "5100057")["jobs"][0]
        assert job["gpu"]["utilization"] is None
        assert job["energy_joules"] is None

    def test_cores_and_memory_both_reach_the_payload(self, capsys):
        job = self._payload(capsys, "5100056")["jobs"][0]
        assert job["cpu"]["utilization"] is not None
        assert job["memory"]["peak_bytes"] is not None

    @pytest.mark.parametrize("view", ["--overview", "--patterns", "--nodes", "--sizing"])
    def test_every_view_has_a_json_form(self, capsys, view):
        run("--demo", "--json", "--no-color", view)
        assert json.loads(capsys.readouterr().out)["slurmpast"]


class TestParser:
    def test_version_is_advertised(self, capsys):
        with pytest.raises(SystemExit) as exc:
            run("--version")
        assert exc.value.code == 0
        assert "slurmpast" in capsys.readouterr().out

    def test_the_epilog_examples_use_flags_that_exist(self):
        parser = cli.build_parser()
        known = {option for action in parser._actions for option in action.option_strings}
        for line in cli.EPILOG.splitlines():
            for token in line.split():
                if token.startswith("--"):
                    assert token in known, token


class TestJsonReportsSeverityInItsExitCode:
    """`--json` is the mode a script checks `$?` from, and it always returned 0.

    The same query rendered as text exited 1. (`--overview`/`--patterns`/`--nodes`/
    `--sizing` do always exit 0, deliberately -- they report rather than judge.
    This path judges.)
    """

    def test_json_and_text_agree_on_the_default_view(self, capsys):
        text = run("--demo", "--plain", "--no-color")
        capsys.readouterr()
        as_json = run("--demo", "--json", "--no-color")
        capsys.readouterr()
        assert as_json == text

    def test_the_findings_behind_the_code_are_in_the_payload(self, capsys):
        run("--demo", "--json", "--no-color")
        payload = json.loads(capsys.readouterr().out)
        assert "patterns" in payload, "the exit code rests on these"
        assert any(f["severity"] == "critical" for f in payload["patterns"])

    def test_explicit_ids_report_their_own_findings(self, capsys):
        """With ids given, per-job verdicts decide it -- as in the text path."""
        healthy = run("--demo", "--json", "--no-color", "5100021")
        capsys.readouterr()
        assert healthy in (0, 1)


class TestAMissingValueIsAnError:
    """`-u -p gpu` -- what `-u "$USER" -p gpu` becomes when $USER is unset.

    The negative-value glue took `-p` as the value of `-u`, leaving `gpu` as a job
    id and the partition filter silently gone. The error then named a job the user
    never typed.
    """

    def test_a_known_flag_is_not_swallowed_as_a_value(self):
        assert cli._glue_negative_values(["-u", "-p", "gpu"]) == ["-u", "-p", "gpu"]

    def test_argparse_gets_to_complain(self, capsys):
        with pytest.raises(SystemExit) as exit_info:
            run("--demo", "-u", "-p", "gpu", "--no-color")
        assert exit_info.value.code == 2
        assert "expected one argument" in capsys.readouterr().err

    def test_a_real_relative_time_still_glues(self):
        assert cli._glue_negative_values(["-S", "-7days"]) == ["-S=-7days"]

    def test_a_dash_leading_username_still_glues(self):
        assert cli._glue_negative_values(["-u", "-odd-name"]) == ["-u=-odd-name"]


class TestDemoHonoursFailed:
    """`--help` says "only jobs that failed"; the demo returned all 58.

    The real path narrows the whole history through sacct's `--state`, so the demo
    has to narrow the whole history too -- not just the list at the bottom.
    """

    def test_the_summary_shrinks(self, capsys):
        run("--demo", "--overview", "--json", "--no-color")
        everything = json.loads(capsys.readouterr().out)["summary"]["jobs"]
        run("--demo", "--failed", "--overview", "--json", "--no-color")
        only_failed = json.loads(capsys.readouterr().out)["summary"]["jobs"]
        assert 0 < only_failed < everything

    def test_what_is_left_really_did_fail(self, capsys):
        run("--demo", "--failed", "--json", "--no-color")
        payload = json.loads(capsys.readouterr().out)
        assert payload["jobs"]
        assert all(j["outcome"]["failed"] for j in payload["jobs"])
