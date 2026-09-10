# ============================================================ CH 23
_state["chapter"] = "23 · Cross-cutting and Operations"

sl, y = content("One transaction, one record, and the window between them",
                "Cross-cutting · consistency and concurrency")
h = code(sl, ML, y, CW * 0.52, [
 "with db.transaction() as tx:      # re-entrant: a nested",
 "    ...                           # call JOINS this one",
 "",
 "# Called in exactly ONE place in core/ --",
 "# EvidenceEngine.append -- and in no service",
 "# and no route.",
], fs=10, title="db/database.py")
tf = txt(sl, ML, y + h + 0.26, CW * 0.52, 2.6)
runs(tf, [("That is the honest state of DR-4. ", CRIMSON, True),
          ("Every governance act is two commits: the state change, then the evidence node. The window between "
           "them is small and it is not zero, and what falls into it is a model that exists with no record of "
           "its registration — which matters more than a missing row, because segregation of duties is decided "
           "by reading the chain. The mechanism to close it exists and is re-entrant by construction; nothing "
           "uses it.", INK, False)],
     size=10.5, first=True, space_after=9, line=1.24)
runs(tf, [("No outbox, no broker, no migrations. ", CRIMSON, True),
          ("No domain event leaves the process; consumers integrate by polling the API. Schema evolution is "
           "expand-and-contract from one typed schema, 51 tables, one database and one flat evidence "
           "chain — there is no separate audit database, for the reason chapter 7 gives.", INK, False)],
     size=10.5, line=1.24)
x = ML + CW * 0.56
tf = txt(sl, x, y, CW * 0.44, 0.32)
para(tf, "What actually holds when two things happen at once", size=12,
     color=CRIMSON, bold=True, font=SERIF, first=True, space_after=0)
data = [["Hazard", "What holds"],
        ["Two governance acts appending evidence", "Read-then-write, now inside a transaction and retried with JITTERED backoff. Measured before the fix at four threads: 7% of appends raised"],
        ["Two versions with the same semver", "UNIQUE (model_id, semver), refused above it so the message is a sentence"],
        ["The same artifact twice", "Content addressing — the same bytes are the same name"],
        ["A telemetry batch twice", "UNIQUE over the digest of the batch's own rows"],
        ["A scheduler job twice", "Each job re-derives its condition; two replicas raise one finding"],
        ["A notification twice", "Digest of the work described, suppressed if unchanged — and delivery is NOT transactional, which is the one genuine gap"]]
th = table(sl, data, x, y + 0.36, CW * 0.44, col_w=[1.9, 3.9], row_h=0.28,
           fs=8.5, hfs=9, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, x, y + 0.36 + th + 0.16, CW * 0.44, 0.50)
runs(tf, [("Absent: ", CRIMSON, True),
          ("Idempotency-Key, a replay window, an advisory lock, an optimistic-concurrency header, and any "
           "cache to invalidate. With one process each is cheap to add and none is there.", INK, False)],
     size=9.5, first=True, space_after=0, line=1.20)

sl, y = content("312 refusal codes, 14 statuses, one table",
                "Cross-cutting · never a bare 500")
data = [["Code", "HTTP", "Meaning", "Client action"],
        ["validation_failed", "422", "Payload or manifest invalid", "Fix and retry"],
        ["grammar_violation", "422", "The warrant document breaks one of L-W0…L-W13", "Read the named law and the field"],
        ["boundary_violation", "422", "Inputs outside the declared operating boundary", "Refer, or widen the assumption"],
        ["illegal_transition", "409", "The lifecycle does not admit this move", "Follow the remediation"],
        ["rule_unreachable", "422", "A rule an earlier rule already covers", "Reorder or delete the shadowed rule"],
        ["anchor_disagreement", "409", "The chain and the heads written outside it no longer agree", "Stop — a security event, not a bad request"],
        ["no_entitlement", "403", "No grant for this principal and use", "Request a grant"],
        ["segregation_of_duties", "403", "You may not act twice on the same object", "Somebody else acts"],
        ["restricted", "423", "A blocking finding or a suspension", "Remediate, or break-glass"],
        ["revoked", "410", "The warrant is revoked", "Stop — do not retry"],
        ["provider_unavailable", "501", "This instance was never wired to a provider", "A deployment decision, not a transient fault"],
        ["fibration_incomplete", "503", "A model class with no fibre reached HTTP", "This instance is not fit to answer"]]
th = table(sl, data, ML, y, CW, col_w=[2.4, 0.9, 4.9, 3.4], row_h=0.26, fs=9.5, hfs=10,
           bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, ML, y + th + 0.20, CW, 0.80)
runs(tf, [("Three fields, always: error, detail, remediation. ", CRIMSON, True),
          ("The code says what was refused, the detail says what was violated, and the remediation says what to "
           "do — not what went wrong. The status is a decision about who must act rather than about who is at "
           "fault, which is why provider_unavailable is 501 and not 503. 133 of the 312 are 422, 70 are 409, "
           "35 are 403, 28 are 404. test_refusal_discipline.py asserts that every code maps to a status and "
           "that none is mapped twice.", INK, False)],
     size=10.5, first=True, space_after=0, line=1.24)

sl, y = content("Operations — what is measured, and what is a target",
                "Operations · the honest inventory")
tf = txt(sl, ML, y, CW * 0.48, 0.32)
para(tf, "Built", size=12, color=INK, bold=True, font=SERIF, first=True, space_after=0)
data = [["Surface", "What it does"],
        ["/health, /health/live", "Trivial liveness"],
        ["/health/ready", "Includes the evidence chain and its anchors — a chain that does not verify returns 503, because the assurance claims cannot be trusted"],
        ["25 scheduler jobs", "Each idempotent, each re-deriving its own condition; anchoring and full chain verification are two of them"],
        ["One logger, one format", "Request id and acting principal on every line; a refusal is logged at WARNING because it is a governance decision"],
        ["The scale suite", "19 tests, marked scale and excluded by default. It asserts COMPLEXITY, not milliseconds — doubling the estate must not more than double the work"],
        ["test_laws.py", "Eighteen of the twenty-one foundational laws are executable and run as tests; the three that do not are named with the reason. All fourteen warrant laws run before a signature"]]
th = table(sl, data, ML, y + 0.36, CW * 0.48, col_w=[1.6, 4.4], row_h=0.30,
           fs=9, hfs=9.5, bold_col0=True, first_col_color=CRIMSON)
x = ML + CW * 0.52
tf = txt(sl, x, y, CW * 0.48, 0.32)
para(tf, "Not built — and named rather than implied", size=12, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=0)
data = [["Claimed elsewhere", "Here"],
        ["SLOs and error budgets", "Every performance figure in the requirements is a TARGET. No load test has been run and no p99 has been measured under concurrency"],
        ["Golden signals, dashboards", "No Prometheus, no OpenTelemetry, no metrics endpoint. What exists is three health probes and a live log at /admin/logs — the last lines the process wrote, filtered by module, request or principal, with every line of one request joined by its id"],
        ["Runbooks", "There are none. Of the ten the design lists, three name a subsystem or a topology that does not exist — outbox lag, cache stampede, regional failover"],
        ["A build that fails", "CI runs the suite in four shards, the seven discipline walkers, the laws, both SQL dialects, ruff and a type checker gating 203 modules, on every push and pull request. Still absent: a coverage gate and any security scanning"]]
th2 = table(sl, data, x, y + 0.36, CW * 0.48, col_w=[1.6, 4.4], row_h=0.30,
            fs=9, hfs=9.5, bold_col0=True, first_col_color=CRIMSON)
cy = y + 0.36 + max(th, th2) + 0.24
rect(sl, ML, cy, CW, 1.05, fill=PARCH)
rect(sl, ML, cy, 0.045, 1.05, fill=CRIMSON)
tf = txt(sl, ML + 0.30, cy + 0.13, CW - 0.6, 0.86)
runs(tf, [("A control asserted and not there is the failure this platform exists to prevent. ", CRIMSON, True),
          ("Which is why this page is a list of absences rather than a page of green targets. The capacity model "
           "— 1,500 models rising to 5,000, 25 M evidence nodes, 80 TB of Delta features — is a sizing "
           "projection and not a measurement, and full chain verification at forty thousand nodes was 2.9 "
           "seconds and 83 MB, which is measured.", INK, False)],
     size=10.5, first=True, space_after=0, line=1.24)
