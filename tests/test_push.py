import tomllib
from types import SimpleNamespace as NS

import pytest

from tent_peg.push import PushError, STAMP, plan_push, push_submission, wanted_marks

RUBRIC = {"criteria": [{"id": "correctness", "description": "Correctness"},
                       {"id": "style", "description": "Style"}]}
CRITERIA = {"Correctness": "_1", "Style": "_2"}


class FakeSub:
    def __init__(self, live=None):
        self.rubric_assessment = live
        self.edits = []

    def edit(self, rubric_assessment):
        self.edits.append(rubric_assessment)


class FakeAssignment:
    def __init__(self, sub):
        self.sub, self.asked = sub, []

    def get_submission(self, user_id, include=None):
        self.asked.append((user_id, include))
        return self.sub


def student(tmp_path, complete=True):
    d = tmp_path / "ann"
    d.mkdir()
    (d / "canvas.toml").write_text("user_id = 10\n")
    (d / "arb-results.toml").write_text(
        "complete = {}\n[[result]]\ncriterion = \"correctness\"\nscore = 10\n"
        "feedback = \"Good\"\n[[result]]\ncriterion = \"style\"\nscore = 1.5\n"
        "feedback = \"\"\n".format("true" if complete else "false"))
    return str(d)


def test_marks_use_descriptions():
    marks = wanted_marks({"complete": True, "result": [
        {"criterion": "style", "score": 2, "feedback": "ok"}]}, RUBRIC)
    assert marks == {"Style": {"points": 2, "comments": "ok"}}


def test_incomplete_and_unknown_refused():
    with pytest.raises(PushError):
        wanted_marks({"complete": False}, RUBRIC)
    with pytest.raises(PushError):
        wanted_marks({"complete": True, "result": [{"criterion": "x", "score": 1}]}, RUBRIC)


def test_first_push_writes_and_stamps(tmp_path):
    d = student(tmp_path)
    sub = FakeSub()
    a = FakeAssignment(sub)
    assert push_submission(d, a, RUBRIC, CRITERIA) == "pushed"
    assert a.asked == [(10, ["rubric_assessment"])]
    assert sub.edits == [{"_1": {"points": 10.0, "comments": "Good"},
                          "_2": {"points": 1.5, "comments": ""}}]
    stamp = tomllib.loads(open(d + "/" + STAMP).read())
    assert stamp["criterion"]["Style"]["points"] == 1.5


def test_repeat_push_is_unchanged(tmp_path):
    d = student(tmp_path)
    live = {"_1": {"points": 10, "comments": "Good"}, "_2": {"points": 1.5, "comments": ""}}
    sub = FakeSub(live)
    assert push_submission(d, FakeAssignment(sub), RUBRIC, CRITERIA) == "unchanged"
    assert sub.edits == []


def test_foreign_marks_not_clobbered(tmp_path):
    d = student(tmp_path)
    sub = FakeSub({"_1": {"points": 4, "comments": "someone else"}})
    with pytest.raises(PushError, match="Correctness"):
        push_submission(d, FakeAssignment(sub), RUBRIC, CRITERIA)
    assert sub.edits == []
    assert push_submission(d, FakeAssignment(sub), RUBRIC, CRITERIA, force=True) == "pushed"


def test_our_earlier_marks_may_be_updated(tmp_path):
    d = student(tmp_path)
    first = FakeSub()
    push_submission(d, FakeAssignment(first), RUBRIC, CRITERIA)
    live = {"_1": {"points": 10, "comments": "Good"}, "_2": {"points": 1.5, "comments": ""}}
    (tmp_path / "ann" / "arb-results.toml").write_text(
        "complete = true\n[[result]]\ncriterion = \"style\"\nscore = 2\n")
    sub = FakeSub(live)
    assert push_submission(d, FakeAssignment(sub), RUBRIC, CRITERIA) == "pushed"
    assert sub.edits[0]["_1"] == {"points": 10, "comments": "Good"}
    assert sub.edits[0]["_2"]["points"] == 2.0


def test_dry_run_writes_nothing(tmp_path):
    d = student(tmp_path)
    sub = FakeSub()
    assert push_submission(d, FakeAssignment(sub), RUBRIC, CRITERIA, dry_run=True) == "dry-run"
    assert sub.edits == [] and not (tmp_path / "ann" / STAMP).exists()


def test_criterion_missing_from_live_rubric():
    with pytest.raises(PushError):
        plan_push({"Gone": {"points": 1, "comments": ""}}, CRITERIA, None, {})


class GradeSub:
    def __init__(self, score=None):
        self.score, self.edits = score, []

    def edit(self, **kwargs):
        self.edits.append(kwargs)


def grade_world(tmp_path, live_score=None, comment="Well done\n"):
    d = tmp_path / "bob"
    d.mkdir()
    (d / "canvas.toml").write_text("user_id = 20\n")
    (d / "arb-results.toml").write_text("complete = true\nscore = 15.0\nout_of = 20\n")
    if comment:
        (d / "arb-feedback.txt").write_text(comment)
    sub = GradeSub(live_score)
    return str(d), NS(points_possible=10, get_submission=lambda uid, include=None: sub), sub


def test_grade_mode_scales_and_comments(tmp_path):
    from tent_peg.push import push_grade
    d, a, sub = grade_world(tmp_path)
    assert push_grade(d, a) == "pushed"
    assert sub.edits == [{"submission": {"posted_grade": 7.5},
                          "comment": {"text_comment": "Well done\n"}}]


def test_grade_mode_repeat_is_unchanged(tmp_path):
    from tent_peg.push import push_grade
    d, a, sub = grade_world(tmp_path)
    push_grade(d, a)
    sub.score = 7.5
    assert push_grade(d, a) == "unchanged"
    assert len(sub.edits) == 1


def test_grade_mode_changed_comment_only(tmp_path):
    from tent_peg.push import push_grade
    d, a, sub = grade_world(tmp_path)
    push_grade(d, a)
    sub.score = 7.5
    (tmp_path / "bob" / "arb-feedback.txt").write_text("Better\n")
    assert push_grade(d, a) == "pushed"
    assert sub.edits[1] == {"comment": {"text_comment": "Better\n"}}


def test_grade_mode_foreign_grade_refused(tmp_path):
    from tent_peg.push import push_grade
    d, a, sub = grade_world(tmp_path, live_score=3)
    with pytest.raises(PushError, match="3"):
        push_grade(d, a)
    assert push_grade(d, a, force=True) == "pushed"
