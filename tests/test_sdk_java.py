"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The Java SDK, checked from the suite that actually runs.

`sdk/java` has its own suite — seventeen JUnit tests — and that suite only runs
where somebody has a JDK. This repository's CI runs `pytest`, so a Java client
checked *only* by Maven is a client that rots quietly: the contract in its
README drifts, a helpful commit adds a local tier table, and nothing here
notices for a year.

So the properties that matter across the language boundary are asserted here
too. They are deliberately the *structural* ones — the contract exists, the
implementation honours it, nothing decides anything — rather than a second copy
of what the JUnit suite already proves about behaviour. Two suites asserting the
same behaviour is the same failure as two implementations of a rule, one layer
up.

If a JDK is present, the Maven suite is run as well and its result is the
assertion. If it is not, that is reported as a skip rather than passing quietly:
a green build that silently did not compile the client is exactly the shape of
green this codebase keeps finding and removing.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
JAVA = ROOT / "sdk" / "java"
SOURCE = JAVA / "src" / "main" / "java" / "com" / "maya" / "sdk"

#: Governance vocabulary that must never appear in the CODE. Each one would be
#: a second implementation of a rule this platform already enforces, able to
#: disagree with the first — quietly, in the direction of permitting more,
#: because that is the direction in which nobody files a bug.
BANNED = ('"T0"', '"T8"', "tierFor", "isApproved", "TRAINABILITY",
          "MATERIALITY", "canPromote", "quorumFor")

BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
LINE_COMMENT = re.compile(r"^\s*//.*$", re.M)


def _code(path: pathlib.Path) -> str:
    """One file with its comments removed.

    The comments argue about governance constantly and should — that is where
    the reasoning lives. Stripping them is what makes the assertions below
    about the code rather than about the prose, which is the same distinction
    the Python SDK's own source walker draws.
    """
    text = path.read_text(encoding="utf-8")
    return LINE_COMMENT.sub("", BLOCK_COMMENT.sub("", text))


class TestTheClientExists:
    def test_the_source_is_there(self):
        assert (SOURCE / "Maya.java").is_file()
        assert (JAVA / "pom.xml").is_file()

    def test_it_compiles_to_the_lts_most_banks_are_on(self):
        """Release 17, not because anything wants to be old. A client compiled
        to a release the caller's platform does not run is a client they
        cannot use, which is the same as not shipping one."""
        assert "<maven.compiler.release>17</maven.compiler.release>" in \
            (JAVA / "pom.xml").read_text()

    def test_it_has_no_runtime_dependency(self):
        """The air-gap rule, and the reason it is not merely a preference: an
        SDK with a dependency tree moves the problem into the client's build
        rather than solving it, and a bank's platform team getting Jackson
        through approval to call a register is a real cost somebody pays."""
        pom = (JAVA / "pom.xml").read_text()
        for block in re.findall(r"<dependency>.*?</dependency>", pom, re.S):
            assert "<scope>test</scope>" in block, \
                "a runtime dependency appeared in the Java SDK's pom"


class TestTheContractIsHonoured:
    """Each of these is a property of *this* platform's API rather than of HTTP
    in general, which is why a client that gets them wrong still looks like it
    works."""

    def test_a_post_is_never_retried(self):
        code = _code(SOURCE / "Maya.java")
        idempotent = re.search(r"IDEMPOTENT\s*=[^;]+;", code, re.S)
        assert idempotent, "the client no longer states which methods may be retried"
        assert '"POST"' not in idempotent.group(0)
        for method in ('"GET"', '"PUT"', '"DELETE"'):
            assert method in idempotent.group(0)

    def test_an_outage_is_not_a_refusal(self):
        """They call for opposite responses, and a client that collapses them
        will eventually treat an outage as a governance verdict."""
        code = _code(SOURCE / "Unreachable.java")
        assert "extends RuntimeException" in code
        assert "extends Refused" not in code

    def test_a_refusal_carries_its_remediation(self):
        code = _code(SOURCE / "Refused.java")
        assert "remediation" in code
        assert "public String remediation()" in code

    def test_the_four_catchable_classes_exist(self):
        code = _code(SOURCE / "Refused.java")
        for name in ("NotAuthenticated", "NotPermitted", "NotFound", "Blocked"):
            assert f"class {name} extends Refused" in code

    def test_the_request_id_is_sent_and_read_back(self):
        code = _code(SOURCE / "Maya.java")
        assert 'REQUEST_HEADER = "X-Request-ID"' in code
        assert "firstValue(REQUEST_HEADER)" in code

    def test_the_digest_is_computed_before_the_upload(self):
        """Letting the server hash whatever it received makes the check
        tautological — it would be comparing a file against itself."""
        code = _code(SOURCE / "Maya.java")
        assert "String digest = sha256(file);" in code
        assert '"digest", digest' in code

    def test_a_dataset_is_streamed_and_never_materialised(self):
        code = _code(SOURCE / "Maya.java")
        assert "OutputStream sink" in code
        assert "BodyHandlers.ofInputStream()" in code
        assert "BodyHandlers.ofString()" not in _stream_method(code)

    def test_it_authenticates_with_a_credential_and_not_a_cookie(self):
        code = _code(SOURCE / "Maya.java")
        assert "Authorization" in code
        assert "Cookie" not in code and "csrf" not in code.lower()

    def test_it_never_follows_a_redirect(self):
        """A 302 to a sign-in page would turn a refusal into an HTML body and
        a 200, which is the one failure mode a service client must not have."""
        assert "Redirect.NEVER" in _code(SOURCE / "Maya.java")


def _stream_method(code: str) -> str:
    start = code.index("streamFeaturesetData")
    return code[start:code.index("// ---", start)] if "// ---" in code[start:] \
        else code[start:]


class TestItDecidesNothing:
    """The rule most likely to be broken by somebody being helpful."""

    @pytest.mark.parametrize("banned", BANNED)
    def test_no_governance_vocabulary_in_the_code(self, banned):
        for path in SOURCE.glob("*.java"):
            assert banned not in _code(path), \
                f"{path.name} decides something: {banned}"

    def test_the_grammar_is_fetched_rather_than_enumerated(self):
        """A vocabulary copied into a client goes stale silently, and it goes
        stale in the permissive direction."""
        assert 'call("GET", "/grammar"' in _code(SOURCE / "Maya.java")

    def test_there_is_no_typed_model_class(self):
        """A Java object graph mirroring the platform's schemas is a second
        description of them. Deliberate, and the Python SDK made the same
        choice for the same reason."""
        classes = {p.stem for p in SOURCE.glob("*.java")}
        assert classes == {"Maya", "Json", "Refused", "Unreachable"}


class TestTheReadmeSaysWhatIsTrue:
    def test_it_no_longer_says_not_built(self):
        readme = (JAVA / "README.md").read_text()
        assert readme.startswith("# MAYA — Java SDK")
        assert "**Not built.**" not in readme

    def test_it_names_the_jdk_trap(self):
        """A JRE-only install fails at the compiler plugin with *release
        version 17 not supported*, which reads as a Maven problem and is not
        one. Found the hard way while building this."""
        assert "JRE-only install" in (JAVA / "README.md").read_text()

    def test_the_test_count_it_states_is_the_test_count(self):
        readme = (JAVA / "README.md").read_text()
        stated = int(re.search(r"(\d+) tests, no runtime", readme).group(1))
        suite = (JAVA / "src" / "test" / "java" / "com" / "maya" / "sdk"
                 / "MayaTest.java").read_text()
        assert stated == suite.count("    void "), \
            "the Java README's test count drifted from the suite"


@pytest.mark.skipif(shutil.which("mvn") is None,
                    reason="no Maven on this machine")
class TestTheJavaSuiteItself:
    """Run where a JDK is present, skipped where one is not — and skipped
    loudly rather than passing quietly, because a green build that silently did
    not compile the client is exactly the shape of green this codebase keeps
    finding and removing."""

    def test_it_compiles_and_its_own_tests_pass(self):
        jdk = _a_jdk()
        if jdk is None:
            pytest.skip("no JDK with a compiler; only a JRE was found")
        result = subprocess.run(
            ["mvn", "-q", "-o", "test"], cwd=JAVA, capture_output=True,
            text=True, timeout=900,
            env={**_environ(), "JAVA_HOME": str(jdk)})
        if result.returncode != 0 and "Could not resolve" in (
                result.stdout + result.stderr):
            pytest.skip("Maven is offline and the plugins are not cached")
        assert result.returncode == 0, result.stdout[-4000:]


def _environ() -> dict:
    import os
    return dict(os.environ)


def _a_jdk():
    """A JDK that can actually compile, which is not the same as a `java`.

    This machine has a JRE 25 and a JDK 21, and Maven picks the first — which
    fails at the compiler plugin with a message about release 17 that reads as
    a Maven problem and is not one.
    """
    for candidate in sorted(pathlib.Path("/usr/lib/jvm").glob("*"),
                            reverse=True):
        if (candidate / "bin" / "javac").is_file():
            return candidate
    return None
