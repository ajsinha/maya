# QA artifacts

Everything a tester needs, in the order they will want it.

| File | What it is |
|---|---|
| **[README.md](README.md)** | **The cheatsheet.** Start here. Twelve sections, every command verified against a live instance, with screenshots. |
| **[qa_setup.py](qa_setup.py)** | **Builds the example estate**, on any platform. Written with MAYA's own SDK, so it doubles as a worked example of the client a bank would build against. Idempotent: run it twice and it says what already exists rather than making a second copy. |
| [qa-setup.sh](qa-setup.sh) | The same estate in bash and curl, for anybody already scripted around it. Needs both, so it does not run on Windows. |
| [screenshots/](screenshots/) | The 18 screens referenced by the cheatsheet, captured from a running instance. |

## The short version

```bash
# terminal 1 — the platform
.venv/bin/python run_maya_web.py          # macOS / Linux
.venv\Scripts\python run_maya_web.py       # Windows

# terminal 2 — the example estate
python docs/QA/qa_setup.py
```

Every command in the cheatsheet is given twice: once as `curl`, once as
Python using the SDK. On Windows use the Python one.

Then open **http://localhost:5006** and sign in as `admin` / `maya-admin-dev`.

If start-up refuses with **SCHEMA DRIFT**, the database predates the schema the
code ships. Close it in one step rather than deleting the database:

```bash
.venv/bin/python run_maya_web.py --check-schema     # what is missing
.venv/bin/python run_maya_web.py --repair-schema    # add exactly that
```

## Leave the log open in a second tab

**Admin → Live log** (`/admin/logs`) shows what the server is doing as it does
it. Every response carries a request id and every line written while serving it
carries the same one, so clicking an id in the log gives you one call end to
end. Attaching the saved file to a defect report is worth more than a
description of it. [Section 12](README.md#12-watching-what-the-server-does--the-live-log)
has the details.

## One thing to know before you begin

MAYA refuses a great deal on purpose. A refusal has a code, a sentence saying
what happened, and a `remediation` saying what to do about it — and in almost
every case it is the platform working rather than failing.

The cheatsheet marks the refusals you should expect. What is worth reporting is
the opposite: a **success that does not correspond to anything** — a count that
says work happened when it did not, a "verified" that verified nothing, a
screen that offers a control and then refuses it.
