import pytest
from types import SimpleNamespace as NS

from tent_peg.markers import course_markers, marker_groups


def enrol(uid, name, type, section, restricted):
    return NS(user_id=uid, user={"sortable_name": name, "login_id": "l%d" % uid},
              type=type, course_section_id=section,
              limit_privileges_to_course_section=restricted)


class Course:
    def get_sections(self, include=None):
        return [NS(id=1, name="Lab 1", students=[{"id": 10}, {"id": 11}]),
                NS(id=2, name="Lab 2", students=[{"id": 20}])]

    def get_enrollments(self, type=None, state=None):
        return [enrol(1, "Zed, Z", "TaEnrollment", 1, True),
                enrol(1, "Zed, Z", "TaEnrollment", 2, True),
                enrol(2, "Boss, B", "TeacherEnrollment", 1, False)]


def test_markers():
    boss, zed = course_markers(Course())
    assert boss["name"] == "Boss, B" and boss["students"] is None
    assert zed["students"] == {10, 11, 20}
    assert set(zed["sections"].values()) == {"Lab 1", "Lab 2"}


class Classroom(Course):
    def get_sections(self, include=None):
        return [NS(id=1, name="All", students=[{"id": 10}, {"id": 11}, {"id": 20}]),
                NS(id=2, name="Marker 1", students=[{"id": 10}]),
                NS(id=3, name="Marker 2", students=[{"id": 11}, {"id": 20}])]

    def get_enrollments(self, type=None, state=None):
        return [enrol(1, "Mark, A", "TaEnrollment", 2, False),
                enrol(2, "Mark, B", "TaEnrollment", 3, False),
                enrol(2, "Mark, B", "TaEnrollment", 1, False),
                enrol(3, "Boss, B", "TeacherEnrollment", 1, False)]


def test_marker_groups_skip_named_sections():
    assert marker_groups(Classroom(), skip=["all"]) == {"Mark, A": {10}, "Mark, B": {11, 20}}
    assert marker_groups(Classroom(), skip=["all", "3"]) == {"Mark, A": {10}}


def test_marker_groups_without_skip_keep_every_section():
    assert marker_groups(Classroom())["Boss, B"] == {10, 11, 20}


def test_marker_groups_unknown_skip_is_an_error():
    with pytest.raises(ValueError, match="no such section: nope"):
        marker_groups(Classroom(), skip=["nope"])
