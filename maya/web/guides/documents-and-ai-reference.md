# Model documents and the AI gateway reference

This reference is for model owners and validators who generate model cards, validation reports and model documentation, for the firm's model risk function that decides what those documents look like, and for the administrators who choose which language model — if any — drafts their prose. It covers how a document is built from the record, how a firm replaces the templates, what drafting does and how it is labelled, approval and deletion, and then the AI gateway: providers, model profiles, the default and how to switch it, the audit of every call, and exactly what is sent to a provider.

## Documents: facts first, prose second

MAYA generates three kinds of document from one model version's record:

| Kind | Built-in template | What it is |
|---|---|---|
| `model_card` | `model_card` | Intended use, what it computes, inputs and parameters, training data, performance, fairness, limitations, and where it runs. |
| `validation_report` | `validation_report` | The evidence MAYA holds, assembled for a validator, with a place for the conclusion — not a draft of it. |
| `model_documentation` | `model_documentation` | Ten numbered sections, from purpose and scope through methodology, data, calibration, implementation, testing and assumptions to monitoring and change history. |

A document is built from a **snapshot of the facts** — the model and version, its mathematics and input contract, code checks and conformance, its training warrants (certificate, blind scores, parameter sets, fairness and importance evidence), its execution warrants (covenants, limits, reports, breaches, monitoring), challengers, the governance profile, findings and reviews, and its inventory row. The facts are gathered through the same services, **under the same read permissions**, as every screen: a document you generate cannot contain what you could not have read.

The snapshot is hashed and the hash stored with the document, so "which facts was this written from" always has an answer. The moment of generation is left out of that hash, so the same record gives the same hash.

### Generating one

```python
# Generate a validation report for version 3, drafted under the default profile
import maya.sdk as maya

my = maya.connect(base_url="https://maya.example.com", api_key="maya_prod_…")
job = my.documents.generate("credit/pd_logit", "validation_report", version_no=3)
done = my.wait(job)
doc = my.documents.get(done["result"]["document_id"])
print(doc["state"], doc["facts_sha256"][:12], [s["key"] for s in doc["ai_sections"]])
```

```bash
# The same over REST: a job comes back (202)
curl -s -X POST https://maya.example.com/api/v1/models/credit/pd_logit/documents \
  -H "Authorization: Bearer $MAYA_API_KEY" -H "Content-Type: application/json" \
  -d '{"kind": "validation_report", "version_no": 3, "use_ai": true}'
```

| Field | Default | Meaning |
|---|---|---|
| `kind` | — | `model_card`, `validation_report` or `model_documentation`. |
| `version_no` | the highest version number | Which version to document. |
| `template` | the kind's own name | A template name from `GET /documents/templates`. |
| `use_ai` | `true` | `false` renders every drafted section as "Not drafted: this document was generated without a language model." |
| `profile` | the gateway's default | The model profile drafted sections use when the template does not name one. |

The request is checked when you make it, so a refusal comes back at once rather than as a failed job: an unknown kind, a template that does not exist, or a template of another kind ("The template '…' is a model_card, not a validation_report"), and read access to the model. On the model's page the **Documents** tab does the same, and the finished document appears there.

Each stored document records its kind, the template's name and SHA-256, the facts' SHA-256, the provider and model, one record per drafted section (key, instruction, whether it was drafted, and why not if it was not, with token counts), the Markdown and its SHA-256, and its state. Generation is audited as `document.generated` with the number of sections drafted.

## Templates, and how a firm overrides them

A template is a Jinja2 file that produces Markdown, named `<name>.md.j2`. The built-ins live in `maya/documents/templates/`. A firm's own live in the folder `documents.template_dir` names — by default `config/templates/documents/`, read relative to the project root.

| Rule | Effect |
|---|---|
| A file there named like a built-in (`model_card.md.j2`, `validation_report.md.j2`, `model_documentation.md.j2`) | **Replaces** the built-in. MAYA uses yours from then on; `GET /documents/templates` shows it as `custom (replaces the built-in)`. |
| Any other `*.md.j2` file there | Becomes a template of its own, offered for the kind its header declares. |

The easiest start is to copy the built-in and edit the copy. The first line of a template may declare what it is:

```jinja
{# maya: kind=model_card; title=Model card (firm layout) #}
```

Without a header, a new template's kind is its own name — which is only one of the three kinds if it is named like one — so a firm template other than a replacement should always carry the header.

### What a template sees

| Name | What it is |
|---|---|
| `facts` | The snapshot: `facts.model`, `facts.version`, `facts.versions`, `facts.governance`, `facts.training`, `facts.execution`, `facts.challenges`, `facts.inventory`, plus `generated_at` and `maya_version`. |
| `ai(key, instruction, words=150, profile=None)` | A section drafted by a language model from the facts. `key` names the section (letters, digits, `_` and `-`; anything else becomes `_`); `words` is the length asked for; `profile` names a model profile, or the default. |
| `table(rows, columns, headers=None)` | A Markdown table from a list of records; "*None recorded.*" when empty. |
| filters `pct`, `num`, `yesno`, `dt` | Percentages, numbers to four significant figures, yes/no, dates. |

A missing fact renders as empty rather than failing, so a template written for a model with a challenger still renders for one without. Raw HTML is neutralised when Markdown becomes HTML — every `<` becomes text — so nothing a description or a drafted section contains can reach a page as markup.

```jinja
{# maya: kind=model_card; title=Model card (credit risk layout) #}
# {{ facts.model.name }} v{{ facts.version.number }}

**Tier** {{ facts.governance.tier or "—" }} · **owner** {{ facts.model.owner or "—" }}

## Intended use
{{ ai("intended_use", "Describe what the model is used for and by whom, from the facts.", words=120) }}

## Inputs
{{ table(facts.version.inputs, ["name", "type", "role"]) }}
```

### How the render works

Rendering takes two passes. The first renders the template with each `ai()` call leaving a marker and recording its request. The requests are then drafted one by one — or, with drafting off, marked as not drafted — and the second pass puts each draft where its marker was, wrapped in comments naming the section. The label a reader sees is applied when the document is **shown**, from the document's state, so approving a document changes the label without changing the stored text or its hash.

## Drafted sections and their labels

Each `ai()` request goes to the AI gateway with a fixed system instruction: use only the facts given; never invent a number, a name, a date, a result or a judgement they do not contain, and write "not recorded" where they do not say; **do not conclude whether the model is fit for use**, because that is the validator's decision. The built-in validation report accordingly drafts only its executive summary and leaves the conclusion to the validator.

Every drafted section is shown with a label:

| State | Label |
|---|---|
| Drafted, document not approved | *Drafted by anthropic · claude-opus-5 from the recorded facts. Not yet reviewed by a person.* |
| Drafted, document approved | *Drafted by … from the recorded facts; reviewed and approved by val.jones on 2026-09-28.* |
| Not drafted | *Not drafted by a language model.* The section's text says why — drafting off, no provider configured, the provider's own error. |

A document is still a document without a model: with `llm.provider: none` (the default) or `use_ai: false`, every drafted section says it was not drafted and everything else renders in full.

## Formats

`GET /documents/{doc_id}/render?format=md|html|pdf` (`my.documents.render(doc_id, format)`) returns the document with each drafted section labelled.

| Format | Notes |
|---|---|
| `md` | The labelled Markdown. |
| `html` | A standalone page. Display maths (`$$ … $$`) is kept out of Markdown so its backslashes survive, and held as TeX source; MAYA's own document view at `/models/<ns>/<name>/documents/<id>` typesets it with KaTeX, while a downloaded copy shows the TeX. |
| `pdf` | Typeset through LaTeX. If the true build fails for a reason that is the host's rather than the document's, MAYA falls back to its draft renderer and says so in the `X-Maya-Draft-Render: true` response header. |

## Approval and deletion

```python
# A second person approves; the drafted labels now name the reviewer
my.documents.approve(doc["id"])
```

| Action | Who | Rule |
|---|---|---|
| Approve (`POST /documents/{doc_id}/approve`) | Someone with `approve` on the model who **did not generate the document** | "A document is approved by someone other than the person who generated it". Approving an approved document is refused. Audit `document.approved` with the content hash. |
| Delete (`DELETE /documents/{doc_id}`) | Whoever generated it, or anyone who may `update` the model | Only a draft: "Only a draft document can be deleted; an approved one is part of the record". Audit `document.deleted` with the content hash. |

Approval covers the drafted sections too: the approver is putting their name to prose a model wrote, which is exactly why the label changes to name them. The `maya_documents` gauge counts documents by state.

## The AI gateway

The AI gateway (`maya/services/ai.py`) is the one place MAYA asks a language model anything: document sections, the recorded challenger with `assistant.provider: llm`, the **Test** button, and live evaluations of [LLM applications](/help/llm-apps). Callers name a **model profile**, never a provider or a model, so moving from one model to another is an edit to a profile — never to a template or to code.

What comes back is a draft. Nothing in the gateway approves, blocks or edits anything.

### Providers

| Provider | What it calls | Its settings |
|---|---|---|
| `none` | Nothing. The default: nothing is drafted until someone chooses a provider. | — |
| `stub` | Nothing: a deterministic answer made from the prompt, for tests and offline demonstrations. | `llm.model` (default `stub-1`) |
| `anthropic` | Claude through the official `anthropic` package, streamed, with adaptive thinking unless switched off. | `llm.anthropic.model`, `llm.anthropic.api_key_env`, `llm.anthropic.base_url`, `llm.anthropic.thinking` |
| `openai` | The Chat Completions API: OpenAI itself, or any server that speaks it (vLLM, LM Studio, llama.cpp's server) by base URL. The key is optional for a local server. | `llm.openai.base_url`, `llm.openai.api_key_env`, `llm.openai.model` |
| `azure_openai` | A deployment at an Azure OpenAI resource endpoint. | `llm.azure_openai.endpoint`, `llm.azure_openai.deployment`, `llm.azure_openai.api_version`, `llm.azure_openai.api_key_env` |
| `ollama` | A model served by Ollama. | `llm.ollama.base_url`, `llm.ollama.model` |
| `bedrock` | A model on Amazon Bedrock through the Converse API (needs `boto3`). | `llm.bedrock.region`, `llm.bedrock.profile`, `llm.bedrock.model` |

Shared settings: `llm.provider`, `llm.model` (overrides the provider's own model setting when set), `llm.max_tokens` (default 2048), `llm.temperature` (0.2) and `llm.timeout_seconds` (120). API keys are **never** configuration: each provider reads its key from the environment variable a setting names, and a missing key is refused with a sentence saying which variable to set.

A third party adds a provider at the `llm_provider` extension point: a package with an entry point in the `maya.llm_provider` group, loaded only when `plugins.allow` names it, because a plugin runs inside MAYA with MAYA's privileges. **Admin → Extensions** and **Admin → AI models** list every provider on offer and any that were refused.

### Model profiles

A profile is a logical model: `provider`, `model`, `max_tokens`, `temperature`, `options` and `description`. `options` are that provider's own settings for this profile — the part after `llm.<provider>.`, such as `base_url`, `region`, `thinking` or `api_key_env` — laid over the global settings, so one provider serves many profiles.

Profiles come from three places; a later one wins a name clash:

| Source | Where | Notes |
|---|---|---|
| settings | the `llm.*` settings | Always exactly one profile, `default`. |
| file | `llm.profiles_file`, by default `config/llm_profiles.yaml` | Not shipped; copy `config/llm_profiles.example.yaml` to start. An unknown key or a profile without a provider is refused when the file is read. |
| database | saved on **Admin → AI models** | Replaces a file profile of the same name. |

```yaml
# config/llm_profiles.yaml
default: drafting
profiles:
  drafting:
    provider: anthropic
    model: claude-opus-5
    max_tokens: 2048
    options: {thinking: adaptive, api_key_env: ANTHROPIC_API_KEY}
  local:
    description: A model on the firm's own hardware; nothing leaves the building
    provider: ollama
    model: llama3.1
    options: {base_url: "http://gpu-box:11434"}
```

A template sends one kind of section to a cheaper or local model with `ai("intended_use", "…", profile="local")`.

### The default, and switching it at runtime

The default profile is, in order of precedence:

1. the choice an administrator made on **Admin → AI models** (or `POST /ai/default`);
2. the `llm.profile` setting;
3. the profiles file's `default:` line;
4. otherwise `default`, the profile made from the settings.

The administrator's choice is stored in the database and read by every process on every call, so switching takes effect at once, everywhere, without a restart. Choosing **Use the configuration's default** — `{"profile": null}` — hands the choice back to the configuration. Each switch is audited as `ai.default_changed` with the before and after.

```python
# See every profile and switch the default (administrators)
st = my.ai.status()
print(
    st["default"],
    st["default_source"],
    [(p["name"], p["source"], p["ready"]) for p in st["profiles"]],
)
my.ai.set_default("local")
print(my.ai.test("local"))  # {'ok': True, 'reply': 'ready', 'seconds': …, 'input_tokens': …}
my.ai.set_default(None)  # back to the configuration
```

`GET /ai/status` needs only a signed-in user and calls nothing: each profile with its source, provider, model and whether it looks usable, which is the default and who chose it, and every provider on offer. Option names containing "key" are left out of what it shows.

### Test, save and delete

All three are for administrators.

| Action | Behaviour |
|---|---|
| **Test** (`POST /ai/profiles/{name}/test`) | Asks the profile's model "Reply with the single word: ready." and returns the reply, the time and the tokens — or `ok: false` and why not. The call goes through the gateway, so it is audited like any other. |
| **Save** (`PUT /ai/profiles/{name}`) | Creates or replaces a database profile. The name is lower-case letters, digits, `_` or `-`, starting with a letter; only the six profile keys are accepted; the provider must be on offer. Audit `ai.profile_saved`. |
| **Delete** (`DELETE /ai/profiles/{name}`) | Removes a database profile. A profile from the file is edited in the file ("No profile named '…' was saved here; one from the file is edited there"), and the profile an administrator made the default cannot be deleted until another is chosen. Audit `ai.profile_deleted`. |

**The no-secrets rule.** An option whose name contains `api_key`, `secret`, `password` or `token` is refused unless it ends in `_env`: "Options may not hold a secret (…): name the environment variable that holds it instead, as api_key_env". A key in a profile would be a key in the database, in backups and in every export of them.

### Every call is recorded

Every completed call writes the audit entry `ai.completion`: its purpose (for a document, `document:<kind>:<section>`), the profile, the provider and model, input and output tokens, the stop reason, the object it was about, and the SHA-256 of the system prompt and prompt. **The prompt itself is not logged**: it carries a model's facts, which the audit log's readers may not be allowed to see. The hash lets anyone holding the prompt prove it was the one sent.

A call the provider could not answer is audited as `ai.completion_failed`, with its purpose, profile, provider, model and the reason, and counted in `maya_ai_completions_total` with `outcome="unavailable"`. Completed calls are counted there with `outcome="ok"`, their tokens in `maya_ai_tokens_total` and their time in `maya_ai_completion_seconds`, each labelled by purpose and provider.

### What is sent, and what is not

| Sent to the provider | Never sent |
|---|---|
| For a document section: the fixed system instruction, the section's instruction, key and length, and the facts snapshot as JSON — up to 60,000 characters of it. The facts include the model's description, formula and inputs, owners' and reviewers' user names, parameter values, scores and metrics, findings with their text, covenants and review notes. | Data rows. The facts hold aggregates and definitions, never a feature's values or a holdout row. |
| For the recorded challenger with `llm`: the review dossier — definitions, the specification and the formula — and the deterministic findings. | API keys, except in the request header to the provider they belong to. |

Choosing a provider is therefore a decision about where a model's record may go. A firm that may not send it outside can use `ollama`, or `openai` pointed at a server inside the firm.

## The assistant's recorded challenger

The recorded challenger writes a memo when a feature, feature set or model version is submitted (see the [workflow reference](/help/workflow)). Which model, if any, it asks is its own setting:

| `assistant.provider` | What writes the memo |
|---|---|
| `rules` (default) | Deterministic checks only, offline. |
| `llm` | The deterministic checks, plus a language model's challenge asked through the AI gateway under `assistant.profile` (empty: the gateway's default). Any provider an administrator set up serves; the call is audited as `ai.completion` like any other. |
| `claude` | The deterministic checks, plus Claude asked directly with `assistant.claude.model`, `assistant.claude.effort`, `assistant.claude.api_key_env` and `assistant.claude.timeout_seconds`. This path does not go through the gateway, so it is not in the gateway's audit entries or metrics; the memo itself records the model. |

`assistant.enabled` switches memos off entirely. If the model cannot be asked, the memo holds the deterministic findings and says why. A memo cannot approve, block or edit anything: no check reads it.

## What this does not do

- A drafted section is not a reviewed section until a second person approves the document, and the label says so on every copy.
- The built-in validation report does not draft its conclusion, and the system instruction forbids concluding in any template. A firm template that asks anyway gets prose, never a decision MAYA acts on.
- The gateway does not choose a model for you, fall back to another provider when one fails, or retry: an unavailable provider leaves the section marked "Not drafted" with the reason.
- The gateway does not filter or redact the facts it sends; which facts leave is decided by the choice of provider.

## API summary

All paths are under `/api/v1`.

| Method and path | SDK |
|---|---|
| `GET /documents/templates` | `my.documents.templates()` |
| `POST /models/{namespace}/{name}/documents` (202, a job) | `my.documents.generate(ref, kind, ...)` |
| `GET /models/{namespace}/{name}/documents` | `my.documents.list(ref)` |
| `GET /documents/{doc_id}` | `my.documents.get(doc_id)` |
| `GET /documents/{doc_id}/render?format=` | `my.documents.render(doc_id, format)` |
| `POST /documents/{doc_id}/approve` | `my.documents.approve(doc_id)` |
| `DELETE /documents/{doc_id}` | `my.documents.delete(doc_id)` |
| `GET /ai/status` | `my.ai.status()` |
| `POST /ai/default` | `my.ai.set_default(profile)` |
| `POST /ai/profiles/{name}/test` | `my.ai.test(name)` |
| `PUT /ai/profiles/{name}` | `my.ai.save_profile(name, **fields)` |
| `DELETE /ai/profiles/{name}` | `my.ai.delete_profile(name)` |
