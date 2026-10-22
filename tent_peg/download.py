"""Download the submissions to one Canvas assignment.

Canvas can hand a grader every submission or (with moderated grading) a
fixed share, but not "the ones assigned to me". So everything is read
through the API and a marker's share is picked out here, by section.
"""
import os
import re

#: Directory naming: the email is world unique; the login id (NCL username)
#: is readily de-identifiable but not immediately so, so it is used for
#: anonymous marking.
LAYOUTS = {"email": "{email}", "login": "{login_id}"}


class DownloadError(Exception):
    pass


def safe_name(text):
    """A string fit to be one path component: no separators, no leading dot."""
    text = re.sub(r"[\\/:*?\"<>|\s]+", "_", str(text)).strip("._")
    return text or "unnamed"


def course_students(course):
    """Map user id to the identity Canvas gives for the students of
    ``course``. The submission's own ``user`` is withheld on anonymous
    assignments, so this roster is the one reliable source. Fields Canvas
    does not reveal are empty."""
    people = {}
    for u in course.get_users(enrollment_type=["student"], include=["email"]):
        people[u.id] = {
            "user_id": u.id,
            "email": (getattr(u, "email", "") or "").strip().lower(),
            "login_id": safe_name(getattr(u, "login_id", "") or "").lower(),
            "sis_id": safe_name(getattr(u, "sis_user_id", "") or ""),
            "name": getattr(u, "name", "") or "",
        }
    return people


def student_fields(submission, people, layout):
    fields = people.get(submission.user_id)
    key = "login_id" if layout == "login" else "email"
    if not fields or not fields[key]:
        raise DownloadError(
            "no {} visible for user {}; cannot name their directory".format(
                key.replace("_", " "), submission.user_id
            )
        )
    return fields


def directory_name(layout, fields):
    return safe_name(LAYOUTS[layout].format(**fields))


def find_assignment(course, ident):
    """The assignment whose id is ``ident``, or else whose name is exactly
    ``ident`` (ignoring case), or else the only one whose name contains it."""
    ident = str(ident).strip()
    if ident.isdigit():
        return course.get_assignment(int(ident))
    assignments = list(course.get_assignments())
    for matches in (
        [a for a in assignments if a.name == ident],
        [a for a in assignments if a.name.lower() == ident.lower()],
        [a for a in assignments if ident.lower() in a.name.lower()],
    ):
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise DownloadError("{!r} matches {} assignments: {}".format(
                ident, len(matches),
                ", ".join("{} ({})".format(a.name, a.id) for a in matches)))
    raise DownloadError("no assignment matching {!r}".format(ident))


def my_section_ids(course, user_id):
    """The sections in which ``user_id`` is enrolled in ``course``."""
    return {e.course_section_id for e in course.get_enrollments(user_id=user_id)}


def section_members(course, section_ids):
    """Map each wanted section id to the set of student user ids in it,
    plus a name for each."""
    members, names = {}, {}
    for section in course.get_sections(include=["students"]):
        if section.id in section_ids:
            members[section.id] = {s["id"] for s in (section.students or [])}
            names[section.id] = section.name
    missing = set(section_ids) - set(members)
    if missing:
        raise DownloadError(
            "no such section: {}".format(", ".join(str(m) for m in sorted(missing)))
        )
    return members, names


def _toml_str(s):
    return '"{}"'.format(str(s).replace("\\", "\\\\").replace('"', '\\"'))


def write_canvas_toml(directory, submission, fields, files, sections, anonymous):
    """canvas.toml: what Canvas said about this submission. user_id,
    submission_ids, late and files are the keys ``arbiter`` already knows.
    Anonymous marking leaves out name, email and student number."""
    lines = ["user_id = {}".format(fields["user_id"])]
    if not anonymous:
        lines += [
            "name = {}".format(_toml_str(fields["name"])),
            "email = {}".format(_toml_str(fields["email"])),
            "sis_id = {}".format(_toml_str(fields["sis_id"])),
        ]
    lines += [
        "login_id = {}".format(_toml_str(fields["login_id"])),
        "anonymous = {}".format("true" if anonymous else "false"),
        "submission_ids = [{}]".format(submission.id),
        "attempt = {}".format(getattr(submission, "attempt", None) or 0),
        "submitted_at = {}".format(_toml_str(getattr(submission, "submitted_at", "") or "")),
        "late = {}".format("true" if getattr(submission, "late", False) else "false"),
        "sections = [{}]".format(", ".join(_toml_str(x) for x in sections)),
        "files = [{}]".format(", ".join(_toml_str(f) for f in files)),
    ]
    with open(os.path.join(directory, "canvas.toml"), "w") as f:
        f.write("\n".join(lines) + "\n")


def download_assignment(
    course,
    assignment,
    out,
    section_ids=None,
    layout=None,
    force=False,
    report=lambda msg: None,
):
    """Write each submission to ``assignment`` into a directory under ``out``.

    ``layout`` is "email" or "login" (default: email, or login when the
    assignment is anonymous). ``section_ids`` limits it to students in those sections (None: everyone).
    A student whose directory already holds a canvas.toml is left alone unless
    ``force``, so an interrupted run can be repeated, and a marker's results
    are not overwritten. Returns the directories written."""
    anonymous = bool(getattr(assignment, "anonymous_grading", False))
    if layout is None:
        layout = "login" if anonymous else "email"
    if layout not in LAYOUTS:
        raise DownloadError("unknown layout {!r}; use one of {}".format(
            layout, ", ".join(LAYOUTS)))
    wanted = None
    section_names = {}
    if section_ids is not None:
        members, section_names = section_members(course, section_ids)
        wanted = set().union(*members.values()) if members else set()
    student_sections = {}
    for section in course.get_sections(include=["students"]):
        for s in section.students or []:
            student_sections.setdefault(s["id"], []).append(section.name)
    people = course_students(course)

    made, seen = [], {}
    for sub in assignment.get_submissions(include=["user"]):
        if wanted is not None and sub.user_id not in wanted:
            continue
        if getattr(sub, "workflow_state", "") == "unsubmitted":
            continue
        fields = student_fields(sub, people, layout)
        name = directory_name(layout, fields)
        if name in seen and seen[name] != sub.user_id:
            raise DownloadError(
                "students {} and {} both map to directory {}; use the other layout".format(
                    seen[name], sub.user_id, name
                )
            )
        seen[name] = sub.user_id
        directory = os.path.join(out, name)
        if os.path.exists(os.path.join(directory, "canvas.toml")) and not force:
            report("{}: exists, left alone".format(name))
            continue
        os.makedirs(directory, exist_ok=True)
        files = []
        for attachment in getattr(sub, "attachments", None) or []:
            filename = safe_name(attachment.display_name)
            attachment.download(os.path.join(directory, filename))
            files.append(filename)
        body = getattr(sub, "body", None)
        if body and getattr(sub, "submission_type", "") == "online_text_entry":
            with open(os.path.join(directory, "submission.html"), "w") as f:
                f.write(body)
            files.append("submission.html")
        write_canvas_toml(
            directory, sub, fields, files, student_sections.get(sub.user_id, []), anonymous
        )
        report("{}: {} file{}".format(name, len(files), "" if len(files) == 1 else "s"))
        made.append(directory)
    return made
