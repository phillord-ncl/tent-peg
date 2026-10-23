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


def marker_groups(course, skip=()):
    """Map each marker's name (as Canvas sorts it) to the set of student user ids
    in the sections they are enrolled in, restricted or not. ``skip`` names
    sections (by id or exact name, ignoring case) to leave out, such as the
    one holding the whole class; a marker with no other section is dropped."""
    skip = {str(x).strip().lower() for x in skip}
    sections = {s.id: s for s in course.get_sections(include=["students"])}
    unknown = skip - {str(i) for i in sections} - {s.name.lower() for s in sections.values()}
    if unknown:
        raise ValueError("no such section: {}".format(", ".join(sorted(unknown))))
    members = {
        i: {st["id"] for st in (s.students or [])}
        for i, s in sections.items()
        if str(i) not in skip and s.name.lower() not in skip
    }
    groups = {}
    for m in course_markers(course):
        mine = [members[i] for i in m["sections"] if i in members]
        if mine:
            groups.setdefault(m["name"], set()).update(*mine)
    return groups
