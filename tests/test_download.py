import tomllib
from types import SimpleNamespace as NS

import pytest

from tent_peg.download import DownloadError, download_assignment


class FakeAttachment:
    def __init__(self, name, content="x = 1\n"):
        self.display_name, self.content = name, content

    def download(self, path):
        with open(path, "w") as f:
            f.write(self.content)


def sub(id, user_id, name, attachments=(), **kw):
    return NS(id=id, user_id=user_id, user={"name": name, "login_id": "l%d" % user_id},
              workflow_state=kw.pop("workflow_state", "submitted"),
              attachments=list(attachments), attempt=1, late=False,
              submitted_at="2026-10-01T10:00:00Z", **kw)


class FakeCourse:
    def __init__(self, subs, sections, users):
        self.sections, self.users = sections, users

    def get_sections(self, include=None):
        return [NS(id=i, name=n, students=[{"id": s} for s in ids])
                for i, (n, ids) in self.sections.items()]

    def get_users(self, enrollment_type=None, include=None):
        return [NS(id=i, name="N%d" % i, login_id="C%d" % i, sis_user_id="9%d" % i,
                   **({"email": e} if e else {})) for i, e in self.users.items()]


class FakeAssignment:
    def __init__(self, subs, anonymous=False):
        self.subs, self.anonymous_grading = subs, anonymous

    def get_submissions(self, include=None):
        return self.subs


def world():
    subs = [sub(1, 10, "A", [FakeAttachment("a.py")]),
            sub(2, 20, "B", [FakeAttachment("b.py"), FakeAttachment("r.md")]),
            sub(3, 30, "C", workflow_state="unsubmitted")]
    course = FakeCourse(subs, {7: ("Lab 1", [10, 30]), 8: ("Lab 2", [20])},
                        {10: "Ann@Ncl.ac.uk", 20: "bob@ncl.ac.uk", 30: "c@ncl.ac.uk"})
    return course, FakeAssignment(subs)


def test_all_named_by_email(tmp_path):
    course, a = world()
    made = download_assignment(course, a, str(tmp_path))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ann@ncl.ac.uk", "bob@ncl.ac.uk"]
    assert len(made) == 2
    meta = tomllib.loads((tmp_path / "bob@ncl.ac.uk" / "canvas.toml").read_text())
    assert meta["files"] == ["b.py", "r.md"]
    assert meta["sections"] == ["Lab 2"] and meta["user_id"] == 20
    assert (tmp_path / "bob@ncl.ac.uk" / "r.md").exists()


def test_section_filter(tmp_path):
    course, a = world()
    download_assignment(course, a, str(tmp_path), section_ids={7})
    assert [p.name for p in tmp_path.iterdir()] == ["ann@ncl.ac.uk"]


def test_unknown_section(tmp_path):
    course, a = world()
    with pytest.raises(DownloadError, match="no such section"):
        download_assignment(course, a, str(tmp_path), section_ids={99})


def test_existing_left_alone_unless_forced(tmp_path):
    course, a = world()
    download_assignment(course, a, str(tmp_path))
    (tmp_path / "ann@ncl.ac.uk" / "a.py").write_text("marked\n")
    assert download_assignment(course, a, str(tmp_path)) == []
    assert (tmp_path / "ann@ncl.ac.uk" / "a.py").read_text() == "marked\n"
    assert len(download_assignment(course, a, str(tmp_path), force=True)) == 2


def test_missing_email_is_an_error(tmp_path):
    course, a = world()
    course.users[10] = None
    with pytest.raises(DownloadError, match="no email visible"):
        download_assignment(course, a, str(tmp_path))


def test_hostile_filename_stays_inside(tmp_path):
    course, a = world()
    a.subs[0].attachments = [FakeAttachment("../../evil.py")]
    download_assignment(course, a, str(tmp_path))
    assert not (tmp_path.parent / "evil.py").exists()
    assert (tmp_path / "ann@ncl.ac.uk" / "evil.py").exists()


def test_login_layout(tmp_path):
    course, a = world()
    download_assignment(course, a, str(tmp_path), layout="login")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["c10", "c20"]


def test_anonymous_defaults_to_login_and_hides_identity(tmp_path):
    course, a = world()
    a.anonymous_grading = True
    download_assignment(course, a, str(tmp_path))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["c10", "c20"]
    text = (tmp_path / "c10" / "canvas.toml").read_text()
    meta = tomllib.loads(text)
    assert meta["anonymous"] is True and meta["login_id"] == "c10"
    assert not {"name", "email", "sis_id"} & set(meta)
    assert "ncl.ac.uk" not in text


def test_anonymous_can_be_named_by_email(tmp_path):
    course, a = world()
    a.anonymous_grading = True
    download_assignment(course, a, str(tmp_path), layout="email")
    assert "ann@ncl.ac.uk" in [p.name for p in tmp_path.iterdir()]


def test_unknown_layout(tmp_path):
    course, a = world()
    with pytest.raises(DownloadError, match="unknown layout"):
        download_assignment(course, a, str(tmp_path), layout="initials")
