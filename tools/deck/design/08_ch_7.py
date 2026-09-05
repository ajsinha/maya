# ============================================================ CH 7
divider("7", "Interfaces", "One API, consumed identically by the UI, the SDK and every engine.",
        ["API conventions", "Resource surface", "Front-end design", "SDK and events"])

sl, y = content("API conventions", "Interfaces · the contract")
data = [["Concern", "Decision", "Why"],
        ["Base", "/api/v1, OpenAPI 3.1, JSON", "One versioned contract; the UI has no privileged path"],
        ["Errors", "RFC 9457 problem+json with code, deny_reason[], remediation_url", "DR-6 and DR-7 — blocking must always explain"],
        ["Pagination", "Keyset with cursor / next_cursor", "Stable paging over 50,000 models"],
        ["Concurrency", "ETag + If-Match; 412 returns a field-level diff", "The UI shows a real conflict dialog instead of overwriting"],
        ["Idempotency", "Idempotency-Key on POST, 24-hour replay window", "Safe retry on flaky networks — DR-3"],
        ["Shaping", "?expand= and ?fields=", "One request per screen instead of N+1 chatter"],
        ["Derivations", "GET /derivations/{id} on every derived value", "Powers the universal [why?] affordance"],
        ["Time travel", "?as_of= on inventory reads", "Examiner questions about a past date"],
        ["Events", "GET /events (SSE)", "Task inbox, breaches, job progress without polling"],
        ["Deprecation", "Two minor versions of overlap; Sunset headers", "Clients are never surprised"]]
table(sl, data, ML, y, CW, col_w=[1.9, 4.6, 5.1], row_h=0.325, fs=10.5, bold_col0=True, first_col_color=CRIMSON)

sl, y = content("Resource surface", "Interfaces · endpoints")
data = [["Group", "Endpoints"],
        ["Models", "/models · /models/{urn} · /uses · /assumptions · /limitations · /relationships · /blast-radius · /scope-determinations"],
        ["Versions", "/models/{urn}/versions · /versions/{id} · /compare · /contract · /reproducibility"],
        ["Aliases", "/models/{urn}/environments/{env}/aliases/{name} · /history"],
        ["Risk", "/models/{urn}/assessments · /assessments/{id} · /tiering/rulesets · /tiering/simulate"],
        ["Features", "/features · /feature-views · /feature-views/{id}/versions · /contracts · /training-sets"],
        ["Runs", "/runs · /runs/{id}/metrics · /artifacts · /runs/{id}/replay"],
        ["Validation", "/validations · /validations/{id}/tests · /findings · /findings/{id}/remediation"],
        ["Overlays", "/overlays · /overlays/{id}/measurements"],
        ["Monitoring", "/monitors · /observations · /breaches · /health/{urn}"],
        ["Warrants", "/warrants · /v1/resolve (warrant service) · /warrants/{id}/revoke · /telemetry"],
        ["Documents", "/documents/compile · /documents/{id} · /documents/{id}/render · /export-packs"],
        ["Policy", "/policies · /policies/evaluate · /obligations"],
        ["Assistance", "/ai/capabilities · /ai/{capability}/draft · /ai/generations/{id}/attest"],
        ["Admin", "/model-classes · /lifecycles · /templates · /regimes · /connectors · /users"]]
table(sl, data, ML, y, CW, col_w=[1.8, 9.8], row_h=0.275, fs=10, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)

sl, y = content("Single sign-on — and the part of it that is not mechanical",
                "Interfaces · identity")
tf = txt(sl, ML, y, CW * 0.52, 0.35)
para(tf, "The mechanical half", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=0)
h = code(sl, ML, y + 0.40, CW * 0.52, [
 "# authorisation code + PKCE + state + nonce",
 "recovered = pow(sig, e, n)",
 "expected  = b\"\\x00\\x01\" + b\"\\xff\" * pad + b\"\\x00\" \\",
 "          + SHA256_DIGEST_INFO + digest",
 "return hmac.compare_digest(recovered, expected)",
 "",
 "# and the algorithm is DECIDED, never read:",
 "if header[\"alg\"] != \"RS256\": raise unsupported",
], fs=9, title="core/authz/jws.py — standard library only")
tf = txt(sl, ML, y + 0.40 + h + 0.24, CW * 0.52, 2.0)
bullets(tf, [("CONSTRUCT the padded block, never parse what you recover",
              "that is the difference between correct PKCS#1 v1.5 and the Bleichenbacher forgery, which works precisely against verifiers that parse"),
             ("Decide the algorithm; do not read alg from the token",
              "the other famous way a JWT is accepted with no signature at all"),
             ("No crypto dependency, by design",
              "a governance system that cannot be deployed air-gapped is one somebody works around — the same reason every front-end asset is vendored")],
        size=10.5, gap=7, indent_size=9.5)
x = ML + CW * 0.56
tf = txt(sl, x, y, CW * 0.44, 0.35)
para(tf, "The half that is not", size=12.5, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=0)
tf = txt(sl, x, y + 0.42, CW * 0.44, 1.15)
runs(tf, [("An identity provider that grants MAYA roles is one that ", INK, False),
          ("decides segregation of duties", CRIMSON, True),
          (" — and the person administering it is very often the person whose duties are being segregated.",
           INK, False)], size=11.5, first=True, space_after=0, line=1.26)
data = [["Rule", "Because"],
        ["Groups are MAPPED, never obeyed",
         "An unmapped group grants nothing"],
        ["Identity binds to (issuer, subject)",
         "A username is not an identity: claiming to be called admin once made you one"],
        ["Incompatible roles refuse the LOGIN",
         "Checked before provisioning, so the lesser problem cannot hide the greater"],
        ["Issuer, subject and groups recorded",
         "“Why did they hold that role in March” survives the directory moving on"]]
# row_h is a FLOOR, not a height: theme.table() adds padding plus one text line
# on top of it, so a generous floor makes every row taller than its content and
# the table taller than its slide. Let the content decide.
th = table(sl, data, x, y + 1.55, CW * 0.44, col_w=[2.2, 3.1], row_h=0.34, fs=8.5, hfs=9,
           bold_col0=True, first_col_color=CRIMSON)
cy = y + 1.55 + th + 0.20
rect(sl, ML, cy, CW, 0.62, fill=PARCH)
rect(sl, ML, cy, 0.045, 0.62, fill=CRIMSON)
tf = txt(sl, ML + 0.30, cy + 0.10, CW - 0.6, 0.50)
runs(tf, [("No SAML and no SCIM. ", CRIMSON, True),
          ("OIDC is supported; a SAML-only directory and automatic deprovisioning are not, so ", INK, False),
          ("a leaver is suspended by hand", INK, True),
          (" — which is an operational obligation worth stating here rather than discovering in an access review.", INK, False)],
     size=11, first=True, space_after=0, line=1.24)

sl, y = content("Front end and SDK", "Interfaces · clients")
tf = txt(sl, ML, y, CW * 0.47, 0.35)
para(tf, "maya-web — a separate process", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=0)
data = [["Concern", "Design"],
        ["Auth", "OIDC + PKCE; access token in memory only; refresh via __Host- SameSite=Strict cookie"],
        ["Logic", "P4′ — the client renders decisions, never derives them"],
        ["Client", "Generated from OpenAPI; pinned by openapi.lock.json; drift fails the build"],
        ["Forms", "Generated in-browser from the fibre's JSON Schema — a new model class needs no front-end release"],
        ["Documents", "Fetched as server-rendered HTML/PDF, never assembled client-side"]]
table(sl, data, ML, y + 0.40, CW * 0.47, col_w=[1.3, 4.4], row_h=0.44, fs=10, hfs=10.5, bold_col0=True, first_col_color=CRIMSON)
x = ML + CW * 0.53
tf = txt(sl, x, y, CW * 0.47, 0.35)
para(tf, "SDK — the compliant path must be the shortest", size=12.5, color=INK, bold=True, font=SERIF, first=True, space_after=0)
tf = txt(sl, x, y + 0.42, CW * 0.47, 2.0)
bullets(tf, ["Resolve and verify the descriptor signature",
             "Fetch features per the contract; check freshness",
             "Check operating boundaries before scoring",
             "Emit signed telemetry",
             "Maintain the local revocation list"], size=11.5, gap=7)
rect(sl, x, y + 2.35, CW * 0.47, 1.35, fill=PARCH)
rect(sl, x, y + 2.35, 0.045, 1.35, fill=CRIMSON)
tf = txt(sl, x + 0.26, y + 2.49, CW * 0.47 - 0.5, 1.1)
runs(tf, [("The design point. ", CRIMSON, True),
          ("A developer who uses the SDK gets governance for free and cannot forget a step. If the compliant path is slower than "
           "the non-compliant one, the inventory rots — so the SDK ships in Phase 1, not later.", INK, False)],
     size=11.5, first=True, space_after=0, line=1.26)
