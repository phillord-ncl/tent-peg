"""Who the markers of a course are, and which students Canvas gives them."""

import click


def warn(msg):
    click.echo("warning: " + msg, err=True)


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
            "full_name": user.get("name") or user.get("sortable_name", "?"),
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


def marker_groups(course, skip=(), report=warn):
    """Map each marker's full name, forename first, to the set of student user ids
    in the sections that are theirs alone: a section counts only when exactly
    one marker is enrolled in it, so a class-wide section shared by many markers
    says nothing and is ignored. ``skip`` names further sections (by id or exact
    name, ignoring case) to leave out. A marker with no section of their own is
    dropped. ``report`` (default: a warning on stderr) is told of each shared section holding under half the
    students, which is probably a mistake."""
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
    class_wide = {st["id"] for sec in sections.values() for st in (sec.students or [])}
    markers = course_markers(course)
    owners = {}
    for m in markers:
        for i in m["sections"]:
            if i in members:
                owners.setdefault(i, []).append(m["full_name"])
    for i, names in sorted(owners.items()):
        if len(names) > 1 and 2 * len(members[i]) < len(class_wide):
            report("section {} is shared by {}: ignored".format(
                sections[i].name, ", ".join(sorted(names))))
    groups = {}
    for i, names in owners.items():
        if len(names) == 1:
            groups.setdefault(names[0], set()).update(members[i])
    return groups
