/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 */
package com.maya.sdk;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * What this client must get right, asserted.
 *
 * <p>The Python SDK's suite runs against the real application in-process,
 * because a mock of the thing under test proves only that the mock agrees with
 * itself. Java cannot reach that seam without running a server, so these tests
 * take the other half of the job: the properties that are <i>local</i> to the
 * client and are the ones a Java client gets wrong. Retrying a POST. Collapsing
 * an outage into a refusal. Discarding the remediation. Deciding something.
 *
 * <p>The last of those is asserted on the source, which is what the contract in
 * this directory's README asks for by name — it is the rule most likely to be
 * broken by somebody being helpful.
 */
class MayaTest {

    @Nested
    @DisplayName("A refusal carries all three parts")
    class Refusals {

        @Test
        void the_remediation_survives() {
            Refused refused = Refused.of(423, Json.object("""
                    {"error": "blocked",
                     "detail": "an open blocking finding stands",
                     "remediation": "close it, or ask for a downgrade"}"""),
                    "", "req-1");
            assertEquals("blocked", refused.error());
            assertEquals("close it, or ask for a downgrade",
                         refused.remediation());
            // And it is in the message, because the half a caller actually
            // reads is the stack trace.
            assertTrue(refused.getMessage().contains("ask for a downgrade"));
        }

        @Test
        void the_request_id_travels_with_the_exception() {
            Refused refused = Refused.of(403, Map.of(), "", "abc123");
            assertEquals("abc123", refused.requestId());
            assertTrue(refused.getMessage().contains("abc123"));
        }

        @Test
        void the_classes_a_caller_catches_on_purpose_are_separate() {
            assertInstanceOf(Refused.NotAuthenticated.class,
                             Refused.of(401, Map.of(), "", ""));
            assertInstanceOf(Refused.NotPermitted.class,
                             Refused.of(403, Map.of(), "", ""));
            assertInstanceOf(Refused.NotFound.class,
                             Refused.of(404, Map.of(), "", ""));
            for (int status : new int[] {409, 410, 423}) {
                assertInstanceOf(Refused.Blocked.class,
                                 Refused.of(status, Map.of(), "", ""));
            }
        }

        @Test
        void a_nested_problem_document_is_looked_through() {
            // FastAPI wraps the platform's problem document under `detail`
            // when it raises. A client that read only the top level would
            // report every such refusal with no remediation at all.
            Refused refused = Refused.of(422, Json.object("""
                    {"detail": {"error": "audience_required",
                                "detail": "no audience",
                                "remediation": "name the principal"}}"""),
                    "", "");
            assertEquals("audience_required", refused.error());
            assertEquals("name the principal", refused.remediation());
        }

        @Test
        void a_proxys_html_is_kept_rather_than_thrown_over() {
            // A 502 answers in HTML. Replacing a legible failure with a parse
            // error is the worst possible moment to lose the body.
            Refused refused = Refused.of(502, Map.of(),
                                         "<html>bad gateway</html>", "");
            assertTrue(refused.detail().contains("bad gateway"));
        }

        @Test
        void an_outage_is_not_a_refusal() {
            // Unreachable deliberately does not extend Refused. A client that
            // collapsed them treats an outage as a governance verdict.
            assertFalse(Refused.class.isAssignableFrom(Unreachable.class));
        }
    }

    @Nested
    @DisplayName("A POST is never retried")
    class Retries {

        @Test
        void only_the_idempotent_methods_may_be_retried() {
            for (String method : List.of("GET", "HEAD", "OPTIONS", "PUT",
                                         "DELETE")) {
                assertTrue(Maya.mayRetry(method), method);
            }
            assertFalse(Maya.mayRetry("POST"));
            assertFalse(Maya.mayRetry("post"));
        }

        @Test
        void a_timed_out_post_says_not_to_retry_it() {
            // The message is the control here: nothing stops a caller
            // retrying, so the exception has to say why they must not.
            Maya maya = Maya.withApiKey("http://127.0.0.1:1", "k");
            Unreachable exc = assertThrows(Unreachable.class,
                    () -> maya.call("POST", "/models", Map.of("urn", "x")));
            assertTrue(exc.getMessage().contains("Do NOT retry"));
            assertTrue(exc.getMessage().contains("not a refusal"));
        }

        @Test
        void a_timed_out_get_says_it_is_safe() {
            Maya maya = Maya.withApiKey("http://127.0.0.1:1", "k");
            Unreachable exc = assertThrows(Unreachable.class,
                                           () -> maya.whoami());
            assertTrue(exc.getMessage().contains("safe to retry"));
        }
    }

    @Nested
    @DisplayName("The digest is computed before the upload")
    class Digests {

        @Test
        void a_file_hashes_to_the_platforms_spelling(@org.junit.jupiter.api.io.TempDir Path dir)
                throws IOException {
            Path file = dir.resolve("model.onnx");
            Files.writeString(file, "hello");
            String digest = Maya.sha256(file);
            assertTrue(digest.startsWith("sha256:"));
            // The known SHA-256 of "hello". Asserted against a constant rather
            // than against a second computation: two implementations of the
            // same mistake agree.
            assertEquals("sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7"
                         + "425e73043362938b9824", digest);
        }
    }

    @Nested
    @DisplayName("Both URN spellings reach the same place")
    class Urns {

        @Test
        void the_full_urn_and_the_short_name_agree() {
            assertEquals("credit.pd.smallbiz",
                         Maya.shortName("maya://model/credit.pd.smallbiz"));
            assertEquals("credit.pd.smallbiz",
                         Maya.shortName("credit.pd.smallbiz"));
            assertEquals("a.b#champion", Maya.shortName("maya://model/a.b#champion"));
        }
    }

    @Nested
    @DisplayName("JSON, written out rather than depended on")
    class JsonRoundTrip {

        @Test
        void it_reads_what_maya_answers() {
            Map<String, Object> out = Json.object("""
                    {"urn": "maya://model/x", "tier": 2, "approved": true,
                     "versions": [{"semver": "1.0.0"}], "note": null}""");
            assertEquals("maya://model/x", out.get("urn"));
            assertEquals(2.0, out.get("tier"));
            assertEquals(Boolean.TRUE, out.get("approved"));
            assertEquals(1, ((List<?>) out.get("versions")).size());
            assertTrue(out.containsKey("note"));
        }

        @Test
        void it_writes_what_maya_accepts() {
            String written = Json.write(new java.util.LinkedHashMap<>(Map.of(
                    "urn", "maya://model/x")));
            assertEquals("{\"urn\":\"maya://model/x\"}", written);
        }

        @Test
        void quotes_and_control_characters_survive_the_round_trip() {
            String awkward = "he said \"no\"\n\tand\\left";
            Map<String, Object> out = Json.object(
                    Json.write(Map.of("because", awkward)));
            assertEquals(awkward, out.get("because"));
        }

        @Test
        void an_object_it_cannot_serialise_says_why() {
            IllegalArgumentException exc = assertThrows(
                    IllegalArgumentException.class,
                    () -> Json.write(new Object()));
            assertTrue(exc.getMessage().contains("second description"));
        }
    }

    @Nested
    @DisplayName("The SDK decides nothing")
    class DecidesNothing {

        /**
         * Asserted on the source, which is what this directory's README asks
         * for by name. The temptation to "help" — a local approved check, a
         * tier table, an enumeration of the trainability classes — is exactly
         * what would create a second implementation of a governance rule, able
         * to disagree with the first in the direction of permitting more.
         */
        @Test
        void no_governance_vocabulary_appears_in_the_code() throws IOException {
            Path root = Path.of("src", "main", "java");
            try (Stream<Path> files = Files.walk(root)) {
                for (Path file : files.filter(p -> p.toString().endsWith(".java"))
                        .toList()) {
                    String source = stripComments(Files.readString(file));
                    for (String banned : List.of("\"T0\"", "\"T8\"",
                                                 "\"approved\" ==",
                                                 "tierFor", "isApproved",
                                                 "TRAINABILITY")) {
                        assertFalse(source.contains(banned),
                                    file + " contains " + banned
                                    + ", which is a governance decision taken "
                                    + "locally");
                    }
                }
            }
        }

        @Test
        void the_grammar_is_fetched_rather_than_enumerated() throws IOException {
            String source = Files.readString(
                    Path.of("src/main/java/com/maya/sdk/Maya.java"));
            assertTrue(source.contains("call(\"GET\", \"/grammar\""));
        }

        /**
         * Comments in this client argue about governance constantly and should.
         * Stripping them is what makes the assertion above about the CODE
         * rather than about the prose — the same distinction the Python
         * suite's equivalent walker draws.
         */
        private String stripComments(String source) {
            return source.replaceAll("(?s)/\\*.*?\\*/", "")
                    .replaceAll("(?m)^\\s*//.*$", "");
        }
    }
}
