# Prompt Templates

This directory contains Jinja2 templates (.j2 files) for all LLM prompts used by agents.

## Structure

```
prompts/
├── prompt_manager.py      # PromptManager utility for loading/rendering templates
├── planner/              # Planner agent prompts
│   ├── analyze.j2
│   ├── retry_with_feedback.j2
│   └── plan_next_step.j2
├── executor/             # Executor agent prompts
├── validator/            # Validator agent prompts
└── responder/            # Responder agent prompts
```

## Usage

### Basic Usage

```python
from backend.agents.prompts.prompt_manager import render_prompt

# Render a template with variables
prompt = render_prompt(
    "planner/analyze.j2",
    user_message="Show me all invoices",
    history=[],
)

# Pass to LLM
result = llm.extract_json(prompt, temperature=0.2)
```

### Using PromptManager Directly

```python
from backend.agents.prompts.prompt_manager import get_prompt_manager

pm = get_prompt_manager()
prompt = pm.render("planner/analyze.j2", user_message="...", history=[])
```

## Benefits

✅ **Separation of Concerns** - Prompts separated from code logic
✅ **Version Control** - Track prompt changes with clear diffs
✅ **Reusability** - Share common sections via Jinja2 includes/macros
✅ **Easier A/B Testing** - Swap templates without code changes
✅ **Better Collaboration** - Non-engineers can edit prompts

## Template Syntax

Jinja2 templates support:
- **Variables**: `{{ user_message }}`
- **Filters**: `{{ completed_steps|length }}`
- **Conditionals**: `{% if history %}...{% endif %}`
- **Loops**: `{% for step in steps %}...{% endfor %}`
- **Includes**: `{% include "common/system_context.j2" %}`
- **Macros**: Reusable template functions

## Example Template

```jinja2
{# planner/analyze.j2 #}
Analyze this user query and decide how to handle it.

User Query: "{{ user_message }}"
{% if history %}
Conversation History: {{ history[-5:] }}
{% endif %}

Available Routes:
1. "generic_response" - For greetings or out-of-scope queries
2. "execution_plan" - For data queries requiring tools
3. "clarification" - When query is ambiguous

Respond in JSON:
{
    "route": "<route_type>",
    "reasoning": "<why this route>"
}
```

## Best Practices

1. **One template per prompt** - Don't mix multiple prompts in one file
2. **Use descriptive names** - `analyze.j2`, not `prompt1.j2`
3. **Add comments** - Use `{# comment #}` for complex logic
4. **Test templates** - Verify variable substitution works correctly
5. **Keep DRY** - Extract common sections to shared templates

## Migrating Existing Prompts

To migrate a hardcoded f-string prompt:

**Before (hardcoded):**
```python
prompt = f"""
Analyze this query: {user_message}
History: {history}
"""
```

**After (template):**
```python
# Create: prompts/agent_name/action.j2
prompt = render_prompt(
    "agent_name/action.j2",
    user_message=user_message,
    history=history,
)
```

## Configuration

PromptManager settings:
- `trim_blocks=True` - Remove newlines after blocks
- `lstrip_blocks=True` - Strip leading whitespace
- `keep_trailing_newline=False` - No trailing newline

These settings keep prompts clean and compact.
