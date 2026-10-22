"""Who the markers of a course are, and which students Canvas gives them."""


def course_markers(course):
    """One dict per staff member (TA or teacher): name, email-ish login,
    roles, whether Canvas restricts them to their sections, and those
    sections. ``students`` is the students in those sections, or None when
    the marker is not restricted (Canvas then gives them everybody)."""
    sections = {
        s.id: (s.name, {st["id"] for st in (s.students or [])})
        for s in course.get_sections(include=["students"])
    }
    people = {}
    for e in course.get_enrollments(type=["TaEnrollment", "TeacherEnrollment"],
                                    state=["active"]):
        user = getattr(e, "user", None) or {}
        m = people.setdefault(e.user_id, {
            "user_id": e.user_id,
            "name": user.get("sortable_name") or user.get("name", "?"),
            "login_id": user.get("login_id", ""),
            "roles": set(),
            "restricted": False,
            "sections": {},
        })
        m["roles"].add(e.type)
        if getattr(e, "limit_privileges_to_course_section", False):
            m["restricted"] = True
        if e.course_section_id in sections:
            m["sections"][e.course_section_id] = sections[e.course_section_id][0]
    for m in people.values():
        if m["restricted"]:
            m["students"] = set().union(
                *(sections[i][1] for i in m["sections"])) if m["sections"] else set()
        else:
            m["students"] = None
    return sorted(people.values(), key=lambda m: m["name"])


def student_names(course):
    return {u.id: u.sortable_name for u in
            course.get_users(enrollment_type=["student"])}
