/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 */
package com.maya.sdk;

import java.util.Map;

/**
 * A governance decision that went against you.
 *
 * <p>Thrown, never returned. A refusal that comes back as a value is one a
 * caller can ignore by forgetting to look at it, and forgetting to look is the
 * normal case rather than the careless one.
 *
 * <p><b>Three parts, and the third is the one that matters.</b> {@code error}
 * says which refusal; {@code detail} says what happened; {@code remediation}
 * says what to do about it. A naive client keeps the first two and discards the
 * third, which turns every refusal into "policy violation" — a sentence nobody
 * can act on, and the reason people route around a control rather than satisfy
 * it. The platform writes a remediation for every refusal it has; this carries
 * it through.
 *
 * <p><b>And the request id travels with the exception.</b> Without it, "it
 * failed" and "which of the four thousand log lines was mine" are two separate
 * investigations.
 */
public class Refused extends RuntimeException {

    private static final long serialVersionUID = 1L;

    private final int status;
    private final String error;
    private final String detail;
    private final String remediation;
    private final String requestId;

    public Refused(int status, String error, String detail, String remediation,
                   String requestId) {
        super(message(status, error, detail, remediation, requestId));
        this.status = status;
        this.error = error;
        this.detail = detail;
        this.remediation = remediation;
        this.requestId = requestId;
    }

    private static String message(int status, String error, String detail,
                                  String remediation, String requestId) {
        StringBuilder out = new StringBuilder();
        out.append(error == null || error.isBlank()
                   ? "http_" + status : error);
        if (detail != null && !detail.isBlank()) {
            out.append(": ").append(detail);
        }
        if (remediation != null && !remediation.isBlank()) {
            out.append(" — ").append(remediation);
        }
        if (requestId != null && !requestId.isBlank()) {
            out.append("  [request ").append(requestId).append(']');
        }
        return out.toString();
    }

    public int status() {
        return status;
    }

    /** The platform's own code for this refusal, e.g. {@code blocked}. */
    public String error() {
        return error;
    }

    public String detail() {
        return detail;
    }

    /** What to do about it. Show this to whoever hit the refusal. */
    public String remediation() {
        return remediation;
    }

    /** The identifier the server wrote in its own log for this call. */
    public String requestId() {
        return requestId;
    }

    // ------------------------------------------------------------- building
    /**
     * The right subclass for a status.
     *
     * <p>The classes are separated because a caller catches them for different
     * reasons. Catching "not permitted" to fall back to a narrower query is
     * sensible; catching "a finding blocks this" the same way is a client
     * working around a control.
     */
    static Refused of(int status, Map<String, Object> body, String rawBody,
                      String requestId) {
        String error = string(body, "error");
        String detail = string(body, "detail");
        String remediation = string(body, "remediation");
        if (error.isBlank() && detail.isBlank()) {
            // A proxy answered, or FastAPI's own validation did. Keep the text
            // rather than reporting an empty refusal — the body is the only
            // thing that says what happened.
            detail = rawBody == null ? "" : rawBody;
        }
        return switch (status) {
            case 401 -> new NotAuthenticated(status, error, detail,
                                             remediation, requestId);
            case 403 -> new NotPermitted(status, error, detail, remediation,
                                         requestId);
            case 404 -> new NotFound(status, error, detail, remediation,
                                     requestId);
            case 409, 410, 423 -> new Blocked(status, error, detail,
                                              remediation, requestId);
            default -> new Refused(status, error, detail, remediation,
                                   requestId);
        };
    }

    @SuppressWarnings("unchecked")
    private static String string(Map<String, Object> body, String key) {
        if (body == null) {
            return "";
        }
        Object value = body.get(key);
        if (value == null && body.get("detail") instanceof Map) {
            // The platform nests its problem document under `detail` when
            // FastAPI raises the HTTPException. Look through it rather than
            // reporting a refusal with no remediation.
            value = ((Map<String, Object>) body.get("detail")).get(key);
        }
        return value == null ? "" : String.valueOf(value);
    }

    /** No credentials, or they did not verify. */
    public static class NotAuthenticated extends Refused {
        private static final long serialVersionUID = 1L;

        NotAuthenticated(int s, String e, String d, String r, String id) {
            super(s, e, d, r, id);
        }
    }

    /** Authenticated, and not allowed to do this. */
    public static class NotPermitted extends Refused {
        private static final long serialVersionUID = 1L;

        NotPermitted(int s, String e, String d, String r, String id) {
            super(s, e, d, r, id);
        }
    }

    /** No such thing — or nothing you are scoped to see. */
    public static class NotFound extends Refused {
        private static final long serialVersionUID = 1L;

        NotFound(int s, String e, String d, String r, String id) {
            super(s, e, d, r, id);
        }
    }

    /**
     * A governance condition stands in the way.
     *
     * <p>An open blocking finding, a quorum not met, an attested record that
     * cannot take a new version. These are the platform working, not failing.
     */
    public static class Blocked extends Refused {
        private static final long serialVersionUID = 1L;

        Blocked(int s, String e, String d, String r, String id) {
            super(s, e, d, r, id);
        }
    }
}
