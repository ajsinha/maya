# QA artifacts

Everything a tester needs, in the order they will want it.

| File | What it is |
|---|---|
| **[README.md](README.md)** | **The cheatsheet.** Start here. Eleven sections, every command verified against a live instance, with screenshots. |
| [qa-setup.sh](qa-setup.sh) | Builds the example estate the cheatsheet walks through. Run once, after starting the platform. |
| [screenshots/](screenshots/) | The 16 screens referenced by the cheatsheet, captured from a running instance. |

## The short version

```bash
# terminal 1 — the platform
.venv/bin/python run_maya_web.py

# terminal 2 — the example estate
./docs/QA/qa-setup.sh
```

Then open **http://localhost:5006** and sign in as `admin` / `maya-admin-dev`.

## One thing to know before you begin

MAYA refuses a great deal on purpose. A refusal has a code, a sentence saying
what happened, and a `remediation` saying what to do about it — and in almost
every case it is the platform working rather than failing.

The cheatsheet marks the refusals you should expect. What is worth reporting is
the opposite: a **success that does not correspond to anything** — a count that
says work happened when it did not, a "verified" that verified nothing, a
screen that offers a control and then refuses it.
