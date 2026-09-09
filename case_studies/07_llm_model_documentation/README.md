# Case study 7 — An LLM drafting documentation, governed as a model

> **The demo in one sentence.** A language model drafts a validation-pack
> section, makes five claims, and the platform **removes** the one that cites
> evidence it does not hold — then refuses to let the person who asked for the
> draft be the person who signs for it.

```bash
# Case study 4 first — this one documents the model it registered.
.venv/bin/python case_studies/04_merton_distance_to_default/build.py
.venv/bin/python case_studies/07_llm_model_documentation/build.py
```

---

## 1. The theory

### An AI capability is a model, under this definition

MAYA defines a model as `f : P ⊗ X → D(Y)`. Apply it to a language model:

| Part | For a regression | For an LLM capability |
|---|---|---|
| **P** | the coefficient vector | the **prompt** and the configuration (model id, temperature, tool set) |
| **X** | the feature row | the **context** it is given — retrieved evidence, the subject record |
| **D(Y)** | a distribution over a number | a **distribution over token sequences** |

Nothing had to change. That is not a rhetorical point: the common alternative
is a *second* governance framework for AI, and two frameworks means two
registers, two approval paths, and a boundary argument about which one applies
to a gradient-boosted scorecard. A definition general enough to have covered
this in advance is worth more than a policy written after the fact.

### Where the implementation stops short of the argument

The paragraph above is the *design* claim, and it is worth checking against
what the platform actually does — which is what building this case study did.

MAYA's domain vocabulary has exactly the right slot: `ParameterKind` includes
`llm_configuration`, and `FitProcedure` includes `configure`, which would make
a capability **T5**. But an AI capability is **not registered as a model
version**. It goes into a parallel register — `/assist/capabilities` — with a
tier, a base model, a prompt digest, an owner, an autonomy mode and a review
sample. It has **no kernel and therefore no derived trainability class**:

```python
capability keys: autonomy, base_model, capability_key, created_at,
                 description, id, oracle_key, owner, prompt_digest,
                 review_sample, status, tier
```

So the taxonomy that governs every other model in the register does not reach
this one. In practice the tier does the work the class would do — A, B and C
decide what is admissible, exactly as T0…T8 do elsewhere — and the two schemes
are coherent rather than contradictory. But they are two schemes, and the
argument in this section is that there should be one.

Worth saying out loud in a demo rather than glossing: *the design says an AI
capability is a model; the implementation registers it beside models rather
than as one.* Whether that matters depends on whether you ever need to ask a
question of the whole estate at once — "what do we run, and how are its
parameters inhabited" — and today that question has to be asked twice.

### Why "hallucination" is the wrong frame for governance

The failure mode people name is *hallucination* — the model states something
false. But a governance platform cannot adjudicate truth, and should not try.
What it can adjudicate is **support**: does this claim cite something the
institution actually holds?

That reframing is the whole design. It converts an open-ended epistemic problem
("is this true?") into a closed, mechanical one ("does this citation resolve?"),
and the closed one can be checked by a computer on every generation rather than
by a human on some of them.

The residue is honest and worth stating: a claim that cites a real evidence node
but *mischaracterises* it passes this gate. Grounding is a necessary condition,
not a sufficient one, which is exactly why attestation by a person is still
required afterwards.

### Grounding: remove, don't flag

The platform **removes** unsupported claims from the output and keeps them,
separately, for the reviewer. The alternative — flagging them in place — is
worse for a reason that is about people rather than software:

- A flagged document still *contains* the unsupported sentence. It will be
  copied, quoted, and pasted into a committee paper by somebody who did not
  notice the marker.
- A flagged document puts the burden on the reader, every time it is read,
  forever.
- A pruned document has the property you actually want: **every sentence
  remaining in it is supported.** That is a statement about the document rather
  than about the reader's diligence.

And the removed claims are not deleted — they go to the reviewer, because a
capability whose failures are discarded has no measurable quality.

### Automation bias, and why sampling must be deterministic

Somebody who has approved forty correct drafts is not reading the forty-first.
This is not a character flaw; it is a well-documented property of human
supervision of reliable automation, and telling people to be vigilant does not
fix it.

Two mechanisms respond to it:

**A mandatory review sample.** A fraction of generations is pulled for
independent review *regardless of how good they look*. Deliberate friction.

**The sample is deterministic on the capability's own draw count**, seeded from
the capability id and how many generations it has produced — not from a clock.
Seeding on the clock made the docstring false in both halves: the sequence was
unrepeatable so no test could depend on it, *and* a drafter watching which of
their own drafts were sampled could infer the rate and time their submissions
around it.

**Edit distance is the measurement.** Somebody accepting everything unchanged
and somebody reading carefully produce the *same approval count* and very
different edit-distance distributions. Only one of those two facts is visible
without measuring it.

### The tiers, and the one that is refused

| Tier | Criterion | Consequence |
|---|---|---|
| **A** | The output can be **mechanically checked** by a named oracle | Register it. The oracle runs every time and is the control |
| **B** | Every claim can be **grounded** in evidence the platform holds | Register it. Unsupported claims are removed |
| **C** | Neither checkable nor groundable | **Not registrable** |

Tier C being *refused* rather than *discouraged* is the sharp end of the
framework. The argument: a Tier C capability sitting in a registry is one that
will be wired into a decision one day, and at that point the register will
appear to have blessed it. Advisory AI is a person using a chat window, and a
chat window is not something a model-risk framework governs.

---

## 2. MAYA does not call the model

Ask which providers are usable and the platform answers, of the commercial
APIs:

```
anthropic    NOT usable
             MAYA does not call the Anthropic API. Nothing here is wired to an
             egress path, a credential, or a confidentiality decision about
             what may leave the institution
openai       NOT usable
mock         usable
```

**This is the same boundary as "MAYA does not train models."** The inference
runs wherever the bank runs it — behind their own egress controls, under their
own confidentiality decision, with their own credential. MAYA issues the
authority, records what came back, and refuses what should be refused.

It also means adopting the platform does not require a conversation about
whether model documentation may leave the building. That conversation is real
and hard, and it is not one a register should be having on the institution's
behalf.

So the "language model" in this script is a deterministic stand-in — and it
stands in for **the bank's egress path**, not for the platform's.

---

## 3. What the script does

| Step | What happens |
|---|---|
| 1 | Ask which providers MAYA can reach — and read the answer |
| 2 | The three tiers, from the platform rather than from this README |
| 3 | **Show a refusal**: registering a Tier C capability |
| 4 | Register the Tier B capability, prompt by **digest** |
| 5 | Record five claims the bank's model produced |
| 6 | **Watch grounding remove one** and say why |
| 7 | **Show a refusal**: the requester attesting their own draft |
| 8 | s.iqbal attests it, with edits |
| 9 | The reviewer's automation-bias record |
| 10 | Write the LaTeX specification |

---

## 4. The claim that gets removed

Four of the five claims cite evidence MAYA holds. The fifth is written to be
exactly the shape these systems produce:

```
c5  Backtesting over the 2019-2024 period showed an area under the ROC curve
    of 0.87, comfortably above the 0.75 threshold in the model risk policy.
    cites: ev-backtest-2024
```

Fluent. Specific. Quantified. Cites a source. **Entirely invented** — there is
no such evidence node, and there was never a backtest.

It is also the single most dangerous sentence in the document, because it is
the one a committee would act on. And it is precisely the sentence a human
reviewer, reading forty of these, would skim past.

```
✓ MAYA: 4 claim(s) kept, 1 REMOVED — 4 of 5 claims were supported;
        1 were removed from the output
  removed  c5: Backtesting over the 2019-2024 period showed an area under…
  because  1 citation(s) do not resolve: ev-backtest-2024
```

---

## 5. The two refusals

**Tier C:**

```
✓ refused: a Tier C capability — advisory AI, in a register
```

**Self-attestation:**

```
[self_attestation] admin requested this generation and cannot also attest it
→ attestation is a person taking responsibility for machine output; it must be
  somebody other than whoever asked for it
```

The second is the same control as parameter-set approval in case studies 1, 2,
3 and 5 — *a number one person can both produce and bless is a preference, not
an estimate* — applied to text instead of to coefficients. It is the same rule
because it is the same problem.

---

## 6. The prompt is a parameter object

```python
PROMPT_DIGEST = "sha256:" + hashlib.sha256(PROMPT.encode()).hexdigest()

maya.assist.register(capability_key="doc.model_description", tier="B",
                     base_model="claude-opus-5",
                     prompt_digest=PROMPT_DIGEST, ...)
```

The **digest**, not the text. Two reasons:

1. What governance needs is the ability to say *this generation came from that
   prompt*. A digest answers that; a stored copy does not, because a copy can be
   edited afterwards and nothing would show it.
2. A prompt is often long and sometimes confidential. The register does not
   need it, so it does not hold it.

Changing the prompt changes the digest, which makes it a different `P` — a new
parameter set that somebody has to approve. This is the same mechanic as
changing a threshold in the HELOC rulebook of case study 6.

---

## 7. What this case study does not show

- **No Tier A oracle.** The other tier — output a named oracle mechanically
  checks — is a separate case study. MAYA ships five oracles, each backed by
  machinery that exists for another reason (`citations.resolve`,
  `contract.refines`, `schemas.substitutable`, `test.registered`,
  `warrant.conforms`).
- **No real model call**, for the reason in §2.
- **No retrieval.** A production capability would fetch its context from the
  evidence graph; here the context is handed in.
- **Grounding is necessary, not sufficient.** A claim citing a real node it
  mischaracterises passes. That is why a person still signs.

---

## 8. A rough edge worth knowing

The generation records `attested_by` as `person/s.iqbal`, but the reviewer
endpoint keys on the bare username:

```bash
curl -s -u admin:… .../assist/reviewers/s.iqbal        # 200
curl -s -u admin:… .../assist/reviewers/person/s.iqbal # 404 — the slash splits the path
```

Not wrong, but the two forms are not interchangeable and nothing says so. The
script passes the bare name with a comment.

---

## 9. Questions this case study answers well

**"Do we need a separate AI policy?"**
No, and this is the case study for that argument. An AI capability is a model
under the same definition, and the controls that apply to it are the ones that
already applied to everything else.

**"How do you stop it making things up?"**
You do not. You stop unsupported claims reaching the document, and you measure
whether the reviewer is still reading.

**"Does our model documentation leave the building?"**
Not through MAYA. It does not call an API and says so when asked.

**"Who is responsible for what the model wrote?"**
The person who attested it — by name, on the record, and never the person who
asked for it.

---

## 10. Files this produces

| File | What it is |
|---|---|
| `generation.json` | The full generation record: claims kept, claims rejected with reasons, the oracle verdict, whether it was sampled |
| `llm-capability-specification.tex` | Specification, with the claim table |

```bash
pdflatex llm-capability-specification.tex     # 2 pages
```
