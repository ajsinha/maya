# MAYA quick start

From nothing to MAYA running on your machine, signed in, with real demonstration data to
look at and a feature of your own — in about fifteen minutes. Every step says **what to
type**, **what you should see**, and **what to do if you don't**. Nothing is assumed.

If you only want the three commands, they are at the very end, in
[the short version](#the-short-version). If anything goes wrong, jump to
[troubleshooting](#troubleshooting).

---

## What you need

| | Requirement | How to check |
|---|---|---|
| Computer | **Linux** (Ubuntu 22.04 or later, Debian 12, Fedora 39 or similar). MAYA is built and tested on Linux only; Windows and macOS are not supported yet. | `uname -s` prints `Linux` |
| Python | **Exactly Python 3.13.** Not 3.12, not 3.14. | `python3.13 --version` prints `Python 3.13.x` |
| Git | Any recent version | `git --version` |
| Disk | About 1.5 GB free (1 GB of it is Python packages) | `df -h ~` |
| Network | To download the code and the Python packages, once | — |
| Browser | Any current Chrome, Firefox, Edge or Safari | — |

You do **not** need a database server, Docker, or administrator (root) rights: MAYA keeps
everything in one folder and uses SQLite unless you tell it otherwise.

### If you do not have Python 3.13

Check first — many systems have it under a different name:

```bash
python3.13 --version        # the name this guide uses
python3 --version           # if this says 3.13.x, use python3 instead of python3.13 below
```

If neither shows 3.13, install it one of these ways, then open a **new** terminal:

- **Any Linux, no root needed (recommended):** install `uv`, then let it fetch Python:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  uv python install 3.13
  ```
  After this, `python3.13` is in `~/.local/bin` and `python3.13 --version` works.
- **Ubuntu, with root:** `sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.13 python3.13-venv`
- **Fedora, with root:** `sudo dnf install python3.13`

---

## Step 1 — Get the code

Open a terminal. Go to the folder where you keep projects (any folder is fine) and clone:

```bash
cd ~
git clone https://github.com/ajsinha/maya.git
cd maya
```

**You should see** `Cloning into 'maya'...` and then be inside the new `maya` folder.
`ls` shows `README.md`, `run_maya_web.py`, `config`, `maya`, `case_studies` and more.

> **Everything from here on is typed inside this `maya` folder.** If a command says
> "No such file or directory", run `cd ~/maya` first.

## Step 2 — Create a private Python environment

This keeps MAYA's packages separate from everything else on your computer.

```bash
python3.13 -m venv .venv
```

**You should see** nothing at all — that is success. A hidden folder `.venv` now exists
(`ls -a` shows it).

**If you see** `No module named venv` or `ensurepip is not available`: install the venv
module (`sudo apt install python3.13-venv` on Ubuntu), or use the `uv` route above, which
includes it.

## Step 3 — Install MAYA's packages

```bash
.venv/bin/pip install -e ./sdk -r requirements.txt -r requirements-dev.txt
```

This downloads about forty packages. It takes between thirty seconds and a few minutes,
depending on your connection.

**You should see** many `Collecting …` and `Downloading …` lines, ending with
`Successfully installed …` and no line starting with `ERROR`.

**If you see** `ERROR: … requires a different Python`, the environment was made with the
wrong Python: delete it (`rm -rf .venv`) and repeat step 2 with Python 3.13.

> Always start MAYA's tools with `.venv/bin/python` (or activate the environment with
> `source .venv/bin/activate`, after which `python` means the right one). Plain `python`
> may be a different Python that has none of MAYA's packages.

## Step 4 — Start MAYA

```bash
.venv/bin/python run_maya_web.py
```

**You should see**, after a few seconds, MAYA's banner and a short report, ending like this
(paths, dates and numbers differ):

```text
     ██║ ╚═╝ ██║██║  ██║   ██║   ██║  ██║     Version 1.0.0  ·  Build 2026-09-26
  Environment   dev
  Database      sqlite  (schema/sqlite.sql)
  Sandbox tier  strong  — verified by a probe child: …
  Storage root  /home/you/maya/data

  !! The bootstrap admin still uses the default password 'maya-dev-admin'. Change it now.
================================================================================

  Serving on http://127.0.0.1:8600   (API docs: /api/v1/docs)
```

The warning about the password is expected on a new install; you will change it in the
next step. Lines mentioning `duckdb` or another package marked with `*` are also normal: an
optional accelerator is not installed and MAYA says what it uses instead. If `Sandbox tier`
says `minimal` rather than `strong`, MAYA still works; see
[troubleshooting](#troubleshooting).

**Leave this terminal open.** MAYA runs for as long as it stays open. To stop it later,
click in it and press **Ctrl+C**.

The first start creates a folder called `data/` inside `maya/`. Everything MAYA stores —
its database, the data you upload, its keys and logs — lives there, and nowhere else.

**If you see** `address already in use`: something else is using port 8600. Start MAYA on
another port instead, and use that number in the browser:
`.venv/bin/python run_maya_web.py --server.port=8700`.

## Step 5 — Open MAYA and sign in

1. Open your browser at **<http://127.0.0.1:8600>**.
2. You see MAYA's landing page. Click **Sign in** (top right).
3. Enter username **`admin`** and password **`maya-dev-admin`**, and click **Sign in**.
4. Change this published password from the menu under your name, **Change password**. MAYA insists on the
   change at sign-in only when `auth.password.force_change` is `true`. A new password must be
   **at least 8 characters** and use **two of**: lower-case letters, upper-case letters,
   digits, symbols — for example `admin123`. Both limits are settings
   (`auth.password.min_length`, `auth.password.require_classes`).
5. You arrive on the **dashboard**. You are signed in as the administrator.

**Write the new password down.** On a fresh install there is only one administrator, and
MAYA has no "forgot password" link: see [troubleshooting](#troubleshooting) if you lose it.

**If the page does not load**: check the terminal from step 4 is still running and says
`Serving on http://127.0.0.1:8600`. Use exactly `127.0.0.1`, not your machine's
network name.

## Step 6 — Load demonstration data

An empty MAYA has nothing to look at. The quickest way to fill it is to run a **case study**:
a complete, realistic example that defines features, loads data, registers a model and
takes it through approval, exactly as people would.

Open a **second terminal** (leave the first one running MAYA), go to the folder, and run:

```bash
cd ~/maya
.venv/bin/python case_studies/01-retail-credit-pd-scorecard/run.py
```

**You should see** about ten seconds of narration: numbered steps, facts, and several lines
starting with `refused —`. Those refusals are the point: MAYA stopping people doing what
they may not do (a designer approving her own work, a model trained on data from the
future). It ends with `seven steps done in …s`.

Now go back to the browser and **reload the page** (F5). The case study created a
namespace called `retail_credit` and several users. Look around:

| Click | What you see |
|---|---|
| **Catalog → Faceted catalog** | The three features the study defined, and its feature set |
| a feature's name | Its definition, versions, the data it holds, and its approval history |
| **Models → All models** | The PD scorecard, its mathematics rendered from the formula, and its specification |
| **Warrants → All warrants** | The training warrant and its **leakage certificate** — open it and read why it refused |
| **Catalog → Lineage** | The whole chain from data to live model, as a graph |
| **Models → Findings & reviews** | The governance view of every model |

The case study's people can sign in too, each with the password **`Maya-testing-pass-1`**:
`dana` (feature designer), `mick` (feature manager), `mona` (model designer), `devi` (model
developer), `mgr` (model manager). Sign out (top right) and sign in as `dana` to see the
same screens with fewer rights.

More case studies — option pricing, IFRS 9, mortgages, yield curves and others — are listed
in [`case_studies/README.md`](../../case_studies/README.md). Run any of them the same way;
they all go into the same MAYA, each in its own namespace.

## Step 7 — Create your first feature from a file

MAYA comes with a tiny file of prices to try, at `docs/getting-started/prices.csv`:

```text
date,symbol,close
2026-01-02,AAA,101.50
2026-01-02,BBB,48.20
…
```

1. Sign in as `admin` (with your new password) if you are not already.
2. Click **Workbench → Quick feature**.
3. **Feature name:** type `prices`.
4. **File:** click *Browse* and choose `docs/getting-started/prices.csv` inside your `maya` folder.
5. **Format:** leave it as `csv`. Click **Create**.

**You should see** the new feature's page, in your personal `scratch.admin` namespace, with
its columns worked out from the file (`date`, `symbol`, `close`) and eight rows. It is
marked *ungoverned*: a quick feature skips review so you can try things. To make a governed
one, use **Workbench → Feature designer**, where it goes through submission and approval.

## Step 8 — Talk to MAYA from a program (optional)

Everything in the web UI is also a REST API. With MAYA still running, in the second
terminal (use the password you chose in step 5):

```bash
curl -s http://127.0.0.1:8600/healthz; echo
TOKEN=$(curl -s -X POST http://127.0.0.1:8600/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "Maya-first-2026"}' | python3 -c 'import sys, json; print(json.load(sys.stdin)["token"])')
curl -s "http://127.0.0.1:8600/api/v1/features?namespace=retail_credit" -H "Authorization: Bearer $TOKEN" | head -c 300; echo
```

**You should see** `{"alive":true,"version":"1.0.0"}` and then the start of a JSON list of
the case study's features. The [API guide](../reference/API_GUIDE.md) takes it from here, and the
interactive reference is at <http://127.0.0.1:8600/api/v1/docs>.

## Step 9 — Stop, restart, start over

| To | Do |
|---|---|
| **Stop MAYA** | Click in the terminal running it and press **Ctrl+C** |
| **Start it again** | `.venv/bin/python run_maya_web.py` — everything you did is still there (it is in `data/`) |
| **Start over from nothing** | Stop MAYA, then `rm -rf data` inside the `maya` folder, then start it again. This deletes **everything**: users, data, models. The admin password goes back to `maya-dev-admin` |
| **Update to a newer version** | Stop MAYA, `git pull`, `.venv/bin/pip install -e ./sdk -r requirements.txt -r requirements-dev.txt`, start it again |

---

## Troubleshooting

| What you see | Why | What to do |
|---|---|---|
| `python3.13: command not found` | Python 3.13 is not installed, or is under another name | See [If you do not have Python 3.13](#if-you-do-not-have-python-313) |
| `ERROR: Could not find a version that satisfies the requirement …` | The environment uses the wrong Python (often 3.12 or 3.14) | `rm -rf .venv`, then repeat steps 2 and 3 with `python3.13` |
| `ModuleNotFoundError: No module named 'fastapi'` (or any other) | You ran plain `python` instead of `.venv/bin/python` | Use `.venv/bin/python …`, or `source .venv/bin/activate` first |
| `address already in use` when starting | Port 8600 is taken — perhaps MAYA is already running in another terminal | Stop the other one, or add `--server.port=8700` and browse to that port |
| The browser says *This site can't be reached* | MAYA is not running, or you used a different address | Check the first terminal; use `http://127.0.0.1:8600` exactly |
| `Password must be at least 8 characters and use 2 of: …` | The new password is too simple | Make it longer, and mix upper and lower case with digits or symbols |
| `That password was used before` | MAYA remembers the last five passwords of each account | Choose a different one |
| *Account locked* after several wrong passwords | Five failures in fifteen minutes lock an account for thirty minutes | Wait thirty minutes, or have an administrator reset the password in **Admin → Users**, which also lifts the lock |
| Lost the only administrator's password | There is no recovery link, on purpose | On a scratch install: stop MAYA, `rm -rf data`, start again (this deletes everything). With another administrator: they set a new one in **Admin → Users** |
| A case study stops with `the 'retail_credit' namespace is already in this estate` | You ran the same study twice | Run it with `--reset`, which removes that study's namespace and runs it again (the other studies stay), or just look at what is already there |
| Warnings about `duckdb`, `uvloop` or other packages | Optional accelerators are not installed | Nothing: MAYA says what it uses instead and works without them |
| The **System health** page says the sandbox tier is `minimal` | The strong sandbox (bubblewrap) is not available on this machine | Fine for trying MAYA. For real use, install `bubblewrap` (`sudo apt install bubblewrap`) and restart |

Still stuck? The log is at `data/logs/maya.log`; the last lines usually say what went wrong.

---

## The short version

```bash
git clone https://github.com/ajsinha/maya.git && cd maya
python3.13 -m venv .venv && .venv/bin/pip install -e ./sdk -r requirements.txt -r requirements-dev.txt
.venv/bin/python run_maya_web.py      # then open http://127.0.0.1:8600 — admin / maya-dev-admin
```

## Where to go next

| To | Read |
|---|---|
| Understand what MAYA is for | [`README.md`](../../README.md) |
| Run and debug MAYA in PyCharm or IntelliJ IDEA | [IDE.md](IDE.md): interpreter, run configuration, debugging, tests |
| Learn the product step by step in the browser | *Help → Guides* inside MAYA: four tutorials, from a first feature to a governed change |
| See complete worked examples | [`case_studies/README.md`](../../case_studies/README.md) |
| Write a program that uses MAYA | [`API_GUIDE.md`](../reference/API_GUIDE.md) |
| Run it for real (PostgreSQL, single sign-on, backups) | *Help → Operations and monitoring* and [`runbooks/`](../operations/runbooks/README.md) |
