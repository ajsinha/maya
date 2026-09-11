/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 */
package com.maya.sdk;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.Base64;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/**
 * A client for one MAYA instance, addressed as one principal.
 *
 * <h2>The one rule this exists to keep</h2>
 *
 * <p><b>The SDK never decides anything.</b> It carries requests and translates
 * refusals. It holds no rule about who may act, no local view of whether a
 * version is approved, no copy of the tiering bands, no enumeration of the
 * trainability classes or of what any of them admits. Every one of those would
 * be a second implementation of a governance rule, and a second implementation
 * is a thing that can disagree with the first — quietly, in the direction of
 * permitting more, because that is the direction in which nobody files a bug.
 *
 * <p>The other half of the same principle is why it exists at all:
 * <b>the compliant path has to be the fast path.</b> If registering a model
 * properly takes forty lines of {@code HttpClient} and getting it wrong takes
 * four, the register fills with models nobody registered properly.
 *
 * <h2>Usage</h2>
 *
 * <pre>{@code
 * Maya maya = Maya.withApiKey("https://maya.internal", System.getenv("MAYA_API_KEY"));
 * Map<String, Object> me = maya.whoami();
 *
 * Map<String, Object> descriptor = maya.resolve(
 *     "maya://model/credit.pd.smallbiz#champion", "prod",
 *     "svc/origination", "origination_decision");
 * }</pre>
 *
 * <h2>What is deliberately absent</h2>
 *
 * <p>There is no typed model class, no builder per endpoint, and no generated
 * client. A Java object graph mirroring the platform's schemas is a second
 * description of them that goes stale in the permissive direction — and the
 * Python SDK, which is the worked example this follows, made the same choice
 * for the same reason. What a caller gets is {@code Map<String, Object>} and
 * the platform's own field names, which are the names in its documentation,
 * its OpenAPI document and its error messages.
 */
public final class Maya {

    /** The versioned API prefix. Liveness sits outside it, on purpose. */
    public static final String API = "/api/v1";

    /** Sent on every request, and read back off every response. */
    public static final String REQUEST_HEADER = "X-Request-ID";

    /**
     * Methods that may be retried.
     *
     * <p>{@code POST} is not among them and never will be. A create that timed
     * out may well have succeeded, and retrying it registers the model twice or
     * records two parameter sets. An SDK that quietly duplicates a governance
     * act is worse than one that fails loudly, because the duplicate is now in
     * the evidence chain and somebody has to explain it.
     */
    private static final java.util.Set<String> IDEMPOTENT =
            java.util.Set.of("GET", "HEAD", "OPTIONS", "PUT", "DELETE");

    private final HttpClient http;
    private final String baseUrl;
    private final String authorization;
    private final Duration timeout;
    private String lastRequestId = "";

    private Maya(String baseUrl, String authorization, Duration timeout) {
        this.baseUrl = baseUrl.endsWith("/")
                ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        this.authorization = authorization;
        this.timeout = timeout;
        this.http = HttpClient.newBuilder()
                .connectTimeout(timeout)
                // Never follow a redirect automatically. A 302 to a sign-in
                // page would turn a refusal into an HTML body and a 200, which
                // is the one failure mode a service client must not have.
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    /**
     * A client authenticating with an API key. This is how a service connects.
     *
     * <p>A password names a person and carries everything they hold. A key
     * names a credential that expires, can be narrowed to a subset of
     * permissions, and can be revoked without touching the account.
     */
    public static Maya withApiKey(String baseUrl, String apiKey) {
        return new Maya(baseUrl, "Bearer " + apiKey, Duration.ofSeconds(30));
    }

    /**
     * A client authenticating as a person, over HTTP Basic.
     *
     * <p><b>Not a cookie.</b> A session cookie is <i>ambient</i> — a browser
     * sends it whether or not the page that triggered the request came from us
     * — which is why a mutating call under one needs a CSRF token. A credential
     * the caller presents is not ambient, so no token applies, and there is
     * nothing for a service client to gain from the cookie flow except a token
     * to get wrong.
     */
    public static Maya withPassword(String baseUrl, String username,
                                    String password) {
        String basic = Base64.getEncoder().encodeToString(
                (username + ":" + password).getBytes(StandardCharsets.UTF_8));
        return new Maya(baseUrl, "Basic " + basic, Duration.ofSeconds(30));
    }

    /** The request id of the last call, as the server wrote it down. */
    public String lastRequestId() {
        return lastRequestId;
    }

    // ------------------------------------------------------------- the wire
    /** One request against the versioned API. Returns the decoded body. */
    public Map<String, Object> call(String method, String path,
                                    Object body) {
        return call(method, path, body, Map.of());
    }

    /** One request, with query parameters. Null-valued parameters are dropped. */
    public Map<String, Object> call(String method, String path, Object body,
                                    Map<String, ?> params) {
        String text = send(method, API + path, body, params, false);
        try {
            return Json.object(text);
        } catch (RuntimeException exc) {
            // A body that is not an object is not a failure of this client.
            // Hand it back whole rather than throwing over it.
            return Map.of("body", text);
        }
    }

    /**
     * A request outside {@code /api/v1}, for liveness.
     *
     * <p>Readiness is not a governed operation, and a monitoring probe should
     * not have to track an API version to ask whether the process is up.
     */
    public Map<String, Object> callAbsolute(String method, String path) {
        return Json.object(send(method, path, null, Map.of(), true));
    }

    private String send(String method, String path, Object body,
                        Map<String, ?> params, boolean absolute) {
        String requestId = UUID.randomUUID().toString().replace("-", "")
                .substring(0, 16);
        URI uri = URI.create(baseUrl + path + query(params));
        HttpRequest.Builder builder = HttpRequest.newBuilder(uri)
                .timeout(timeout)
                .header("Authorization", authorization)
                .header("Accept", "application/json")
                .header(REQUEST_HEADER, requestId);
        if (body == null) {
            builder.method(method, HttpRequest.BodyPublishers.noBody());
        } else {
            builder.header("Content-Type", "application/json")
                    .method(method, HttpRequest.BodyPublishers.ofString(
                            Json.write(body), StandardCharsets.UTF_8));
        }
        HttpResponse<String> response;
        try {
            response = http.send(builder.build(),
                                 HttpResponse.BodyHandlers.ofString());
        } catch (IOException | InterruptedException exc) {
            if (exc instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            // Not a Refused. See Unreachable's own note: collapsing these is
            // how an outage gets treated as a governance verdict.
            throw new Unreachable(
                    "MAYA did not answer " + method + " " + path
                    + ". This is not a refusal — nothing was decided"
                    + (IDEMPOTENT.contains(method)
                       ? ". This method is safe to retry"
                       : ". Do NOT retry: a " + method
                         + " that timed out may have succeeded"),
                    exc);
        }
        // The server's own id wins when it sends one: that is the identifier
        // it wrote down, and matching the log is the whole point.
        lastRequestId = response.headers()
                .firstValue(REQUEST_HEADER)
                .orElse(requestId);
        if (response.statusCode() >= 400) {
            throw refusal(response.statusCode(), response.body());
        }
        return response.body();
    }

    private Refused refusal(int status, String body) {
        Map<String, Object> parsed;
        try {
            parsed = Json.object(body);
        } catch (RuntimeException exc) {
            parsed = Map.of();
        }
        return Refused.of(status, parsed, body, lastRequestId);
    }

    private static String query(Map<String, ?> params) {
        if (params == null || params.isEmpty()) {
            return "";
        }
        StringBuilder out = new StringBuilder();
        for (Map.Entry<String, ?> entry : params.entrySet()) {
            if (entry.getValue() == null) {
                continue;
            }
            out.append(out.isEmpty() ? '?' : '&')
                    .append(encode(entry.getKey()))
                    .append('=')
                    .append(encode(String.valueOf(entry.getValue())));
        }
        return out.toString();
    }

    private static String encode(String text) {
        return URLEncoder.encode(text, StandardCharsets.UTF_8);
    }

    // ------------------------------------------------------------- the verbs
    /**
     * Who the platform thinks you are, and what you may do.
     *
     * <p>Worth calling first in any tool. The permissions come from the
     * platform rather than from anything here, so a tool can hide an action the
     * caller may not take without ever deciding that for itself.
     */
    public Map<String, Object> whoami() {
        return call("GET", "/me", null);
    }

    /** Readiness, including whether the evidence chain verifies. */
    public Map<String, Object> health() {
        return callAbsolute("GET", "/health/ready");
    }

    /**
     * The warrant grammar: verbs, runtimes, bindings, output sinks.
     *
     * <p>Fetched rather than enumerated. A vocabulary copied into a client goes
     * stale silently, and it goes stale in the permissive direction.
     */
    public Map<String, Object> grammar() {
        return call("GET", "/grammar", null);
    }

    /** Register a model. Every field is required by the platform, not here. */
    public Map<String, Object> registerModel(Map<String, Object> model) {
        return call("POST", "/models", model);
    }

    /** One model, resolved by URN or by short name. */
    public Map<String, Object> model(String urn) {
        return call("GET", "/models/" + encode(shortName(urn)), null);
    }

    /**
     * Resolve a warrant into a signed descriptor.
     *
     * <p>Read {@code signature} before acting on one, and read
     * {@code GET /warrant-signing} once before writing the check: a MAYA
     * signature is HMAC with a key derived from the audience, so it proves the
     * descriptor was sealed by a holder of <i>your</i> key and confines a
     * compromise to you. It does not prove authorship to a third party.
     */
    public Map<String, Object> resolve(String urn, String environment,
                                       String principal, String declaredUse) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("urn", urn);
        body.put("environment", environment);
        body.put("principal", principal);
        body.put("declared_use", declaredUse);
        return call("POST", "/resolve", body);
    }

    /**
     * Collect this audience's warrant signing key.
     *
     * <p>The only call here that returns a secret. It verifies warrants whose
     * {@code authority.principal} is exactly this audience and nothing else,
     * which is the point — and MAYA cannot tell whether you stored it safely.
     */
    public Map<String, Object> warrantSigningKey(String audience) {
        return call("POST", "/warrant-signing/key", null,
                    Map.of("audience", audience));
    }

    // ---------------------------------------------------------- artifacts
    /**
     * Upload an artifact, hashing it <b>before</b> it is sent.
     *
     * <p>The platform checks what arrived against what was meant, so a
     * truncated upload is refused rather than stored under the address of
     * whatever turned up. Letting the server hash whatever it received makes
     * the check tautological — it would be comparing a file against itself.
     */
    public Map<String, Object> putArtifact(Path file, String format) {
        String digest = sha256(file);
        byte[] content;
        try {
            content = Files.readAllBytes(file);
        } catch (IOException exc) {
            throw new IllegalArgumentException(
                    "cannot read " + file + " to upload it", exc);
        }
        String requestId = UUID.randomUUID().toString().replace("-", "")
                .substring(0, 16);
        URI uri = URI.create(baseUrl + API + "/artifacts"
                             + query(Map.of("format", format,
                                            "digest", digest)));
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(timeout)
                .header("Authorization", authorization)
                .header("Content-Type", "application/octet-stream")
                .header(REQUEST_HEADER, requestId)
                .POST(HttpRequest.BodyPublishers.ofByteArray(content))
                .build();
        try {
            HttpResponse<String> response = http.send(
                    request, HttpResponse.BodyHandlers.ofString());
            lastRequestId = response.headers()
                    .firstValue(REQUEST_HEADER).orElse(requestId);
            if (response.statusCode() >= 400) {
                throw refusal(response.statusCode(), response.body());
            }
            return Json.object(response.body());
        } catch (IOException | InterruptedException exc) {
            if (exc instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            throw new Unreachable(
                    "MAYA did not answer the artifact upload. Do NOT retry "
                    + "blindly: the upload may have succeeded", exc);
        }
    }

    /** The SHA-256 of a file, as the platform spells digests. */
    public static String sha256(Path file) {
        try {
            MessageDigest sha = MessageDigest.getInstance("SHA-256");
            try (InputStream in = Files.newInputStream(file)) {
                byte[] buffer = new byte[1 << 16];
                int read;
                while ((read = in.read(buffer)) > 0) {
                    sha.update(buffer, 0, read);
                }
            }
            return "sha256:" + HexFormat.of().formatHex(sha.digest());
        } catch (IOException | NoSuchAlgorithmException exc) {
            throw new IllegalArgumentException(
                    "cannot hash " + file, exc);
        }
    }

    // ------------------------------------------------------------ datasets
    /**
     * Stream a featureset version's rows into a sink.
     *
     * <p><b>Never materialised.</b> A method returning a list of records is
     * convenient until the first real dataset, at which point it is an
     * out-of-memory error inside somebody else's job. The response is written
     * through as it arrives and the caller owns the sink.
     *
     * @param format {@code arrow}, {@code parquet}, {@code ndjson} or {@code csv}
     * @return the number of bytes written
     */
    public long streamFeaturesetData(String name, int version, String format,
                                     OutputStream sink) {
        String requestId = UUID.randomUUID().toString().replace("-", "")
                .substring(0, 16);
        URI uri = URI.create(baseUrl + API + "/featuresets/" + encode(name)
                             + "/versions/" + version + "/data"
                             + query(Map.of("format", format)));
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(timeout)
                .header("Authorization", authorization)
                .header(REQUEST_HEADER, requestId)
                .GET()
                .build();
        try {
            HttpResponse<InputStream> response = http.send(
                    request, HttpResponse.BodyHandlers.ofInputStream());
            lastRequestId = response.headers()
                    .firstValue(REQUEST_HEADER).orElse(requestId);
            try (InputStream in = response.body()) {
                if (response.statusCode() >= 400) {
                    throw refusal(response.statusCode(),
                                  new String(in.readAllBytes(),
                                             StandardCharsets.UTF_8));
                }
                byte[] buffer = new byte[1 << 16];
                long total = 0;
                int read;
                while ((read = in.read(buffer)) > 0) {
                    sink.write(buffer, 0, read);
                    total += read;
                }
                return total;
            }
        } catch (IOException | InterruptedException exc) {
            if (exc instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            throw new Unreachable(
                    "MAYA did not answer, or the stream broke partway. "
                    + "Whatever reached the sink is incomplete", exc);
        }
    }

    // ------------------------------------------------------------- helpers
    /**
     * The short name from a URN, accepting either spelling.
     *
     * <p>A caller reads the full URN off a warrant and the short name off a
     * URL. Making them convert produces a 404 whose cause is a string format,
     * which is a bad afternoon for no reason.
     */
    public static String shortName(String urn) {
        if (urn == null) {
            return "";
        }
        String trimmed = urn.trim();
        return trimmed.startsWith("maya://model/")
                ? trimmed.substring("maya://model/".length()) : trimmed;
    }

    /** Whether this method may be retried after a timeout. */
    public static boolean mayRetry(String method) {
        return IDEMPOTENT.contains(method.toUpperCase(java.util.Locale.ROOT));
    }
}
