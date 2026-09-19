# ADR-028 — A timestamp authority's signature is checked against its CA, inside MAYA

**Status:** Accepted, 0.3.0 (2026-09-19).

## Context

Custody anchors pin the audit chain's head outside the database, so that a consistent
rewrite — history changed and every later hash recomputed — is still caught (§29.6). One
anchor method is an RFC 3161 timestamp token from a third-party authority. MAYA checked the
token's status and that it carried the head's imprint, and left the authority's signature to
be checked by hand. A token whose signature nobody checked is a claim, not a timestamp:
anyone who could rewrite the database could write a plausible token beside it.

## Decision

With **`custody.anchor.tsa_ca_file`** naming the authority's CA certificate (PEM), MAYA checks
the authority's signature on every token with `openssl ts -verify`, **when it anchors and at
every custody verification**. A token that fails is not kept, and the anchor records why. A
CA file that is configured but missing, or `openssl` not installed, **refuses to start**:
*"custody.anchor.tsa_ca_file needs the CA file to exist and openssl to be installed"*.
Without the setting, MAYA checks status and imprint only.

## Consequences

- MAYA depends on the `openssl` binary for this check — a subprocess, not a library — and
  says so at startup rather than at the first anchor.
- RFC 3161 anchoring stays off by default, because it sends the head hash to a third party.
- Without a CA file the signature is still the operator's to check. The token's recorded
  detail names an `openssl ts -verify -data …` command for that; see the
  [custody runbook](../runbooks/audit-chain-and-custody.md) for why that hint is wrong and
  what to run instead.

## References

- Specification §29.6; README *Not yet*.
- Code: `maya/services/custody.py` (`verify_tsa_signature`, `check_timestamp_response`,
  `CustodyService._check_token`, `CustodyService.verify`), `config/application.yaml`
  (`custody.anchor`).
- Tests: `tests/test_custody.py` —
  `test_rfc3161_timestamp_is_requested_and_its_imprint_checked`,
  `test_a_real_tsa_signature_is_verified_against_its_ca`,
  `test_an_anchor_catches_a_rechained_rewrite`.
