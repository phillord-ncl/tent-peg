from types import SimpleNamespace as NS

from click.testing import CliRunner

from tent_peg import cli
from tent_peg.status import classify, format_tally, format_total, tally
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
    assert format_tally(counts) == "marked 1/2"


def test_tally_by_group_with_unassigned():
    result = tally(SUBS, groups={"a": {1, 2}, "b": {2}})
    assert sorted(result) == ["a", "b", "unassigned"]
    assert len(result["a"]["marked"]) == 1 and len(result["b"]["unmarked"]) == 1
    assert [x.user_id for x in result["unassigned"]["missing"]] == [3]


def test_status_command_for_my_section(monkeypatch):
    setup(monkeypatch)
    r = CliRunner().invoke(cli.main, ["status", "9", "--list"])
    assert r.exit_code == 0, r.output
    assert "marked 0/1" in r.output
    assert "unmarked: " in r.output


def test_status_by_marker(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(cli, "marker_groups", lambda course, skip=(): {"mk": {10}})
    r = CliRunner().invoke(cli.main, ["status", "9", "--by-marker"])
    assert r.exit_code == 0, r.output
    assert "mk  marked 0/1" in r.output
    assert "Total: marked 0/2, Unassigned 1, Unsubmitted 1/3" in r.output


def test_format_tally_counts_only_submissions_and_flags_regrades():
    subs = [s(1, "graded"), s(2, "graded", grade_matches_current_submission=False),
            s(3, "submitted"), s(4, "unsubmitted")]
    assert format_tally(tally(subs)[None]) == "marked 1/3, 1 regrade"


def test_format_total_counts_a_shared_student_once():
    result = tally(SUBS, groups={"a": {1, 2}, "b": {2}})
    assert format_total(result) == "Total: marked 1/3, Unassigned 1, Unsubmitted 1/4"


def test_format_tally_can_show_students_not_submitted():
    subs = [s(1, "graded"), s(2, "unsubmitted"), s(3, "unsubmitted")]
    counts = tally(subs)[None]
    assert format_tally(counts) == "marked 1/1"
    assert format_tally(counts, missing=True) == "marked 1/1, 2 not submitted"
