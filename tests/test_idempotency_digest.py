"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The idempotency digest must be over what a request MEANS.

Taken over the raw bytes, `{"a":1,"b":2}` and `{"b":2,"a":1}` hash differently,
so a client retrying the identical request through a different JSON library, a
proxy that re-serialised it, or a language whose mapping order differs was
refused `idempotency_key_reused` — and told the key "was used for a different
POST", which was false.

That is the wrong direction for this particular control to fail in.
Idempotency exists so a caller who is unsure whether their request arrived can
safely send it again; digesting the spelling made the safe retry the one thing
guaranteed to fail, and the refusal blamed the caller for a change they had
not made.

The other half matters just as much: a genuinely different body must still be
refused, or the control is gone.
"""
from __future__ import annotations

import json

from core.concurrency.idempotency import _body_digest


def _as_bytes(payload) -> bytes:
    return json.dumps(payload).encode("utf-8")


class TestOrderingIsNotMeaning:
    def test_the_same_object_in_a_different_order_digests_the_same(self):
        first = _as_bytes({"urn": "maya://model/pd", "owner": "ana",
                           "domain": "credit"})
        second = _as_bytes({"domain": "credit", "owner": "ana",
                            "urn": "maya://model/pd"})
        assert first != second, "the two spellings must differ as bytes"
        assert _body_digest(first) == _body_digest(second)

    def test_nested_ordering_is_also_irrelevant(self):
        a = _as_bytes({"fields": {"owner": "ana", "domain": "credit"}})
        b = _as_bytes({"fields": {"domain": "credit", "owner": "ana"}})
        assert _body_digest(a) == _body_digest(b)

    def test_whitespace_between_tokens_is_irrelevant(self):
        compact = b'{"a":1,"b":2}'
        spaced = b'{ "a" : 1 , "b" : 2 }'
        assert _body_digest(compact) == _body_digest(spaced)


class TestEveryRealDifferenceStillShows:
    def test_a_changed_value_digests_differently(self):
        assert _body_digest(_as_bytes({"owner": "ana"})) != \
            _body_digest(_as_bytes({"owner": "ben"}))

    def test_an_added_field_digests_differently(self):
        assert _body_digest(_as_bytes({"owner": "ana"})) != \
            _body_digest(_as_bytes({"owner": "ana", "tier": 1}))

    def test_a_removed_field_digests_differently(self):
        assert _body_digest(_as_bytes({"owner": "ana", "tier": 1})) != \
            _body_digest(_as_bytes({"owner": "ana"}))

    def test_a_list_reordered_digests_differently(self):
        """Order in a LIST is meaning — `["a","b"]` and `["b","a"]` are two
        different requests, and only mapping order is spelling."""
        assert _body_digest(_as_bytes({"roles": ["a", "b"]})) != \
            _body_digest(_as_bytes({"roles": ["b", "a"]}))

    def test_a_string_and_a_number_digest_differently(self):
        assert _body_digest(_as_bytes({"tier": 1})) != \
            _body_digest(_as_bytes({"tier": "1"}))


class TestWhatIsNotJson:
    def test_a_body_that_is_not_json_falls_back_to_the_bytes(self):
        """Byte equality is the only meaning available for an opaque body."""
        assert _body_digest(b"not json at all") == \
            _body_digest(b"not json at all")
        assert _body_digest(b"not json at all") != _body_digest(b"something else")

    def test_an_empty_body_is_stable(self):
        assert _body_digest(b"") == _body_digest(b"")
