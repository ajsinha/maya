# Suspected sandbox escape

For the administrator or `techops` engineer who has reason to think user-supplied Python got out
of its jail. MAYA runs three kinds of untrusted code — a model's code artifact through the
six-rung validation ladder, a `python` feature source on every pull, and a conformance or smoke
run — each in a separate capped child process (§17.2). "Escape" means that child did something
outside what its tier allows: reached the network, read or wrote outside its own temporary
directory, survived its limits, or influenced the parent beyond returning a value.

Treat a suspicion as credible until measured. Everything below is measurement, because the honest
position is this: MAYA's sandbox is tested against a fixed list of attacks
(`tests/test_sandbox_linux.py`), and a fixed list is not a proof.

## Symptoms

Any of these is enough to open this runbook:

- The tier fell, or is not what the deployment requires. `/admin/health` and `/metrics`:

  ```text
  maya_sandbox_tier{tier="minimal"} 1
  ```

  The `MayaSandboxTierDegraded` alert fires on anything but `strong`
  ([the rules file](../../../config/prometheus/maya-slo.rules.yml)).
- A validation report or conformance run that should have been refused passed, or a sandboxed
  run returned something it could not have computed from its inputs.
- Network activity, files, processes or cgroups on the host attributable to a `maya-sbx-*`
  temporary directory or a `sandbox_runner.py` child.
- MAYA's own files changed without a MAYA action behind them: `config/application.yaml`,
  anything under `storage.root`, `keys/`.
- A model artifact upload whose source contains an escape attempt — worth this runbook even if
  the ladder refused it, because it tells you somebody is trying.

## Diagnosis

**1. Establish what tier this host actually delivers.** It is measured by a probe child that
tries to escape, not assumed from the platform:

```bash
python -c "import json; from maya.security.sandbox import sandbox_tier; print(json.dumps(sandbox_tier(), indent=2))"
```

On a Linux host with everything present:

```json
{
  "tier": "strong",
  "mechanism": "bubblewrap namespaces (user, pid, net, mount, ipc, uts) with a read-only minimal root + seccomp-bpf deny-list + cgroup v2 scope (memory, CPU, tasks) + setrlimit",
  "reason": "verified by a probe child: separate uid, no network, read-only root without the home directory or MAYA's storage, seccomp filter active, cgroup caps"
}
```

`moderate` (macOS `sandbox-exec`) and `minimal` (Windows: wall-clock kill only, network blocking
best-effort) are much weaker. If the tier is not what you expected, the primitive that went
missing — `bwrap`, seccomp, cgroup v2 — is the incident, and the "escape" may simply be code
doing what a weaker tier permits.

**2. Re-run the escape battery on this host.** It is the fastest way to tell "the jail is open"
from "the jail is fine and something else happened":

```bash
python -m pytest tests/test_sandbox_linux.py tests/test_sandbox.py -q
# 23 passed
```

Those cover a raw socket bypassing the `socket` module, reading MAYA's configuration, reading
the user's shell profile, writing to `/etc`, `execv` of another program, `ptrace`, a memory
bomb, an infinite loop, and the import allowlist.

**3. Run the specific thing you suspect.** A one-off probe, with the same entry point MAYA uses:

```python
import json
from maya.security import sandbox

out = sandbox.run_sandboxed(
    "import os\ndef run(X, params):\n    import _socket\n    _socket.socket()\n    return 'escaped'",
    "run",
    {"X": {}, "params": {}},
    preload=(),
)
print(json.dumps(out, indent=1))
```

On a `strong` host that answers:

```json
{"ok": false, "result": null, "error": "PermissionError: [Errno 1] Operation not permitted",
 "tier": "strong", "duration": 0.12,
 "limits_applied": ["RLIMIT_CPU", "RLIMIT_AS", "RLIMIT_FSIZE", "RLIMIT_CORE", "seccomp"]}
```

Two more, verified the same way: reading `config/application.yaml` answers
`FileNotFoundError: [Errno 2] No such file or directory` — the file is not in the jail's root at
all — and writing to `/etc` answers `OSError: [Errno 30] Read-only file system`. A
`"result": "escaped"` from any of them is the escape, and `limits_applied` missing `seccomp` says
the filter never loaded.

**4. Find every untrusted run in the window.** The audit log names them:

```bash
curl -s "$MAYA_URL/api/v1/audit?action=model.artifact_validated" -H "Authorization: Bearer $MAYA_API_KEY"
# detail: {"passed": …, "tier": "strong"}  — the tier each validation actually ran under
```

A validation whose `detail.tier` is weaker than this host reports now ran under a weaker jail;
those are the runs to look at first. Then the code itself:

```bash
# Every model version with an artifact, newest first, with its report
curl -s "$MAYA_URL/api/v1/models?namespace=<ns>" -H "Authorization: Bearer $MAYA_API_KEY"
# Fetch the artifact blob by its hash and read it
curl -s "$MAYA_URL/api/v1/blobs/<artifact_hash>" -H "Authorization: Bearer $MAYA_API_KEY"
```

`python` feature sources are in the feature definition (`source.type: python`), reachable through
the catalog; they run on every pull, so they are the ones with the most attempts at bat.

**5. Look for what a successful escape would leave.** On the host:

```bash
ls -la /tmp/maya-sbx-* 2>/dev/null          # a jail that outlived its run
ps -ef | grep '[s]andbox_runner.py'         # a child that outlived its parent
ss -tanp | grep -i python                   # connections from a process that should have no network
find "$MAYA_HOME" -newermt '-24 hours' -not -path '*/lake/*' -not -path '*/logs/*'
```

## Steps

1. **Stop running untrusted code.** There is no switch for this, so use the two that exist:

   ```bash
   # Refuse to start, and refuse to run, below the strong tier
   python run_maya_web.py --sandbox.min_tier=strong
   ```

   Outside `dev` MAYA then refuses to start at all if the host cannot deliver it:

   ```text
   maya.core.errors.CapabilityRefused: Sandbox tier is '<tier>' but sandbox.min_tier is
   'strong' in a <env> environment: <the probe's reason>
   ```

   Until the host is fixed, stop the worker processes (`--worker`) and the primary's job
   workers: artifact validation is a job, so a queue with nothing draining it runs no untrusted
   code. `--jobs.workers=0` on the web process does that while leaving the UI up.

2. **Preserve the evidence before restarting anything.** Copy, do not move:
   - the artifact blobs and `python` source definitions involved;
   - the audit log region around the window (`GET /api/v1/audit`, exported as JSON);
   - the surviving `/tmp/maya-sbx-*` directories;
   - the host's own logs — `dmesg`, the seccomp and audit subsystems, the cgroup tree.

   The audit log is hash-chained, so verify it now, while you still can distinguish a break from
   a later one:

   ```bash
   python -m maya.cli admin verify-integrity
   # <n> pin(s) checked; drift: 0; audit chain ok: True
   curl -s "$MAYA_URL/api/v1/custody/verify" -H "Authorization: Bearer $MAYA_API_KEY"
   # {"ok":true, …, "verdict":"chain and anchors agree"}
   ```

   Custody, not the chain alone, is the one that catches a consistent rewrite — see
   [audit chain and custody](audit-chain-and-custody.md).

3. **Establish what the code could have reached** — which is the real question, and it is about
   the host, not MAYA. A `strong` jail has no network, a read-only minimal root without
   `storage.root` or the home directory, a separate uid, and its own pid/ipc/uts namespaces. If
   the tier was `strong` and the battery in step 2 passes, the reachable set is that jail's
   temporary directory and the payload it was given. If the tier was weaker, assume the process's
   own uid: everything MAYA can read, including `config/application.local.yaml`, `keys/` and the
   database.

4. **If the jail was open, rotate what it could have read.** In tier order:
   - **`keys/`**: the signing key, the sealing key (`secretbox.key`), the dev session secret.
     Rotating the sealing key invalidates every sealed secret — TOTP enrolments and webhook
     signing secrets — so plan the re-enrolment.
   - **`app.secret_key`**: every session is forged-able until it changes. Change it and end every
     session.
   - **Database credentials** and any `${ENV}` referenced by the configuration.
   - **API keys**: revoke and reissue.

5. **Fix the host, then re-measure.** Install `bubblewrap`, enable cgroup v2, allow unprivileged
   user namespaces (`sysctl kernel.unprivileged_userns_clone=1` where it is off), and re-run
   step 1's probe until it reports `strong`.

6. **Report it as a defect.** An escape from a `strong` jail is a MAYA defect, not a
   configuration problem. It needs a new case in `tests/test_sandbox_linux.py` — the test file
   *is* the record of what MAYA claims to stop — and the claim on the health page corrected until
   it is fixed.

## Verification

- `sandbox_tier()` reports the required tier, with a `reason` that says the probe verified it.
- `python -m pytest tests/test_sandbox_linux.py tests/test_sandbox.py -q` is green (23 tests).
- The specific escape you suspected, re-run through `run_sandboxed`, returns `"ok": false` with
  the refusal above, and `limits_applied` includes `seccomp`.
- No `maya-sbx-*` directory and no `sandbox_runner.py` process outlives its run.
- `admin verify-integrity` exits 0 and `custody/verify` says the chain and anchors agree.
- Whatever you rotated is rotated, and the people whose second factors you invalidated have
  re-enrolled.

**Commands run while this runbook was written.** On a Linux host at the `strong` tier, against a
throwaway `MAYA_HOME`: `sandbox_tier()` (the JSON above is its actual output), the full sandbox
suites (23 passed), and three `run_sandboxed` escape attempts — raw socket, reading MAYA's
configuration, writing to `/etc` — whose refusals are quoted verbatim. **Not exercised:** the
`sandbox.min_tier` startup refusal (this host delivers `strong`, so the refusal cannot be
provoked; its text is quoted from `maya/services/platform.py`), every rotation step, the
`moderate` and `minimal` tiers, and the host-forensics commands (`dmesg`, `ss`, the cgroup tree),
which are the operating system's, not MAYA's.

## What this does not reach

- **A fixed list of attacks is not a proof.** MAYA tests the escapes in
  `tests/test_sandbox_linux.py` and nothing else. §26 records that an external security review
  is out of scope, so no adversary other than those tests has tried.
- **Tectonic is not sandboxed.** The typesetter runs user-authored LaTeX with no resource cap and
  no network isolation (audit §17, item 32). A specification document is untrusted input too, and
  this runbook's measurements do not cover it.
- **No upload expansion or size limits** (§21.5). A zip bomb in a `.xlsx` or a bundle is a
  denial-of-service path that never reaches the sandbox, so nothing here would detect it.
- **No intrusion detection.** MAYA audits that a sandboxed run happened and under which tier. It
  does not watch what the child did, count syscalls, or alert on anything but the tier falling.
- **No quarantine.** An artifact that fails the ladder is recorded as failed and left in the blob
  store; nothing isolates it, and nothing scans it for known-bad content.
- **The audit log names the run, not the escape.** `model.artifact_validated` records `passed` and
  `tier`. If a child escaped and returned a plausible answer, the audit entry looks exactly like a
  successful validation.
