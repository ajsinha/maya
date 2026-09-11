# 13 — Machine assistance: admitted by the check, never by the model

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

> **What this document is.** The rest of the specification treats AI as something the platform
> **governs**. This one treats AI as something the platform **uses**, and takes a position on where
> that is a good idea, where it is a bad idea, and why the line falls in a place the formalism can
> draw rather than a place a committee has to.
>
> It is an argued position. Where the popular answer is wrong, it says so.

---

## 1. The criterion, and why it is not a judgement about models

Most enterprise AI strategies sort use cases by *value* and bolt on controls. That produces the
familiar shape: an impressive pilot, a governance review that cannot say anything more specific than
*"a human should check it"*, and a production system whose failure mode is that nobody checks.

There is a better sorting criterion available here, and it is a theorem rather than a preference.
[00 §12a](00-mathematical-foundations.md) states it:

> **Definition (oracle).** For a task `T` with outputs in `O`, an *oracle* is a decidable predicate
> `ok_T : O → 𝔹`, computable from the formal structure and from data independent of the output, such
> that `ok_T(o)` holds only if `o` is correct.
>
> **Proposition (automation admissibility).** If `T` is oracle-backed, the soundness of *verified
> automation* — compute `g(x)`, accept iff `ok_T(g(x))` — is **independent of the generator `g`**. No
> incorrect output is accepted, whatever produced it. The generator's error rate determines
> *throughput*, not correctness.

Two consequences follow, and both are unusual enough to be worth stating plainly.

**The question is never "is the model good enough".** Where an oracle exists, that question does not
arise: a wrong output is rejected, and a model that is wrong more often merely wastes more attempts.
Where no oracle exists, the correctness of the output is exactly the correctness of `g`, and "the
model is quite good now" is the only argument available — which is not an argument a bank can put in
front of an examiner.

**The criterion is a property of the domain, not of the vendor.** It does not change when the base
model changes. That is why this document does not have a section on model selection.

Where a check exists, a language model can be wrong **loudly and cheaply** and the system catches it.
Where no check exists, it is wrong **quietly** — and in a governance system, quiet wrongness is the
failure mode that matters, because the whole product is the claim that its assertions are derivable.

So this document is organised **by check**, not by use case. §2 is what the checks admit, §3 is the
checks that exist, §4 is the path an output takes through them, and §9 is what the criterion admits
that nobody has built.

---

## 2. Two tiers, and the third one is not a tier

| | Tier A — **verified** | Tier B — **grounded** |
|---|---|---|
| **The control** | A formal property passes or fails. The check *is* the control | Every claim cites evidence, every citation is verified, a person approves what survives |
| **Autonomy** | Human-approved automation | Human-approved automation, or collaborative assistance |
| **If the model degrades** | The check fails and nothing is recorded | Citations fail and the claims are removed |
| **Refusal on failure** | `oracle_failed` — nothing is recorded at all | `nothing_grounded` — if no claim survived, there is nothing left to record |

There is a Tier C in the argument — output that can be neither checked nor grounded, where AI may
summarise and surface but never conclude. **It is deliberately not registrable**, and the refusal
says why:

```json
{"error": "advisory_not_registrable",
 "detail": "a capability whose output can be neither checked nor grounded is
            advisory, and advisory AI is a person using a chat window",
 "remediation": "if the output can be checked, name the oracle and register it as
                 Tier A; if its claims can cite evidence, register it as Tier B"}
```

That is a stronger position than the usual one, and the reason is structural rather than cautious:
**a Tier C capability in a registry is a Tier C capability that will one day be wired into a decision
path**, because everything in a registry eventually is. A person using a chat window is fine. A
platform capability that produces unverifiable output and has an owner, a key and an endpoint is a
governance decision waiting for somebody to be in a hurry.

Two further rules are enforced at registration rather than at use, because registration is the
governance act:

- **A Tier A capability must name its oracle** (`oracle_required`). *"We validate the output"* without
  naming the check is the sentence that precedes every AI incident.
- **The named oracle must exist** (`unknown_oracle`), and the refusal lists the ones that do.

Only two autonomy modes are accepted at all: `collaborative_assistance` (a person is doing the work)
and `human_approved_automation` (the machine drafts, a person signs). Those are precisely the two
modes that pass the boundary gates in [09 §9.1](09-security-compliance.md), and this is the one place
in the codebase where that vocabulary is enforced rather than described.

---

## 3. The five oracles that exist

`core/assist/oracles.py`. The list is short because **the honest list is short**.

| Key | Checks | Rests on |
|---|---|---|
| `warrant.conforms` | A generated warrant validates against the grammar and its admissibility laws | `core/execution/grammar` |
| `contract.refines` | A proposed contract refines the incumbent (`L-7`) | `core/domain/contracts` |
| `schemas.substitutable` | Proposed input and output schemas satisfy variance (`L-12`) | `core/domain/schemas` |
| `test.registered` | A proposed validation test exists in the catalogue | `core/validation/catalogue` |
| `citations.resolve` | Every cited evidence node exists — Boolean-semiring citation soundness | `core/evidence` |

**Every one of them is machinery that already existed for another reason, and that is not a
coincidence.** A platform whose properties are formal enough to check a human's work can check a
machine's, and the same check serves both. An oracle written specially to bless AI output would be an
oracle nobody had reason to trust — it would have been designed by the same people, at the same time,
under the same assumptions as the thing it blesses.

`citations.resolve` is the weakest of the five and deliberately so. It asks whether every cited node
*exists*, which is the Boolean-semiring reading. The stronger question — whether the cited set
contains a *minimal support* of the claim under its derivation — is available in principle from
[00 §9.2](00-mathematical-foundations.md) and is **not what runs**. Saying which is the difference
between grounding verification and grounding aspiration, and this is currently nearer the second than
the first.

### 3.1 Two checks that are not registered as oracles, and should be

Regime activation now runs **two** mechanical checks before a regime can be turned on, and both are
exactly the shape the criterion asks for:

- **`L-16` — deontic consistency.** `core/regimes/sentences.py::deontic_conflicts` finds terms one
  sentence obliges and another forbids; activation refuses with `obligation_contradiction`, naming
  the term and both sentences. It is checked **first**, before the satisfaction condition, because it
  is cheaper and because a regime that contradicts itself makes every determination unsatisfiable —
  which the satisfaction condition would report as a subtler failure than it is.
- **`L-8` — the satisfaction condition.** Truth invariant under change of notation, checked against
  probe states.

`L-16` matters more for machine-drafted encodings than for hand-written ones, for a reason worth
naming. It is decidable exactly as far as the sentences **declare their shape**: `obliges`, `forbids`
and `conditional` are structural, and a sentence built from a bare lambda is `custom`. So
`undecidable()` **names** the sentences the check could not read, rather than assuming them
consistent — because a check that quietly ignores what it cannot judge reports success for exactly
the cases it was least able to judge. A model drafting an encoding is the most likely author of a
`custom` sentence, so that report is precisely the list a reviewer of machine output needs.

Neither `L-16` nor `L-8` is in `ORACLES`, because the capability they would back — a regulatory
encoding assistant (§9) — is not built. The checks are ready and the generator is not, which is the
right way round.

---

## 4. The path an output takes

`core/assist/drafting.py` and `core/assist/generations.py`. Five steps, and the **order** is the
design.

```
1  evidence gathered  →  2  prompt assembled  →  3  provider drafts
                                                       ↓
   5  attested by somebody else  ←  4  gate: oracle, then grounding
```

1. **The evidence is gathered first, from the register.** Not from the model, and not from the
   prompt. What the model may cite is fixed **before it is asked**, capped at forty nodes, so a
   citation it invents has nowhere to land. A subject with no evidence recorded against it is refused
   outright (`nothing_to_ground`): *"a subject with no record is one nobody should be drafting
   about."*

2. **The prompt is assembled from that record**, one line per evidence node, each labelled with the
   node's id, and its digest is recorded — so *"what was it asked"* has an answer that survives the
   model moving on. The cap is not an efficiency measure: a prompt carrying the whole chain is a
   prompt nobody can review, and a claim citing one of four thousand nodes is not a citation anybody
   can check.

3. **The provider drafts, and nothing it returns is believed.** It hands back prose and a list of
   claims, each naming the evidence it rests on. A provider cannot introduce a fact — only a
   *candidate* fact, which survives exactly as far as its citation does.

4. **The gate runs, unchanged.** For Tier A the oracle decides, and a failure records **nothing**.
   For Tier B the grounding gate checks every citation and **removes** the claims that failed.

   Removal rather than flagging is the decision worth defending. A document where the unsupported
   sentences are marked is a document where the marks are what gets skimmed past — and the sentence
   still reads as though the platform said it. The rejected claims are kept **separately**, which is a
   far more useful artifact than an annotated draft: it is the list of places the model was making
   things up. A claim citing *nothing* is not grounded either, however true it happens to be; uncited
   prose in a governance document is the thing this gate exists to stop.

5. **It lands `drafted`, and drafted is not evidence.** Not *should not be* — **cannot be**. A drafted
   generation carries no weight anywhere in the platform, and attestation is the only transition that
   gives it any. `self_attestation` refuses the requester: *"attestation is a person taking
   responsibility for machine output; it must be somebody other than whoever asked for it."*

What a reader eventually sees is **assembled from the claims that survived**, not from the provider's
prose. The prose is kept for the record under `as_drafted` and is never shown as the answer.

---

## 5. Which model MAYA can ask

MAYA can now *ask* as well as record, and the ratio is deliberate: **one provider works and three
refuse by name.**

| Provider | State |
|---|---|
| `mock` | Works. Deterministic, seeded from the digest of its own prompt, composing sentences from the evidence it was handed |
| `anthropic`, `openai`, `self_hosted` | Refuse, each naming itself and the reason |

A stub returning plausible prose into a governance register is a machine writing into the record with
nothing behind it, and the first person to see the output would have no way to tell. A refusal that
says which provider, why it cannot run, and what to do instead costs nothing and cannot be mistaken
for an answer.

**Wiring a real provider is not a matter of filling in an HTTP call.** Four things must be answered
first, and none of them is code:

| | |
|---|---|
| **Egress** | Every other asset here is vendored so the platform can be deployed air-gapped. A remote provider is the first component that must reach the internet, and whether it may is a deployment decision rather than a default |
| **Confidentiality** | A prompt assembled from this register carries model inventory, validation findings and exposure figures. What may leave the institution is a question for whoever owns the data, not for a client library |
| **Reproducibility** | A remote model is not deterministic and its weights move under a version string. The warrant grammar already treats `llm.prompt` and `llm.agent` as stochastic runtimes for exactly this reason. What is recorded must be the output and its digest, never *"the model said so"* |
| **Cost and rate limits** | Operational, which is why they are named here rather than discovered in production |

`self_hosted` is listed separately because it answers the first two by construction, and is therefore
the likeliest first real provider rather than the least likely.

**The mock is a real test of the path, not a stand-in for one.** It exercises the capability register,
the oracle, the grounding gate, attestation, edit-distance measurement and automation-bias sampling
for real; only the sentence is fake, and the sentence is the part the platform was never going to
trust. It also, on request, produces **one deliberately ungroundable claim** — a citation that reads
exactly like a real one and names nothing — so the rejection path can be watched doing its job. A
mock that only ever cited real evidence would leave the control that actually matters untested, and
the first ungrounded claim anybody saw would be in production.

---

## 6. The measurements that are not about the output

Two things are measured that say nothing about whether a draft was any good, and they are the most
interesting instrumentation in the package.

**Edit distance on attestation** — how much the reviewer changed, by token overlap. Crude on purpose:
the absolute number means little, and what matters is whether it **falls** for a given reviewer.
`automation_bias(reviewer)` splits their attestations in half and reports the two means; a late mean
under half the early one is flagged: *"this reviewer may have stopped reading."* That is a control
failure the platform can detect **without anybody reporting it**, which is the only way this class of
failure is ever detected.

**A review sample** — a fraction of generations, ten per cent by default, pulled for independent
review regardless of how good they look. Deliberate friction: somebody who has approved forty correct
drafts is not reviewing the forty-first, and no amount of telling them to will change that.

The sampling is **deterministic on the capability's own counter**, seeded from the capability id and
how many generations it has already produced. It was seeded on the clock until somebody noticed, and
that made the docstring false in both halves: the sequence was unrepeatable, so no test could depend
on it, *and* a drafter watching which of their own drafts were sampled could infer the rate and time
around it.

The seed is a digest byte over **256**, not 255 — which is a detail worth one paragraph because it was
wrong, and wrong in the direction this document is about. Over 255.0 a byte lands in `[0, 1]`
*inclusive*, so the byte `0xFF` scores exactly `1.0`, and `1.0 < rate` is false at `rate = 1.0`. A
capability configured to review **every** generation therefore reviewed all but roughly one draw in
256 — and because the seed is fixed by the capability id rather than by a clock, it was not a random
draw that escaped but the same capability's, every time. A stated rate of 1.0 that is not 1.0 is
precisely the failure mode this section exists to detect, arriving in the control that detects it. Over
256.0 the byte lands in `[0, 1)`, a rate of `k/256` draws exactly `k`, and 1.0 means all of them.

---

## 7. What must never happen, and why a credential beats a policy

**AI must never make a governance decision.** Specifically, never:

| Decision | Why not |
|---|---|
| **Assign a risk tier** | The tier is a *derivation* from a versioned rule set over sourced facts. An LLM-assigned tier is unexplainable, unstable across runs, and destroys the chain. It may propose an *input*; it may not produce the output |
| **Conclude a validation** | Effective challenge is defined by SR 26-2 as critical analysis by objective experts with the standing to effect change. A model has no standing, no accountability, and cannot be sanctioned |
| **Make a scope determination** | The whole point of the institutions construction is that scope is a derivation with a citation. Replacing it with a model's opinion discards the most valuable property in the design |
| **Approve anything** | Approval is an accountable human act with a signature behind it |
| **Accept residual risk** | Requires authority. Models do not have authority |
| **Close a finding** | Closure requires independent verification by a person who did not raise it — and that is enforced from the evidence chain ([09 §2.5](09-security-compliance.md)), not by convention |
| **Compute a metric** | Do not ask a language model for a Gini coefficient. Compute it and let the model describe it. This sounds obvious and is violated constantly |

**And AI must never be in the warrant path.** [06](06-warrants-and-execution.md) requires a p99 under
50 ms and deterministic behaviour. Nothing probabilistic goes there.

The formalism explains *why* this list is what it is, rather than leaving it as caution. For a derived
quantity `q = f(Φ)` defined by a versioned rule `f`, there is no automation question about computing
`q` — evaluating `f` is deterministic. The question arises only for supplying `Φ`, which is
oracle-backed when facts come from systems of record, and for **proposing `f`**, which is a normative
choice. Since `f` *constitutes* the standard, no independent specification exists against which a
proposed `f` could be checked. Concluding a validation, granting an approval and accepting residual
risk are in the same class: they have **no notion of correctness independent of the authority
exercising them**. These are not weakly-checkable tasks withheld out of caution.

### The credential, and how weakly it is currently enforced

The right way to hold this line is architectural: **no AI capability holds a credential permitting a
governance state transition.** Policy erodes under commercial pressure from sensible people;
a credential that does not exist does not.

Stated honestly, that is **not yet what the code does**. What is true today:

- the four `assist:*` permissions (`read`, `register`, `generate`, `attest`) are disjoint from every
  governance permission, and none of them can approve, tier, scope or close anything;
- no principal is created for a capability, so a capability holds no credential at all — every call
  is made by a person;
- and there is **no check that would fail** if somebody later gave a capability a principal and
  handed it `version:approve`.

The property holds by construction rather than by enforcement, which means it holds until somebody
changes something. A test asserting that no principal named for a capability holds a governance
permission is the missing piece, and it is missing.

---

## 8. The recursion, honestly scoped

There is an obvious objection: a platform that governs AI, using AI, is either circular or
hypocritical.

It is neither, and the reason is precise rather than rhetorical. [00 §12a](00-mathematical-foundations.md)
puts it as **well-foundedness**: the governing machinery — the tiering map, the evidence structure,
the institutions, the lifecycle categories — is not an element of the governed population; every
assistant is. Where the strata touch, at an assistant drafting a regime encoding, the dependency is
*mediated by an oracle that is not itself machine-produced*.

> **Generation may cross the strata; acceptance may not.**

That is the whole answer, and §4 is the mechanism: a provider produces candidates, a check that
existed before it decides, and a person attests.

### What "self-governance" does and does not mean here

The design commitment is that every AI capability is registered in MAYA's own inventory as a **T5
model** — owner, approved use, autonomy mode, tier, contract, frozen eval set, budget, kill switch —
visible on the same dashboards, to the same auditors, with the same red marks when it drifts.

**That is a design target, and the honest description of what runs is narrower.** Capabilities live
in their own table, `ai_capability`, and nothing links a capability to a row in the model register.
The `tier` on a capability is A or B — an *assistance* tier — and not a trainability class. So:

| Claimed control | State |
|---|---|
| Capability registered with an owner, an autonomy mode, a base model and a prompt digest | **Built.** Registration is an evidence-appending governance act |
| Registered **in the model inventory as a T5 model** | **Not built.** A separate register, not linked |
| Kill switch | **Built**, as `suspend`, with a reason and an evidence node. A suspended capability refuses with `capability_inactive` |
| Frozen eval set, regression gate, re-gating on every prompt or base-model change | **Not built.** There is no eval harness anywhere in the code |
| Canary fingerprinting to detect a base model changing under a vendor endpoint | **Not built** — and moot while every remote provider refuses |
| Per-capability token, cost and step budgets enforced at a gateway | **Built in the platform, not at a gateway** — `ai_spend` records tokens, cost and steps per capability and the budget is checked before a generation. That works because MAYA *is* the caller here, which is the one place in this platform where it can enforce rather than attest. A gateway sitting in front of a provider is somebody else's component and stays so |
| Prompt as a versioned artifact | **Partial.** `prompt_digest` is a string the registrant supplies and nothing verifies it against a stored artifact |
| Numbers interpolated from evidence, never generated (`FR-AI-005`) | **Not enforced.** The gate checks citations, not arithmetic. A claim can carry a number and pass on a resolving citation |
| Unmappable sentences marked `unverified_narrative` and attested per section (`FR-AI-006`) | **Deliberately not built, and superseded.** The gate *removes* an ungrounded claim rather than marking it, for the reason in §4: a marked sentence still reads as though the platform said it, and the marks are what gets skimmed past. The requirement should be restated rather than met |

Two of those gaps matter more than the rest. Without an eval harness there is no regression gate, so
*"re-gated on every prompt, corpus or base-model change"* is a sentence with nothing behind it. And
without numeric interpolation, the strongest single claim about drafted documentation — that
hallucinated statistics are removed as a class — is not true today; what is true is that an
unsupported *sentence* is removed.

The forcing-function argument survives all of that, and is the reason to close the gaps rather than
retire the claim:

- **If the platform cannot govern its own AI, it cannot govern the bank's.** Every awkwardness in the
  GenAI track shows up first in our own use, where we cannot blame the user.
- **It produces the reference implementation.** When a team asks what a governed GenAI application
  looks like, the answer is a working one they already use.
- **It makes the platform its own first customer**, which is the most reliable quality mechanism
  there is.

---

## 9. What the criterion admits, and nobody has built

Everything in this section is design. The ordering is by **oracle strength**, not by value, which is
the whole argument of this document applied to its own roadmap.

| | Capability | Tier | Its oracle | State |
|---|---|---|---|---|
| **1** | Feature deduplication and semantic search over the catalogue | A | A human adjudicates each proposed duplicate in seconds; the proposal points at two real rows | Not built. The catalogue's search is deliberately not embedding-based |
| **2** | Natural-language query over the inventory | A | The generated query parses and returns, or does not — and the user sees the query | Not built |
| **3** | Probe-set generation | A | A probe either executes and discriminates, or does not | Not built. This attacks an acknowledged weakness — [00 §5.3](00-mathematical-foundations.md) is candid that behavioural equivalence is only as strong as the probe set, and thin probe sets are the norm |
| **4** | Regulatory institution encoding | A | `L-16` then `L-8`, both of which run today (§3.1) | Not built, and the closest to ready. It converts the extensibility guarantee from *possible* to *cheap*, which is the difference between a guarantee and a claim |
| **5** | Format migration — re-expressing an artifact so it can enter production under the format policy | A | Run both artifacts over the probe set and assert numerical equivalence within tolerance. If equivalence fails, nothing ships | Not built |
| **6** | Remediation planning | A | *None needed.* The tropical semiring `(ℝ⁺∪{∞}, min, +)` computes the cheapest path to close a gap, in person-days, over the actual evidence structure. The **plan comes from the algebra**; an agent would only coordinate, so there is nothing for it to be creatively wrong about | Not built |
| **7** | Documentation drafting with grounding verification | B | Citation soundness — currently existence, ideally minimal support (§3) | **The path is built** (§4); no capability is registered against it in this repository |
| **8** | Model and EUC discovery | B | Every proposal points at a specific artifact a human can open | **Built without a model in it**, which is the right answer to the criterion rather than a way around it. `tools/scanner/` sweeps with regular expressions over formulas and code, every candidate carries **the text that matched** so a triager can check it in seconds, and confidence is capped well below certainty. The oracle a generative version would have needed — *is this actually a model* — is the triage decision itself, and the triage decision is what the register records. Scope it narrowly regardless: a queue with poor precision is worse than no queue, because it creates the appearance of coverage, and `core/discovery/contract.py` measures precision from the dismissals for exactly that reason |
| **9** | Validation assistance and gap analysis | B | *"You asserted six assumptions and tested four"* is a mechanical gap analysis dressed as an AI feature, and it is the finding that surfaces late and embarrassingly today | Not built |
| **10** | Finding correlation and triage | B | A human confirms the grouping before notifications go out | **Built without the assistance, and that is the interesting part.** `core/validation/correlation.py` answers M-8 — one cause, named once, with the findings it produced hanging off it — and it does the grouping *by assertion*: a person names the root. What the platform offers is `candidates()`, a deliberately weak suggestion over same-source/same-category/one-window/several-models. The oracle this capability would have needed is the human confirmation, and once the human confirmation is the mechanism rather than the check, the generator adds proposal quality and nothing else. Worth building only if the suggestion turns out to be too weak in practice |

**Nothing on this list makes a decision.** That is not an accident of the ordering; it is what the
criterion admits.

Item 4 deserves the note. Encoding a regime is expensive expert work — a supervisory statement is
forty pages of open-textured prose that someone must turn into a signature and a set of sentences.
That is an excellent task for a language model *and* its output is checkable, which is a rare pairing.
The specialist's job changes from *authoring* to *reviewing an encoding that has already passed two
consistency checks*, which is a much better use of a scarce person. What the model does not do is
publish.

---

## 10. Risks, including one that is usually missed

| Risk | Why it matters here | Mitigation, and whether it exists |
|---|---|---|
| **Fluency reduces scrutiny** | The one worth worrying about most, and rarely named. AI-drafted documentation *reads* complete. Reviewers of fluent text find fewer problems than reviewers of obviously rough text — the artifact's polish becomes a signal of its quality, and it is not one. The risk is not that AI writes bad documentation; it is that AI writes *plausible* documentation and thereby lowers the quality of human review | **Partly built.** Edit distance and its falling trend are measured (§6). Rendering AI-drafted sections visibly differently, and requiring attestation per section rather than per document, are not built |
| **Prompt injection through inventory metadata** | An attacker, or a careless developer, puts instructions in a model description, a feature definition or a vendor document, and the drafting assistant reads it. A real injection surface that an ordinary enterprise chatbot does not have | **Partly built.** The prompt is assembled from labelled evidence nodes and the model is told it may cite only those, so a fabricated citation is dropped. There is no injection detector, and separation is by prompt construction rather than by a parser (`FR-AI-017`) |
| **Evidence poisoning** | If an agent can create evidence nodes, it can create supporting evidence for a claim | **Built.** Agents propose; only humans and instrumented systems create evidence, and a generation is `drafted` until somebody other than the requester attests it. The `trust` column and the trust semiring exist to carry reduced confidence; nothing currently sets AI output below full trust |
| **Automation bias** | A triage queue that is usually right trains people to approve without looking | **Built.** Deterministic sampling and edit-distance trend (§6). Nothing acts on a falling trend automatically; somebody has to ask |
| **Base-model drift** | A vendor silently updates a model behind an endpoint and behaviour changes | **Not built.** Canary probe-set fingerprinting on a schedule is the answer and does not exist. Moot while every remote provider refuses |
| **Cost blowout** | Agentic loops over a large estate get expensive fast | **Partly answered, at two different layers.** Per-capability token, cost and step budgets exist in `ai_spend` and are checked before a generation — that is the layer that can actually stop something, because MAYA *is* the caller. `core/estate/cost.py` is the other half and deliberately does not stop anything: it takes attested cost over the whole estate, attributes it from the register's ownership, and reports the **share nobody attributed**. A breach raises a finding with an owner. What is still absent is enforcement at a gateway, which is not MAYA's to hold |
| **Capability creep into Tier C** | The pressure to let a well-performing assistant *"just assign the tier"* will be constant and will come from sensible people | **Partly built.** Tier C is not registrable, and the assist permissions grant no governance authority — but by construction rather than by a check (§7) |

---

## 11. The position, stated plainly

AI belongs in this platform, substantially, for a reason that is easy to miss: **a governance system
built on formal foundations is an unusually good place to use AI, because it comes with oracles.**
The satisfaction condition checks a regulatory encoding. Deontic consistency checks an obligation set.
Contract refinement checks a substitution. Probe-relative equivalence checks a conversion. Boolean
evaluation over a derivation checks a citation. Elsewhere in the enterprise, *"the AI might be wrong"*
is managed with review processes and hope. Here, for a meaningful fraction of the work, it is managed
with a test.

And the boundary should be drawn **harder** than is currently fashionable. AI may draft, retrieve,
propose, cluster, convert, generate tests and chase. It may never conclude, approve, tier, scope or
close. Not because models are untrustworthy in some general sense, but because the entire value of
this platform is that its claims are *derivable* — and a claim whose provenance is *"a language model
said so"* is precisely the kind of claim the system exists to eliminate.

The uncomfortable part is the honest one. The path is built and the capabilities are not; the
criterion is executable and the oracles for the highest-value tasks are ready and unused; the
strongest self-governance claim in the design — every capability a T5 model in our own inventory — is
a separate table today. That gap is written down here rather than in a roadmap, because a claim about
a platform's own AI is the one claim a reader has no independent way to check.

---

## 12. Traceability

| Section | Satisfies |
|---|---|
| §1 The criterion | [00 §12a](00-mathematical-foundations.md) |
| §2 Tiers | `FR-AI-001`–`FR-AI-004`; the two autonomy modes of [09 §9.1](09-security-compliance.md) |
| §3 Oracles | `L-7`, `L-12`, and the grammar's admissibility laws; `L-8` and `L-16` in [00 §12](00-mathematical-foundations.md) |
| §4 The gate | `FR-AI-003` (retrieval over the evidence graph only), `FR-AI-004` (citation verification); [09 §7](09-security-compliance.md) |
| §6 Measurement | `FR-AI-015` (deliberate sampling), `FR-AI-016` (edit distance) |
| §8 Self-governance | `FR-AI-001` (capability registry), `FR-AI-002` (no governance credential), `FR-AI-005`, `FR-AI-006` — each with its gap named |
| §7 Refusals | `FR-AI-017`; [09 §2.5](09-security-compliance.md) |
| §9 Format migration | The closed format list in [09 §3](09-security-compliance.md) |
| §10 Agentic controls | [09 §9.3](09-security-compliance.md) |
| Build status | [12 §0](12-implementation-plan.md#0-build-status) is authoritative |

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
