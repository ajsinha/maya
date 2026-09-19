# ADR-014 — Platforms: Linux only is exercised; Windows and macOS out of scope

**Status:** Accepted 2026-09-17 as "Windows, Linux and macOS equally first-class".
**Amended by the owner's decision (recorded at 0.3.0, 2026-09-19):** only Linux is
exercised, and there is no hosted CI. The specification (§24.5, SC-14) still states the
original decision; this record is where the change is written down.

## Context

The specification made all three operating systems first-class (§24.5), for a real reason:
server deployments will be Linux, but the laptop topology will overwhelmingly not be, and a
platform a quant cannot run on their own machine is one they route around. The plan
therefore put three-OS CI in M0, on an empty repository, because establishing it later
means discovering forty platform assumptions at once (plan §5).

That CI was never set up, and there is no hosted CI of any kind (ADR-002).

## Decision

**Only Linux is exercised.** Windows and macOS are out of scope by the owner's decision. The
code keeps the portable choices the original decision required — `spawn` everywhere,
`pathlib`, atomic exclusive-create commits, no `flock`, a declared sandbox tier per
platform, `tzdata` pinned for Windows — but nothing proves them on the other two.

## Consequences

- **SC-14 — the full suite green on all three — is not met**, and gates 11c and 12 of
  the plan (the cross-platform byte comparison of the Type B seams, and the three-platform
  matrix) are not built.
- Code that exists only for the other platforms has **never run**: the `moderate`
  sandbox tier through `sandbox-exec` on macOS, the wall-clock `minimal` tier on Windows,
  and the `tzdata` fallback Windows depends on for time zones.
- The risk the plan named is now simply carried: a Windows or macOS user is the first
  person to run MAYA there, and whatever they discover is discovered in use.
- The `strong` sandbox tier (bubblewrap, seccomp, cgroup v2) is Linux-only in any case.

## References

- Specification §24.5, SC-14; plan §5, M0 status note, §7 (rungs 11c, 12); README
  *Out of scope by decision*.
- Code: `run_maya_web.py` (`spawn`), `maya/security/sandbox.py` (`sandbox_tier`),
  `maya/core/backends.py` (`tzdb` seam), `requirements.txt` (`tzdata`).
- Tests: `tests/test_sandbox_linux.py` (the `strong` tier, Linux only);
  `tests/test_sandbox.py::test_tier_is_declared_honestly`. No test runs on another OS.
