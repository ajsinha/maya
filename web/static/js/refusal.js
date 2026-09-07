/* MAYA — one reading of a refusal body, for every screen.
 *
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 *
 * Three screens each had their own version of this and all three did
 * `escapeHtml(body.detail)`. On a MAYA refusal `detail` is a sentence and that
 * works. On a VALIDATION error it is not: FastAPI answers 422 with
 *
 *     {"detail": [{"type": "missing", "loc": ["body", "purpose_class"],
 *                  "msg": "Field required", "input": {...}}]}
 *
 * and an array of objects rendered as a string is the literal text
 * "[object Object]". So typing a letter into a number box, leaving a required
 * field blank, or sending a field the schema does not know — the three
 * commonest things a person does wrong — produced "Refused — [object Object]"
 * on every authoring screen in the platform. The API said exactly which field
 * and why; the interface threw it away.
 *
 * This normalises every shape the server can send into one object, so a screen
 * renders rather than decides.
 */
(function () {
  "use strict";

  function fieldOf(loc) {
    /* ["body", "kernel", "input_schema", 0, "dtype"] -> "kernel.input_schema[0].dtype".
       The leading "body"/"query" is dropped: somebody looking at a form knows
       where they typed. */
    var parts = (loc || []).slice();
    if (parts.length && (parts[0] === "body" || parts[0] === "query"
                         || parts[0] === "path")) {
      parts = parts.slice(1);
    }
    return parts.reduce(function (out, part) {
      if (typeof part === "number") { return out + "[" + part + "]"; }
      return out ? out + "." + part : String(part);
    }, "");
  }

  function fromValidationErrors(errors) {
    return errors.map(function (e) {
      var field = fieldOf(e.loc);
      var message = e.msg || e.type || "is not acceptable";
      return field ? field + " — " + message : message;
    });
  }

  /* Returns {code, lines, remediation}. `lines` is never empty and never
     contains an object; a screen may join them however it likes. */
  function read(xhr) {
    var body = (xhr && (xhr.responseJSON
                        || (xhr.response && typeof xhr.response === "object"
                            ? xhr.response : null))) || {};
    var detail = body.detail;
    var lines;

    if (Array.isArray(detail)) {
      lines = fromValidationErrors(detail);
    } else if (detail && typeof detail === "object") {
      /* An HTTPException raised with a dict. Its own `detail` is the sentence. */
      lines = [String(detail.detail || detail.msg || JSON.stringify(detail))];
      body = { error: detail.error || body.error,
               remediation: detail.remediation || body.remediation };
    } else if (typeof detail === "string" && detail) {
      lines = [detail];
    } else {
      lines = [(xhr && xhr.statusText) || "refused"];
    }

    return {
      code: body.error || "",
      lines: lines.length ? lines : ["refused"],
      remediation: body.remediation || "",
      status: (xhr && xhr.status) || 0
    };
  }

  window.MAYA = window.MAYA || {};
  window.MAYA.refusal = { read: read, fieldOf: fieldOf };
}());
