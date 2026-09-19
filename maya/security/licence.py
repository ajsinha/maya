"""
Licence algebra (§29.6): vendor terms that follow the data through the algebra.

A source declares its terms; anything built from it inherits the *most
restrictive* combination of its operands' terms. The vocabulary is closed and
ordered, so "most restrictive" is computable rather than a judgement call:

* ``redistribution``: none < internal < external < public — how far the data may
  travel. ``none``: it may be viewed and used inside MAYA but never leaves in
  bulk; ``internal``: downloads within the firm; ``external``: to regulators and
  counterparties (bundles); ``public``: anywhere.
* ``derived_works``: forbidden < attribution < allowed — whether a derived
  feature or a trained model may be built on it.
* ``population``: groups or ``desk:<name>`` entries allowed to receive it; the
  combination is the intersection (an empty intersection means nobody).
* ``retention_days``: the shortest wins.
* ``vendors``: accumulated, for attribution.

Every combined clause remembers which source imposed it, so a refusal names the
source and the clause instead of just saying no.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any

from maya.core.errors import LicenceBreach, ValidationFailed

REDISTRIBUTION = ("none", "internal", "external", "public")
DERIVED = ("forbidden", "attribution", "allowed")
KEYS = ("vendor", "redistribution", "derived_works", "population", "retention_days", "notes")


def validate(lic: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    if not lic:
        return errors
    unknown = set(lic) - set(KEYS)
    if unknown:
        errors.append("unknown licence term(s): " + ", ".join(sorted(unknown)))
    if lic.get("redistribution", "public") not in REDISTRIBUTION:
        errors.append(f"licence.redistribution must be one of {', '.join(REDISTRIBUTION)}")
    if lic.get("derived_works", "allowed") not in DERIVED:
        errors.append(f"licence.derived_works must be one of {', '.join(DERIVED)}")
    if not isinstance(lic.get("population", []), list):
        errors.append("licence.population is a list of groups or desk:<name> entries")
    days = lic.get("retention_days")
    if days is not None and (not isinstance(days, int) or days < 1):
        errors.append("licence.retention_days is a positive whole number of days")
    return errors


def combine(sources: list[tuple[str, dict[str, Any] | None]]) -> dict[str, Any]:
    """The most restrictive combination; ``clauses`` records who imposed each term."""
    out: dict[str, Any] = {"redistribution": "public", "derived_works": "allowed",
                           "population": None, "retention_days": None, "vendors": [],
                           "clauses": {}}
    for ref, lic in sources:
        if not lic:
            continue
        if lic.get("vendor") and lic["vendor"] not in out["vendors"]:
            out["vendors"].append(lic["vendor"])
        _tighten(out, "redistribution", REDISTRIBUTION, lic, ref)
        _tighten(out, "derived_works", DERIVED, lic, ref)
        if lic.get("population"):
            mine = set(lic["population"])
            before = out["population"]
            out["population"] = sorted(mine if before is None else set(before) & mine)
            if before is None or set(out["population"]) != set(before):
                out["clauses"]["population"] = _who(lic, ref)
        days = lic.get("retention_days")
        if days and (out["retention_days"] is None or days < out["retention_days"]):
            out["retention_days"] = days
            out["clauses"]["retention_days"] = _who(lic, ref)
    return out


def _tighten(out: dict[str, Any], term: str, order: tuple[str, ...], lic: dict[str, Any],
             ref: str) -> None:
    value = lic.get(term)
    if value and order.index(value) < order.index(out[term]):
        out[term] = value
        out["clauses"][term] = _who(lic, ref)


def _who(lic: dict[str, Any], ref: str) -> str:
    return f"{lic['vendor']} via {ref}" if lic.get("vendor") else ref


def _breach(eff: dict[str, Any], term: str, what: str) -> LicenceBreach:
    source = eff["clauses"].get(term, "a source")
    return LicenceBreach(f"Licence: {what} ({term}: {eff[term]}, imposed by {source})",
                         term=term, value=eff[term], source=source)


def check_export(eff: dict[str, Any], audience: str) -> None:
    """``internal``: a download inside the firm; ``external``: a bundle for outsiders."""
    need = {"internal": "internal", "external": "external"}[audience]
    if REDISTRIBUTION.index(eff["redistribution"]) < REDISTRIBUTION.index(need):
        raise _breach(eff, "redistribution",
                      "this data may not leave MAYA in bulk" if eff["redistribution"] == "none"
                      else "this data may not be given to anyone outside the firm")


def check_derivation(eff: dict[str, Any], what: str) -> None:
    if eff["derived_works"] == "forbidden":
        raise _breach(eff, "derived_works", f"the vendor forbids derived works ({what})")


def in_population(eff: dict[str, Any], groups: list[str], desk: str | None) -> bool:
    if eff["population"] is None:
        return True
    allowed = set(eff["population"])
    return bool(allowed & set(groups)) or (desk is not None and f"desk:{desk}" in allowed)


def check_reader(eff: dict[str, Any], who: str, groups: list[str], desk: str | None) -> None:
    if not in_population(eff, groups, desk):
        raise _breach(eff, "population", f"{who} is outside the population permitted to "
                                         f"receive this data")


def normalise(lic: dict[str, Any] | None) -> dict[str, Any] | None:
    if not lic:
        return None
    errors = validate(lic)
    if errors:
        raise ValidationFailed("; ".join(errors))
    return lic
