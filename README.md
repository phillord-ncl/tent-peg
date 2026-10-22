# tent-peg

Interact with the Canvas assignments of a course: download the submissions
you are marking, and see who the markers are. It is part of the tent family
with [tent-pole](https://github.com/phillord-ncl/tent-pole), which pushes
course content to Canvas, and [arbiter](https://github.com/phillord-ncl/arbiter),
which does the marking.

Canvas can hand a grader every submission, but not just the ones assigned to
them. tent-peg reads them through the API and keeps only the students in your
own Canvas sections, so a marker of 30 students downloads 30 students' work,
not 300.

## Install

Needs Python 3.12 or later.

    pipx install git+https://github.com/phillord-ncl/tent-peg.git

## Configure

tent-peg uses tent-pole's configuration, so it needs a Canvas API key. Get one
from Account, Settings, *New Access Token*
([how](https://community.canvaslms.com/docs/DOC-3013)), and put it in
`~/.config/tent-pole/tent-pole.toml`:

    [general]
    api_key = "put-your-api-key-in-here"
    api_url = "https://ncl.instructure.com"

The course comes from a `tent-pole.toml` in the current directory (or a
parent, up to the git root) with `[course] identifier = "..."`, or from
`-c`, which takes a course id, code or name. `--beta` uses the `[dev]`
test instance and course instead; see tent-pole's `docs/configure.md`.

## Commands

    tent-peg [-c COURSE] [--beta] COMMAND

`sections` lists the course's sections and how many students are in each.

`assignments` lists the assignments with their ids.

`markers` lists the course's TAs and teachers, whether Canvas restricts each
to their sections, and for those restricted, their students
(`--no-students` leaves the students out).

`download ASSIGNMENT --out DIR` downloads the submissions to an assignment,
given by id or by name (an exact name, else a name that matches only one
assignment). Options:

- `--section ID` (repeatable): students in these sections. The default is the
  sections you are enrolled in.
- `--all`: every student, for when you are in no section. It cannot be
  combined with `--section`.
- `--layout email|login`: how to name the student directories.
- `--force`: rewrite students already downloaded. Without it they are left
  alone, so you can run `download` again later for late submissions without
  touching marks you have already made.

`marks push ASSIGNMENT [DIR]` writes the marks arbiter recorded back to
Canvas. `DIR` is one submission, or a directory of them (default: here).
This is the only command that writes to Canvas. Options:

- `--dry-run`: say what would be pushed, and write nothing.
- `--force`: overwrite marks Canvas holds that this tool did not push.
- `--rubric FILE`: the `.rubric.toml` arbiter marked against (default: the
  one named in `arb-results.toml`).

If the assignment has a rubric, each criterion's score and feedback go in as
a rubric assessment. Criteria are matched by description, since Canvas
criterion ids change when a rubric is edited. If it has none, the total in
`arb-results.toml` goes in as the grade, scaled to the assignment's points,
and the student's `arb-feedback.txt`, if there is one, as a comment.

A push leaves `canvas-pushed.toml` in the student's directory. A later push
refuses to replace marks on Canvas that differ from it, so a mark entered by
another marker is not lost. Comments cannot be edited, so one is posted only
when its text has changed.

All the other commands only read from Canvas.

## What download writes

One directory per student, holding the files they uploaded and a
`canvas.toml`:

    marking/ann@newcastle.ac.uk/canvas.toml
    marking/ann@newcastle.ac.uk/project-1.zip

The directory is named by the student's university email address
(`--layout email`, the default), which is unique. `canvas.toml` records the
Canvas user and submission ids, name, login id, student number, attempt, when
it was submitted, whether it was late, the sections, and the files. A text
entry submission is saved as `submission.html`.

### Anonymous assignments

If the assignment is marked anonymously, the directories are named by the
student's login id instead (`--layout login`), and `canvas.toml` leaves out the
name, email and student number. A login id is easy to look up, so this hides
who a student is from a casual look, not from someone determined. You can still
ask for `--layout email`.

## Marking

tent-peg gets the work; arbiter marks it:

    tent-peg -c "CSC1034 (26/27)" download "Assignment/Assessment 1" --out marking
    arbiter unpack -r marking
    arbiter --arb CSC1034.arb.toml -r marking
    tent-peg -c "CSC1034 (26/27)" marks push "Assignment/Assessment 1" marking

## Development

    poetry install
    poetry run pytest

The tests use hand-written fakes for the Canvas objects, so they need no
network.
