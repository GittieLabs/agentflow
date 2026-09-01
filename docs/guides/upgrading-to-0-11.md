# Upgrading to 0.11.0

0.11.0 adds a verbatim vendor-parameter passthrough and **removes** the model-name suffix
convention it replaces. This page is the whole migration.

!!! danger "Breaking: the `-low` / `-medium` / `-high` model-name suffix is gone"
    If any agent's `model` ends in `-low`, `-medium` or `-high`, its behaviour changes on upgrade.
    Everyone else is unaffected.

## What changed, and why

Before 0.11.0, reasoning effort for Anthropic and Gemini was selected by **decorating the model
name**. The provider parsed it back off with `rsplit("-", 1)`:

```python
AgentConfig(name="advisor", model="claude-sonnet-5-high")
# provider sent: model="claude-sonnet-5", output_config={"effort": "high"}
```

That convention had three defects, and the first is the one that forced its removal:

1.  **It silently mangled legitimate model names.** `rsplit("-", 1)` cannot tell an effort suffix
    from the end of a real model name. Any model genuinely called something ending in `-high` was
    truncated, and the tail was misread as an effort level — with nothing in the request or the
    response to say so. As vendors keep shipping names, that becomes more likely, not less.
2.  **It was invisible.** Nothing in the API surface said the model string was being parsed, so a
    caller had no way to know it had happened.
3.  **It did not exist on `openai_compat`.** The same suffixed model meant reasoning effort on one
    provider and a mangled model name on another, so identical configuration produced different
    requests depending on who served them.

## Migrating

Restore the model name to its **real** value and pass the effort through `params`.

=== "Anthropic"

    ```python
    # before
    AgentConfig(name="advisor", model="claude-sonnet-5-high")

    # after
    AgentConfig(
        name="advisor",
        model="claude-sonnet-5",
        params={"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}},
    )
    ```

=== "Gemini"

    ```python
    # before
    AgentConfig(name="advisor", model="gemini-3-pro-high")

    # after
    AgentConfig(
        name="advisor",
        model="gemini-3-pro",
        params={"thinking_config": {"thinking_level": "high"}},
    )
    ```

=== "Front matter"

    ```yaml
    ---
    name: advisor
    model: claude-sonnet-5
    params:
      thinking: {type: adaptive}
      output_config: {effort: high}
    ---
    ```

Anthropic's rule that `temperature` must be absent whenever thinking is active is **preserved**. It
now keys off `params` containing `thinking` rather than off a parsed model name, so enabling
adaptive thinking still suppresses `temperature` automatically.

## How to tell whether you are affected

Search your agent configuration for a model ending in one of the three suffixes:

```bash
grep -rn "model:.*-\(low\|medium\|high\)$" path/to/your/agents/
```

- **No matches** — nothing to do. `params` is purely additive for you.
- **Matches** — apply the migration above. If you leave them, the model name is now sent to the
  vendor **verbatim**, which is almost certainly not a real model, and the call will fail rather
  than silently do the wrong thing. That noisy failure is deliberate.

## What you gain

`params` is forwarded verbatim to the vendor SDK call, so anything a vendor supports is reachable
without waiting for AgentFlow to name it — including `reasoning_effort` on `openai_compat`, which
had no effort mechanism at all before 0.11.0.

```python
await provider.chat(messages, params={"reasoning_effort": "high"})
```

Two rules apply, both covered in [LLM Providers](../concepts/providers.md#vendor-parameters-params):

- A parameter a model ignores is **your** business, not an AgentFlow error.
- A parameter that would override AgentFlow's own arguments — `model`, `messages`, `system`,
  `tools` — is **refused** with a `ValueError` naming every offending key. `params` changes how a
  call is made, never what is asked.
