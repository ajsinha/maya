/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 */
package com.maya.sdk;

/**
 * MAYA did not answer.
 *
 * <p>Deliberately not a {@link Refused}, and this is the distinction the Java
 * contract calls out first. "MAYA said no" and "MAYA did not answer" call for
 * opposite responses — the first is a decision to act on and the second is a
 * retry or an alert — and a client that collapses them will eventually treat an
 * outage as a governance verdict, which is how a whole estate quietly stops
 * being governed for an afternoon.
 */
public class Unreachable extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public Unreachable(String message, Throwable cause) {
        super(message, cause);
    }
}
