"""
MAYA — what the platform is permitted to fetch.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

MAYA makes very few outbound requests, and two of them are to URLs it did not
choose: `token_endpoint` and `jwks_uri` are read out of an identity provider's
own discovery document and then fetched. Nothing validated the scheme, and
`urllib.request.urlopen` handles `file:` as readily as `https:` — so a
misconfigured or compromised issuer returning
`"jwks_uri": "file:///etc/shadow"` had the platform open it.

Found by turning on the security lint, which is the argument for having one.
"""

import pytest

from core.outbound import OutboundError, permit


class TestOnlyTheSchemesMayaWillFetch:
    def test_https_is_permitted(self):
        assert permit("https://idp.example/.well-known/jwks.json")

    @pytest.mark.parametrize("url", [
        "file:///etc/shadow",
        "file://localhost/etc/passwd",
        "ftp://internal/secrets",
        "gopher://internal:70/x",
        "data:text/plain;base64,aGk=",
    ])
    def test_everything_else_is_refused(self, url):
        with pytest.raises(OutboundError) as exc:
            permit(url)
        assert exc.value.code == "outbound_scheme_refused"
        assert exc.value.remediation

    def test_a_url_with_no_host_is_refused(self):
        with pytest.raises(OutboundError) as exc:
            permit("https:///no-host-here")
        assert exc.value.code == "outbound_host_missing"

    def test_an_empty_url_is_refused_rather_than_fetched(self):
        with pytest.raises(OutboundError) as exc:
            permit("")
        assert exc.value.code == "outbound_url_missing"


class TestPlainHttpIsLoopbackOnly:
    """A developer runs an identity provider on their laptop. That is the only
    reason `http` is admitted at all, and it must not become a way for the
    platform to talk to a network in clear."""

    @pytest.mark.parametrize("url", ["http://127.0.0.1:8080/jwks",
                                     "http://localhost:8080/jwks"])
    def test_loopback_is_permitted(self, url):
        assert permit(url)

    def test_a_routable_host_over_http_is_refused(self):
        with pytest.raises(OutboundError) as exc:
            permit("http://idp.example/jwks")
        assert exc.value.code == "outbound_not_encrypted"

    def test_a_name_that_does_not_resolve_is_not_loopback(self):
        """An unresolvable host is not a reason to relax. Failing open here
        would make every typo a permitted plain-http fetch."""
        with pytest.raises(OutboundError):
            permit("http://nothing.invalid./jwks")

    def test_a_name_resolving_to_both_loopback_and_a_route_is_refused(self,
                                                                     monkeypatch):
        """Every address, not the first.

        A name resolving to `127.0.0.1` *and* a routable address is not
        loopback, and treating it as one admits exactly the redirection this
        exists to refuse.
        """
        import socket

        def resolves_to_both(host, port, *a, **kw):
            return [(2, 1, 6, "", ("127.0.0.1", 0)),
                    (2, 1, 6, "", ("93.184.216.34", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", resolves_to_both)
        with pytest.raises(OutboundError) as exc:
            permit("http://dual.example/jwks")
        assert exc.value.code == "outbound_not_encrypted"


class TestTheFetchSitesUseIt:
    """The guard is only worth anything where the fetching happens."""

    @pytest.mark.parametrize("module,function", [
        ("core.authz.oidc", "_http"),
        ("core.notify.channels", None),
    ])
    def test_the_module_calls_permit(self, module, function):
        import importlib
        import inspect

        source = inspect.getsource(importlib.import_module(module))
        assert "permit(" in source, f"{module} fetches without the guard"

    def test_a_discovery_document_naming_a_file_url_is_refused(self):
        """The attack in one line: the issuer supplies the address."""
        from core.authz.oidc import _http
        with pytest.raises(OutboundError):
            _http("file:///etc/shadow")
