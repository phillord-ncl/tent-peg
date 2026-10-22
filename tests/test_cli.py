from types import SimpleNamespace as NS

from click.testing import CliRunner

from tent_peg import cli
from tests.test_download import FakeAssignment, FakeCourse, world


class FakeCanvas:
    def __init__(self, course):
        self.course = course

    def get_course(self, id):
        return self.course

    def get_current_user(self):
        return NS(id=1)


def setup(monkeypatch):
    course, assignment = world()
    course.get_assignment = lambda id: assignment
    assignment.name = 'Project (anon)'
    course.get_assignments = lambda: [assignment, NS(id=2, name='Other')]
    course.get_enrollments = lambda user_id: [NS(course_section_id=7)]
    monkeypatch.setattr(cli.tp_config, "config_canvas", lambda: FakeCanvas(course))
    monkeypatch.setattr(cli.tp_config, "config_course", lambda: 5)
    monkeypatch.setattr(cli, "course_by_exact", lambda ident, canvas: canvas.course)


def test_download_defaults_to_my_sections(monkeypatch, tmp_path):
    setup(monkeypatch)
    r = CliRunner().invoke(cli.main, ["download", "9", "--out", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert [p.name for p in tmp_path.iterdir()] == ["ann@ncl.ac.uk"]
    assert "1 submissions written" in r.output


def test_download_named_sections(monkeypatch, tmp_path):
    setup(monkeypatch)
    r = CliRunner().invoke(cli.main, ["download", "9", "--section", "7", "--section", "8", "--out", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert len(list(tmp_path.iterdir())) == 2


def test_download_error_is_clean(monkeypatch, tmp_path):
    setup(monkeypatch)
    r = CliRunner().invoke(cli.main, ["download", "9", "--section", "99", "--out", str(tmp_path)])
    assert r.exit_code == 1 and "no such section" in r.output


def test_download_by_name(monkeypatch, tmp_path):
    setup(monkeypatch)
    r = CliRunner().invoke(cli.main, ["download", "project", "--out", str(tmp_path)])
    assert r.exit_code == 0, r.output
    r = CliRunner().invoke(cli.main, ["download", "nope", "--out", str(tmp_path)])
    assert r.exit_code == 1 and "no assignment matching" in r.output


def test_not_in_any_section(monkeypatch, tmp_path):
    setup(monkeypatch)
    cli.tp_config.config_canvas().course.get_enrollments = lambda user_id: []
    r = CliRunner().invoke(cli.main, ["download", "9", "--out", str(tmp_path)])
    assert r.exit_code == 1 and "not enrolled in any section" in r.output
    assert list(tmp_path.iterdir()) == []


def test_all_needs_no_section(monkeypatch, tmp_path):
    setup(monkeypatch)
    cli.tp_config.config_canvas().course.get_enrollments = lambda user_id: []
    r = CliRunner().invoke(cli.main, ["download", "9", "--all", "--out", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert len(list(tmp_path.iterdir())) == 2


def test_all_with_section_is_refused(monkeypatch, tmp_path):
    setup(monkeypatch)
    r = CliRunner().invoke(cli.main, ["download", "9", "--all", "--section", "7", "--out", str(tmp_path)])
    assert r.exit_code != 0 and "do not go together" in r.output


def test_marks_push_dry_run(monkeypatch, tmp_path):
    from tests.test_push import RUBRIC, FakeSub, student
    setup(monkeypatch)
    d = student(tmp_path)
    (tmp_path / "ann" / "r.rubric.toml").write_text(
        '[[criteria]]\nid = "correctness"\ndescription = "Correctness"\n'
        '[[criteria]]\nid = "style"\ndescription = "Style"\n')
    sub = FakeSub()
    a = cli.find_assignment
    monkeypatch.setattr(cli, "find_assignment", lambda course, ident: NS(
        rubric=[{"id": "_1", "description": "Correctness"},
                {"id": "_2", "description": "Style"}],
        get_submission=lambda uid, include=None: sub))
    r = CliRunner().invoke(cli.main, [
        "marks", "push", "9", str(tmp_path), "--dry-run",
        "--rubric", str(tmp_path / "ann" / "r.rubric.toml")])
    assert r.exit_code == 0, r.output
    assert "ann: dry-run" in r.output and sub.edits == []
