from types import SimpleNamespace as NS

from tent_peg.markers import course_markers


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
