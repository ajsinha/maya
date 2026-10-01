# The AI gateway: a provider failing, or token use past budget

For an administrator. Everything MAYA asks a language model goes through one gateway: the
drafted sections of generated documents, the assistant's recorded challenger when
`assistant.provider` is `llm`, live evaluations of LLM applications, and the **Test** button
on Admin → AI models. None of these is on a critical path. A failing provider degrades them
visibly and blocks nothing, but it should still be fixed.

## Symptoms

- `MayaAiProviderFailing`: more than half the calls to one provider failed over 15 minutes.
  Documents come out with sections marked not drafted, with the reason; challenger memos say
  *"… — the memo holds the deterministic findings only"*; live evaluation runs fail with
  `llm_unavailable` (HTTP 503).
- `MayaAiTokenBudget`: more than the budget of tokens in a day.

## Diagnosis

1. **Admin → AI models** lists every profile with its provider, model and whether it is
   ready, and the reason when it is not: a missing key variable, an unreachable base URL,
   an uninstalled SDK. **Test** asks the profile's model one short question and shows the
   reply, the time and the tokens, or the error.
2. `GET /ai/status` returns the same as JSON.
3. The audit log has one `ai.completion` entry per successful call, with its purpose,
   profile, provider, model and token counts. Filter by action `ai.completion` to see who
   and what is spending.
4. `sum by (purpose, provider) (increase(maya_ai_tokens_total[1d]))` shows where the tokens
   went.

## Remedy

- **A provider is down or refusing.** Fix the cause the page names: set the key's
  environment variable (profiles name the variable and never hold the key), correct the
  base URL, or install the provider's SDK. If the provider itself is down, **Make default**
  another ready profile. The switch takes effect at once in every process, and is audited.
- **Spend is too high.** Find the purpose. Give a cheaper profile to document sections that
  do not need the strongest model (a template names a profile per section), turn drafting
  off for bulk regeneration, or lower `llm.max_tokens`. A live LLM-application evaluation
  always calls the provider and model its version declares, so it cannot be moved to a
  cheaper profile. Evaluate less often, or submit recorded runs instead.

## Verification

Test on the profile succeeds; the failure ratio falls below the threshold within 15
minutes; the next generated document has its sections drafted.

## What this does not reach

The token budget of five million a day is a placeholder. Set it in
`config/prometheus/maya-governance.rules.yml`. The metric counts tokens, not money: prices
differ by provider and model, and change.
