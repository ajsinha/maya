# ADR-017 — Workflow policy is authored and managed in the UI; YAML is a projection

**Status:** Accepted, 2026-09-17.

## Context

Approval policy — which states exist, who may move an object between them, how many
approvers, what separation of duties — is governance. Kept as a YAML file in the
repository, it is changed by whoever can merge to the repository, reviewed by nobody who
owns model risk, and takes effect at the next deploy. Kept in two places, a file and a
database, the two disagree and nobody knows which one ran.

## Decision

**The policy is data, authored and managed in the UI** (`/workflow/policies`), with
validation at edit time: an unknown or unreachable state, an unregistered check, a role that
does not exist, or an approval no role could satisfy is refused with the reason before the
policy can be saved. A saved policy is a draft with an impact preview over the live
population. **Activation is approval by a second administrator**, and the previous version
is kept. YAML is an import and export format — a projection that round-trips byte for
byte — never a second authority.

## Consequences

- A real policy editor had to be built, with edit-time validation, and the policy is itself
  governed: *"A policy you drafted must be activated by another administrator: the rules of
  governance are governed too"*.
- A single-administrator deployment cannot change policy without
  `workflow.allow_self_approval`, which is honoured only in `dev`.
- Break-glass exists, is loud and permanent on the record, and is reported on its own page.

## References

- Specification §10.2, §10.4, §10.6; plan §4.2, M5.
- Code: `maya/workflow/policy.py` (validation, `to_yaml`, `from_yaml`),
  `maya/workflow/default_policies.yaml`, `maya/services/workflow_service.py` (`activate`),
  `maya/web/routes/workflow.py`, `maya/web/static/js/policy.js`.
- Tests: `tests/test_workflow_and_estate.py::test_invalid_policies_are_refused_at_edit_time`,
  `::test_policy_is_governed_and_changes_behaviour`, `::test_yaml_round_trip_is_byte_identical`,
  `::test_break_glass_is_loud_and_permanent`; `tests/test_web.py::test_policy_editor_saves_a_draft`;
  `tests/test_web_catalog_models.py::test_policy_editor_import_and_activation_by_a_second_admin`.
