# ADR-026 — A signed-in session's principal is reused for two seconds

**Status:** Accepted, 0.3.0 (2026-09-19); recorded in specification revision 2.3.

## Context

The web tier holds no shared key: each page calls the API as the person signed in, through
the SDK (§12). One page makes several of those calls, and each resolved the same session from
the database — six times for the home page. That was measurable latency on every page, paid
to re-learn something that had not changed in the last few milliseconds. The fix is a cache;
the cost of a cache is staleness, and a stale principal is a session that outlives its end.

## Decision

A fully signed-in session's principal is reused for
**`auth.session.principal_cache_seconds`** (default **2**; **0** turns reuse off). A sign-out,
revocation or access change **applies at once in the web process that made it**, and at most
that many seconds late in any other. A session still owing a second factor is never cached.
API keys are not cached.

## Consequences

- **This is the one place a session outlives its end, and it is accepted deliberately.** With
  several web processes (ADR-022), a person signed out — by themselves, by an administrator,
  or by the IdP through back-channel logout (ADR-027) — can still be served by another process
  for up to two seconds.
- Where that window matters more than the page cost, set it to 0.
- Within one process there is no window at all, so a single-process deployment is unaffected.

## References

- Specification §12 (revision 2.3 note); README *Not yet*.
- Code: `maya/services/auth.py` (`_session_principal`, `_resolve_session`),
  `config/application.yaml` (`auth.session.principal_cache_seconds`).
- Tests: `tests/test_principal_cache.py` — `test_a_session_is_resolved_once_then_reused`,
  `test_sign_out_and_revocation_apply_at_once_in_this_process`,
  `test_a_role_change_applies_at_once_in_this_process`, `test_zero_turns_reuse_off`. The
  cross-process window itself has no test.
