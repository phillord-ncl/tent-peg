import pytest
from types import SimpleNamespace as NS

from tent_peg.markers import course_markers, marker_groups


def enrol(uid, name, type, section, restricted):
    return NS(user_id=uid, user={"sortable_name": name, "name": " ".join(reversed(name.split(", "))), "login_id": "l%d" % uid},
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
    assert marker_groups(Classroom(), skip=["all"]) == {"A Mark": {10}, "B Mark": {11, 20}}
    assert marker_groups(Classroom(), skip=["all", "3"]) == {"A Mark": {10}}


def test_marker_groups_ignore_sections_shared_by_markers():
    told = []
    assert marker_groups(Classroom(), report=told.append) == {"A Mark": {10}, "B Mark": {11, 20}}
    assert told == []  # "All" holds the whole class: shared, but expected


def test_marker_groups_warn_of_a_shared_part_class_section():
    class Shared(Classroom):
        def get_sections(self, include=None):
            return [NS(id=1, name="All", students=[{"id": 10}, {"id": 11}, {"id": 20}]),
                    NS(id=2, name="Marker 1", students=[{"id": 10}]),
                    NS(id=3, name="Marker 2", students=[{"id": 11}])]

        def get_enrollments(self, type=None, state=None):
            return Classroom.get_enrollments(self) + [enrol(1, "Mark, A", "TaEnrollment", 3, False)]
    told = []
    assert marker_groups(Shared(), skip=["all"], report=told.append) == {"A Mark": {10}}
    assert told == ["section Marker 2 is shared by A Mark, B Mark: ignored"]


def test_marker_groups_give_a_marker_all_their_own_sections():
    class TwoSections(Classroom):
        def get_enrollments(self, type=None, state=None):
            return [enrol(1, "Mark, A", "TaEnrollment", 2, False),
                    enrol(1, "Mark, A", "TaEnrollment", 3, False)]
    assert marker_groups(TwoSections(), skip=["all"]) == {"A Mark": {10, 11, 20}}


def test_marker_groups_unknown_skip_is_an_error():
    with pytest.raises(ValueError, match="no such section: nope"):
        marker_groups(Classroom(), skip=["nope"])
