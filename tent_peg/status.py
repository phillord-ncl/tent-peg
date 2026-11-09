"""Where marking has got to: what Canvas holds for each submission."""

from .download import DownloadError, UNASSIGNED, directory_name, student_fields

# Order matters: it is the order the columns are shown in.
STATES = ("marked", "regrade", "unmarked", "missing")


def classify(submission):
    """One of ``STATES`` for a Canvas submission.

    marked: graded (or excused) and the grade is for the current submission.
    regrade: graded, but the student has submitted again since.
    unmarked: submitted and waiting for a mark.
    missing: nothing submitted and no mark."""
    state = getattr(submission, "workflow_state", "")
    if getattr(submission, "excused", False) or state == "graded":
        if getattr(submission, "grade_matches_current_submission", True) is False:
            return "regrade"
        return "marked"
    if state == "unsubmitted":
        return "missing"
    return "unmarked"


def tally(submissions, wanted=None, groups=None):
    """Count submissions by state.

    ``wanted`` limits it to those user ids (None: everyone). With ``groups``
    (name to set of user ids) the result maps each name to its own tally, a
    student counting in every group that holds them and in ``unassigned``
    when none does; otherwise it maps ``None`` to the one tally.
    Each tally maps a state to a list of submissions."""
    result = {}
    for sub in submissions:
        if wanted is not None and sub.user_id not in wanted:
            continue
        if groups is None:
            names = [None]
        else:
            names = sorted(g for g in groups if sub.user_id in groups[g]) or [UNASSIGNED]
        for name in names:
            result.setdefault(name, {s: [] for s in STATES})[classify(sub)].append(sub)
    return result


def label(sub, people, layout):
    """A name for a student: their directory name, else their user id."""
    try:
        return directory_name(layout, student_fields(sub, people, layout))
    except DownloadError:
        return str(sub.user_id)


def format_tally(counts):
    """One line: 'marked 3/10, 5 unmarked, 1 regrade, 1 missing'."""
    total = sum(len(v) for v in counts.values())
    parts = ["marked {}/{}".format(len(counts["marked"]), total)]
    parts += ["{} {}".format(len(counts[s]), s) for s in STATES[1:] if counts[s]]
    return ", ".join(parts)
