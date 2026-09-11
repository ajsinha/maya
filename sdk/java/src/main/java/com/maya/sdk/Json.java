/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 */
package com.maya.sdk;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Just enough JSON, written out rather than depended on.
 *
 * <p>The reason is the same one that keeps every front-end asset vendored: a
 * governance platform that cannot be deployed air-gapped is one somebody works
 * around, and an SDK with a dependency tree moves that problem into the
 * client's build rather than solving it. Asking a bank's platform team to get
 * a JSON library through approval so that a service can call the register is a
 * larger cost than these two hundred lines.
 *
 * <p>What this is not: a general JSON library. It reads what MAYA answers and
 * writes what MAYA accepts. It does not stream, it has no object mapping, and
 * it makes no attempt to be fast — a governance call is a governance call, and
 * the parsing is never the expensive part of one.
 */
public final class Json {

    private Json() {
    }

    // ------------------------------------------------------------- reading
    /** Parse a document. Returns Map, List, String, Double, Boolean or null. */
    public static Object parse(String text) {
        Reader reader = new Reader(text);
        reader.skipWhitespace();
        Object value = reader.value();
        reader.skipWhitespace();
        if (!reader.done()) {
            throw new IllegalArgumentException(
                    "trailing content after the JSON value at " + reader.at());
        }
        return value;
    }

    /**
     * Parse, expecting an object.
     *
     * <p>A 502 from a proxy answers in HTML. A client that threw a parse error
     * over it would replace a legible failure with an illegible one at exactly
     * the moment somebody is trying to find out what happened, so the caller
     * gets the chance to keep the text.
     */
    @SuppressWarnings("unchecked")
    public static Map<String, Object> object(String text) {
        Object parsed = parse(text);
        if (!(parsed instanceof Map)) {
            throw new IllegalArgumentException(
                    "expected a JSON object, got " + describe(parsed));
        }
        return (Map<String, Object>) parsed;
    }

    private static String describe(Object value) {
        if (value == null) {
            return "null";
        }
        return value.getClass().getSimpleName().toLowerCase();
    }

    // ------------------------------------------------------------- writing
    /** Serialise a Map, List, String, Number, Boolean or null. */
    public static String write(Object value) {
        StringBuilder out = new StringBuilder();
        writeValue(value, out);
        return out.toString();
    }

    private static void writeValue(Object value, StringBuilder out) {
        if (value == null) {
            out.append("null");
        } else if (value instanceof String s) {
            writeString(s, out);
        } else if (value instanceof Boolean || value instanceof Number) {
            out.append(value);
        } else if (value instanceof Map<?, ?> map) {
            out.append('{');
            boolean first = true;
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!first) {
                    out.append(',');
                }
                first = false;
                writeString(String.valueOf(entry.getKey()), out);
                out.append(':');
                writeValue(entry.getValue(), out);
            }
            out.append('}');
        } else if (value instanceof Iterable<?> items) {
            out.append('[');
            boolean first = true;
            for (Object item : items) {
                if (!first) {
                    out.append(',');
                }
                first = false;
                writeValue(item, out);
            }
            out.append(']');
        } else {
            throw new IllegalArgumentException(
                    "cannot serialise " + value.getClass().getName()
                    + ". This client sends maps, lists and primitives; an "
                    + "object mapper would be a second description of the "
                    + "platform's schemas, able to disagree with the first");
        }
    }

    private static void writeString(String text, StringBuilder out) {
        out.append('"');
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                case '\b' -> out.append("\\b");
                case '\f' -> out.append("\\f");
                default -> {
                    if (c < 0x20) {
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        out.append('"');
    }

    // -------------------------------------------------------- the recursive
    private static final class Reader {
        private final String text;
        private int index;

        Reader(String text) {
            this.text = text;
        }

        boolean done() {
            return index >= text.length();
        }

        String at() {
            return "offset " + index;
        }

        void skipWhitespace() {
            while (index < text.length()
                    && Character.isWhitespace(text.charAt(index))) {
                index++;
            }
        }

        Object value() {
            skipWhitespace();
            if (done()) {
                throw new IllegalArgumentException("the document ends early");
            }
            char c = text.charAt(index);
            return switch (c) {
                case '{' -> readObject();
                case '[' -> readArray();
                case '"' -> readString();
                case 't', 'f' -> readBoolean();
                case 'n' -> readNull();
                default -> readNumber();
            };
        }

        private Map<String, Object> readObject() {
            Map<String, Object> out = new LinkedHashMap<>();
            index++;                                // past '{'
            skipWhitespace();
            if (!done() && text.charAt(index) == '}') {
                index++;
                return out;
            }
            while (true) {
                skipWhitespace();
                String key = readString();
                skipWhitespace();
                expect(':');
                out.put(key, value());
                skipWhitespace();
                if (done()) {
                    throw new IllegalArgumentException("unterminated object");
                }
                char c = text.charAt(index++);
                if (c == '}') {
                    return out;
                }
                if (c != ',') {
                    throw new IllegalArgumentException(
                            "expected ',' or '}' at " + (index - 1));
                }
            }
        }

        private List<Object> readArray() {
            List<Object> out = new ArrayList<>();
            index++;                                // past '['
            skipWhitespace();
            if (!done() && text.charAt(index) == ']') {
                index++;
                return out;
            }
            while (true) {
                out.add(value());
                skipWhitespace();
                if (done()) {
                    throw new IllegalArgumentException("unterminated array");
                }
                char c = text.charAt(index++);
                if (c == ']') {
                    return out;
                }
                if (c != ',') {
                    throw new IllegalArgumentException(
                            "expected ',' or ']' at " + (index - 1));
                }
            }
        }

        private String readString() {
            expect('"');
            StringBuilder out = new StringBuilder();
            while (true) {
                if (done()) {
                    throw new IllegalArgumentException("unterminated string");
                }
                char c = text.charAt(index++);
                if (c == '"') {
                    return out.toString();
                }
                if (c != '\\') {
                    out.append(c);
                    continue;
                }
                char escape = text.charAt(index++);
                switch (escape) {
                    case '"' -> out.append('"');
                    case '\\' -> out.append('\\');
                    case '/' -> out.append('/');
                    case 'n' -> out.append('\n');
                    case 'r' -> out.append('\r');
                    case 't' -> out.append('\t');
                    case 'b' -> out.append('\b');
                    case 'f' -> out.append('\f');
                    case 'u' -> {
                        out.append((char) Integer.parseInt(
                                text.substring(index, index + 4), 16));
                        index += 4;
                    }
                    default -> throw new IllegalArgumentException(
                            "unknown escape \\" + escape);
                }
            }
        }

        private Boolean readBoolean() {
            if (text.startsWith("true", index)) {
                index += 4;
                return Boolean.TRUE;
            }
            if (text.startsWith("false", index)) {
                index += 5;
                return Boolean.FALSE;
            }
            throw new IllegalArgumentException("expected a boolean at " + index);
        }

        private Object readNull() {
            if (!text.startsWith("null", index)) {
                throw new IllegalArgumentException("expected null at " + index);
            }
            index += 4;
            return null;
        }

        private Double readNumber() {
            int start = index;
            while (index < text.length()
                    && "-+.eE0123456789".indexOf(text.charAt(index)) >= 0) {
                index++;
            }
            if (start == index) {
                throw new IllegalArgumentException(
                        "unexpected character '" + text.charAt(index)
                        + "' at " + index);
            }
            return Double.valueOf(text.substring(start, index));
        }

        private void expect(char c) {
            if (done() || text.charAt(index) != c) {
                throw new IllegalArgumentException(
                        "expected '" + c + "' at " + index);
            }
            index++;
        }
    }
}
