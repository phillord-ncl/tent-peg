"""Push the marks arbiter recorded for a submission to Canvas as a rubric
assessment.

Canvas criterion ids are not stable across a rubric edit, so they are
resolved from the live rubric on every push: arbiter's criterion id is
looked up in the local ``.rubric.toml`` for its description, and that
description picks the live Canvas criterion. Each push leaves
``canvas-pushed.toml`` in the submission directory; a later push refuses
to overwrite Canvas values that differ from it, so a mark another marker
has entered is never clobbered.
"""
import hashlib
import os
import tomllib

STAMP = "canvas-pushed.toml"
#: Written beside arb-results.toml by the course's own feedback script.
FEEDBACK = "arb-feedback.txt"


class PushError(Exception):
    pass


def _read(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def _toml_str(s):
    return '"{}"'.format(str(s).replace("\\", "\\\\").replace('"', '\\"'))


def read_results(directory):
    """arb-results.toml in ``directory``, or PushError if absent."""
    path = os.path.join(directory, "arb-results.toml")
    if not os.path.exists(path):
        raise PushError("no arb-results.toml (not marked yet)")
    return _read(path)


def wanted_marks(results, rubric_toml):
    """Map criterion description to {"points", "comments"} from arbiter's
    results, using ``rubric_toml`` (parsed .rubric.toml) to turn arbiter's
    criterion ids into descriptions."""
    if not results.get("complete"):
        raise PushError("marking is not complete")
    descriptions = {c["id"]: c["description"] for c in rubric_toml.get("criteria", [])}
    marks = {}
    for r in results.get("result", []):
        cid = r["criterion"]
        if cid not in descriptions:
            raise PushError("criterion {!r} is not in the rubric".format(cid))
        marks[descriptions[cid]] = {
            "points": r["score"],
            "comments": r.get("feedback", "") or "",
        }
    return marks


def live_criteria(assignment):
    """Map criterion description to Canvas criterion id for the rubric
    attached to ``assignment``; PushError if there is none or two
    criteria share a description."""
    criteria = getattr(assignment, "rubric", None) or []
    if not criteria:
        raise PushError("assignment has no rubric")
    found = {}
    for c in criteria:
        if c["description"] in found:
            raise PushError("rubric has two criteria described {!r}".format(c["description"]))
        found[c["description"]] = c["id"]
    return found


def _as_assessment(live):
    """Normalise Canvas's rubric_assessment to {id: (points, comments)}."""
    return {
        cid: (v.get("points"), v.get("comments") or "")
        for cid, v in (live or {}).items()
        if isinstance(v, dict)
    }


def plan_push(marks, criteria, live_assessment, stamp):
    """What to send, as (payload, conflicts, unchanged).

    ``payload`` maps Canvas criterion id to its new points and comments,
    and is empty when nothing needs writing. ``conflicts`` lists criteria
    where Canvas holds a value that is neither what we last pushed
    (``stamp``, description -> points/comments) nor what we are about to
    push. Criteria in the live assessment that we do not mark are carried
    over so the write cannot lose them."""
    missing = [d for d in marks if d not in criteria]
    if missing:
        raise PushError("no such criterion in the live rubric: {}".format(
            ", ".join(repr(m) for m in missing)))
    live = _as_assessment(live_assessment)
    payload, conflicts, changed = {}, [], False
    marked_ids = set()
    for desc, mark in marks.items():
        cid = criteria[desc]
        marked_ids.add(cid)
        new = (float(mark["points"]), mark["comments"])
        current = live.get(cid)
        if current is not None and current[0] is not None:
            current = (float(current[0]), current[1])
        if current == new:
            payload[cid] = {"points": new[0], "comments": new[1]}
            continue
        changed = True
        last = stamp.get(desc)
        if current is not None and current != (None, ""):
            if last is None or (float(last["points"]), last["comments"]) != current:
                conflicts.append(desc)
        payload[cid] = {"points": new[0], "comments": new[1]}
    for cid, (points, comments) in live.items():
        if cid not in marked_ids and points is not None:
            payload[cid] = {"points": points, "comments": comments}
    return (payload if changed else {}), conflicts, not changed


def read_stamp(directory):
    path = os.path.join(directory, STAMP)
    return _read(path).get("criterion", {}) if os.path.exists(path) else {}


def write_stamp(directory, marks):
    lines = []
    for desc, m in marks.items():
        lines += [
            "[criterion.{}]".format(_toml_str(desc)),
            "points = {}".format(float(m["points"])),
            "comments = {}".format(_toml_str(m["comments"])),
            "",
        ]
    with open(os.path.join(directory, STAMP), "w") as f:
        f.write("\n".join(lines))


def push_submission(directory, assignment, rubric_toml, criteria, force=False,
                    dry_run=False):
    """Push one submission directory. Returns "pushed", "unchanged" or
    "dry-run"; raises PushError when it must not (or cannot) write."""
    meta = _read(os.path.join(directory, "canvas.toml"))
    marks = wanted_marks(read_results(directory), rubric_toml)
    sub = assignment.get_submission(meta["user_id"], include=["rubric_assessment"])
    payload, conflicts, unchanged = plan_push(
        marks, criteria, getattr(sub, "rubric_assessment", None),
        read_stamp(directory))
    if conflicts and not force:
        raise PushError(
            "Canvas holds different marks for {} that we did not push "
            "(use --force to overwrite)".format(", ".join(conflicts)))
    if unchanged:
        write_stamp(directory, marks)
        return "unchanged"
    if dry_run:
        return "dry-run"
    sub.edit(rubric_assessment=payload)
    write_stamp(directory, marks)
    return "pushed"


## Assignments without a rubric: one grade and one comment per student.

def scaled_grade(results, points_possible):
    """The total in arb-results.toml as a mark out of ``points_possible``."""
    if not results.get("complete"):
        raise PushError("marking is not complete")
    return round(results["score"] / results["out_of"] * points_possible, 2)


def _digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def read_grade_stamp(directory):
    path = os.path.join(directory, STAMP)
    return _read(path).get("grade", {}) if os.path.exists(path) else {}


def write_grade_stamp(directory, grade, comment):
    with open(os.path.join(directory, STAMP), "w") as f:
        f.write("[grade]\npoints = {}\ncomment_sha = {}\n".format(
            float(grade), _toml_str(_digest(comment))))


def push_grade(directory, assignment, force=False, dry_run=False,
               feedback_name=FEEDBACK):
    """Push one submission's total as a grade, and its feedback file (if
    any) as a comment. Canvas comments only accumulate, so the comment is
    posted only when it differs from the one last pushed. Refuses to
    replace a Canvas grade this tool did not set. Returns "pushed",
    "unchanged" or "dry-run"."""
    meta = _read(os.path.join(directory, "canvas.toml"))
    grade = scaled_grade(read_results(directory), assignment.points_possible)
    path = os.path.join(directory, feedback_name)
    comment = open(path).read() if os.path.exists(path) else ""
    sub = assignment.get_submission(meta["user_id"])
    live = getattr(sub, "score", None)
    stamp = read_grade_stamp(directory)
    grade_changed = live is None or float(live) != grade
    comment_changed = bool(comment) and stamp.get("comment_sha") != _digest(comment)
    if not grade_changed and not comment_changed:
        write_grade_stamp(directory, grade, comment)
        return "unchanged"
    if grade_changed and live is not None and not force:
        if "points" not in stamp or float(stamp["points"]) != float(live):
            raise PushError(
                "Canvas already holds the grade {} that we did not push "
                "(use --force to overwrite)".format(live))
    if dry_run:
        return "dry-run"
    kwargs = {}
    if grade_changed:
        kwargs["submission"] = {"posted_grade": grade}
    if comment_changed:
        kwargs["comment"] = {"text_comment": comment}
    sub.edit(**kwargs)
    write_grade_stamp(directory, grade, comment)
    return "pushed"
