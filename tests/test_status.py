from types import SimpleNamespace as NS

from click.testing import CliRunner

from tent_peg import cli
from tent_peg.status import classify, format_tally, tally
from tests.test_cli import setup


def s(uid, state, **kw):
    return NS(user_id=uid, workflow_state=state, **kw)


def test_classify():
    assert classify(s(1, "graded")) == "marked"
    assert classify(s(1, "graded", grade_matches_current_submission=True)) == "marked"
    assert classify(s(1, "graded", grade_matches_current_submission=False)) == "regrade"
    assert classify(s(1, "unsubmitted", excused=True)) == "marked"
    assert classify(s(1, "submitted")) == "unmarked"
    assert classify(s(1, "pending_review")) == "unmarked"
    assert classify(s(1, "unsubmitted")) == "missing"


SUBS = [s(1, "graded"), s(2, "submitted"), s(3, "unsubmitted"), s(4, "submitted")]


def test_tally_limited_to_wanted():
    counts = tally(SUBS, wanted={1, 2})[None]
    assert [len(counts[k]) for k in ("marked", "unmarked", "missing")] == [1, 1, 0]
    assert format_tally(counts) == "marked 1/2, 1 unmarked"


def test_tally_by_group_with_unassigned():
    result = tally(SUBS, groups={"a": {1, 2}, "b": {2}})
    assert sorted(result) == ["a", "b", "unassigned"]
    assert len(result["a"]["marked"]) == 1 and len(result["b"]["unmarked"]) == 1
    assert [x.user_id for x in result["unassigned"]["missing"]] == [3]


def test_status_command_for_my_section(monkeypatch):
    setup(monkeypatch)
    r = CliRunner().invoke(cli.main, ["status", "9", "--list"])
    assert r.exit_code == 0, r.output
    assert "marked 0/2, 1 unmarked, 1 missing" in r.output
    assert "unmarked: " in r.output


def test_status_by_marker(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(cli, "marker_groups", lambda course, skip=(): {"mk": {10}})
    r = CliRunner().invoke(cli.main, ["status", "9", "--by-marker"])
    assert r.exit_code == 0, r.output
    assert "mk" in r.output and "unassigned" in r.output
