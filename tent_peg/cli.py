import os

import click
from tent_pole import config as tp_config
from tent_pole.course import course_by_exact

from tent_pole.rubric import load_rubric_toml

from .push import PushError, live_criteria, push_grade, push_submission, read_results
from .markers import course_markers, student_names
from .download import (
    LAYOUTS,
    DownloadError,
    download_assignment,
    find_assignment,
    my_section_ids,
)


def find_course(canvas):
    identifier = tp_config.config_course()
    if not identifier:
        raise click.ClickException("no course configured")
    course = course_by_exact(identifier, canvas)
    if course is None:
        raise click.ClickException("no course matching {!r}".format(identifier))
    return course


def peg_setting(key, given=None):
    """``given`` if set, else ``[peg] key`` from tent-pole.toml, else None."""
    return given if given is not None else tp_config.get_maybe(tp_config.CONFIG, "peg/" + key)


def need_assignment(given):
    found = peg_setting("assignment", given)
    if not found:
        raise click.UsageError(
            "no assignment: name it, or set [peg] assignment in tent-pole.toml")
    return found


@click.group()
@click.option("-c", "--course", "course_id", help="Course id, code or name.")
@click.option("--beta", is_flag=True, help="Use the [dev] test instance and course.")
def main(course_id, beta):
    if beta:
        os.environ["TENT_POLE_USE_TEST_CONFIG"] = "1"
    if course_id:
        tp_config.CONFIG.setdefault("course", {})["identifier"] = course_id
        tp_config.CONFIG["course"].pop("id", None)
        if beta:
            tp_config.CONFIG.setdefault("dev", {})["test_course_id"] = course_id


@main.command()
def assignments():
    """List the course's assignments with their ids and section/submission counts."""
    course = find_course(tp_config.config_canvas())
    click.echo("{} ({})".format(course.name, course.id))
    for a in course.get_assignments():
        click.echo("{}\t{}\t{} submitted".format(
            a.id, a.name, getattr(a, "needs_grading_count", "?")))


@main.command()
def sections():
    """List the course's sections with student counts."""
    course = find_course(tp_config.config_canvas())
    for s in course.get_sections(include=["total_students"]):
        click.echo("{}\t{}\t{} students".format(
            s.id, s.name, getattr(s, "total_students", "?")))


@main.command()
@click.argument("assignment", required=False)
@click.option("--out", default=None, type=click.Path(file_okay=False),
              help="Directory to write one directory per student into "
                   "(default: [peg] marking in tent-pole.toml, else here).")
@click.option("--section", "sections", type=int, multiple=True,
              help="Students in this section id instead of your own (repeatable).")
@click.option("--all", "everyone", is_flag=True,
              help="Every student, for when you are in no section.")
@click.option("--layout", type=click.Choice(sorted(LAYOUTS)), default=None,
              help="Name directories by email or by NCL login id (default: email, login for anonymous assignments).")
@click.option("--force", is_flag=True, help="Rewrite students already downloaded.")
def download(assignment, out, sections, everyone, layout, force):
    """Download the submissions to ASSIGNMENT (id or name) in the configured
    course, for the students in your sections only (or in --section, or
    everyone with --all)."""
    assignment = need_assignment(assignment)
    out = peg_setting("marking", out) or "."
    canvas = tp_config.config_canvas()
    course = find_course(canvas)
    if everyone and sections:
        raise click.UsageError("--all and --section do not go together")
    if sections:
        section_ids = set(sections)
    elif everyone:
        section_ids = None
    else:
        section_ids = my_section_ids(course, canvas.get_current_user().id)
        if not section_ids:
            raise click.ClickException(
                "you are not enrolled in any section; name one with --section, or use --all")
    try:
        assignment = find_assignment(course, assignment)
        made = download_assignment(
            course, assignment, out, section_ids, layout, force, click.echo
        )
    except DownloadError as e:
        raise click.ClickException(str(e))
    click.echo("{} submissions written to {}".format(len(made), out))


@main.command()
@click.option("--students/--no-students", default=True,
              help="List each restricted marker's students.")
def markers(students):
    """List the course's markers and, where Canvas restricts them to
    sections, the students they have been given."""
    course = find_course(tp_config.config_canvas())
    found = course_markers(course)
    names = student_names(course) if students else {}
    for m in found:
        click.echo("{} ({}) -- {}".format(
            m["name"], m["login_id"], ", ".join(sorted(m["roles"]))))
        click.echo("    sections: {}".format(
            ", ".join(m["sections"].values()) or "none"))
        if m["students"] is None:
            click.echo("    not section-restricted: Canvas lets them see everyone")
        else:
            click.echo("    restricted to their sections: {} students".format(
                len(m["students"])))
            if students:
                for sid in sorted(m["students"], key=lambda i: names.get(i, "")):
                    click.echo("        {}".format(names.get(sid, sid)))


@main.group()
def marks():
    """Work with the marks arbiter recorded."""


def _submission_dirs(root):
    """``root`` itself if it holds a canvas.toml, else its subdirectories that do."""
    if os.path.exists(os.path.join(root, "canvas.toml")):
        return [root]
    return sorted(
        os.path.join(root, d) for d in os.listdir(root)
        if os.path.exists(os.path.join(root, d, "canvas.toml")))


@marks.command()
@click.argument("assignment", required=False)
@click.argument("directory", type=click.Path(exists=True, file_okay=False), required=False)
@click.option("--rubric", "rubric_path", type=click.Path(exists=True, dir_okay=False),
              help="The .rubric.toml arbiter marked against (default: the one "
                   "named in the first arb-results.toml).")
@click.option("--dry-run", is_flag=True, help="Say what would be pushed; write nothing to Canvas.")
@click.option("--force", is_flag=True,
              help="Overwrite marks Canvas holds that this tool did not push.")
def push(assignment, directory, rubric_path, dry_run, force):
    """Push arbiter's marks for ASSIGNMENT to Canvas.

    With a rubric on the assignment they go in as rubric assessments. With
    none, the total goes in as the grade (scaled to the assignment's points)
    and each arb-feedback.txt, if present, as a comment.

    DIRECTORY is one submission, or a directory of them (default: [peg]
    marking in tent-pole.toml, else here)."""
    assignment = need_assignment(assignment)
    directory = peg_setting("marking", directory) or "."
    if not os.path.isdir(directory):
        raise click.ClickException("no such directory: {}".format(directory))
    dirs = _submission_dirs(directory)
    if not dirs:
        raise click.ClickException("no submissions (canvas.toml) under {}".format(directory))
    course = find_course(tp_config.config_canvas())
    try:
        assignment = find_assignment(course, assignment)
        if not getattr(assignment, "rubric", None):
            criteria = None
        else:
            criteria = live_criteria(assignment)
        if criteria is None:
            rubric_toml = None
        elif rubric_path is None:
            for d in dirs:
                try:
                    rubric_path = read_results(d).get("rubric")
                except PushError:
                    continue
                break
        if criteria is not None:
            if not rubric_path or not os.path.exists(rubric_path):
                raise click.ClickException(
                    "cannot find the .rubric.toml; name it with --rubric")
            rubric_toml = load_rubric_toml(rubric_path)
    except (DownloadError, PushError) as e:
        raise click.ClickException(str(e))
    failed = 0
    for d in dirs:
        name = os.path.basename(os.path.normpath(d))
        try:
            if criteria is None:
                outcome = push_grade(d, assignment, force, dry_run)
            else:
                outcome = push_submission(d, assignment, rubric_toml, criteria, force, dry_run)
            click.echo("{}: {}".format(name, outcome))
        except PushError as e:
            failed += 1
            click.echo("{}: skipped, {}".format(name, e))
    if failed:
        raise click.ClickException("{} of {} not pushed".format(failed, len(dirs)))
