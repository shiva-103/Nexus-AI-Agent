import json
import os
from typing import Any
from groq import Groq

DEFAULT_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

def get_client():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None
    return Groq(api_key=key)

def infer_mappings_with_groq(source_columns, target_schema):
    client = get_client()
    if not client:
        return None

    prompt = f'''
You are a data migration mapping agent.

Target schema:
{json.dumps(target_schema, indent=2)}

Source columns:
{json.dumps(list(source_columns), indent=2)}

For every source column, choose the best target field if there is enough evidence.
Do NOT invent target fields.
Return ONLY JSON with this shape:
{{
  "mappings": [
    {{
      "source": "source column",
      "target": "target field or null",
      "confidence": 0.0,
      "reason": "short explanation",
      "decision": "auto|review|unmapped"
    }}
  ]
}}

Rules:
- confidence is between 0 and 1.
- auto only when the semantic meaning is clear and confidence >= 0.90.
- review when there is plausible ambiguity or confidence is 0.70-0.89.
- unmapped below 0.70.
- Prefer precision over guessing.
'''
    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You are a precise enterprise data migration agent."},
            {"role": "user", "content": prompt},
        ],
    )
    return json.loads(response.choices[0].message.content)

def explain_escalation(issue, record=None):
    client = get_client()
    if not client:
        return "The agent could not confidently resolve this case using deterministic rules."
    prompt = f'''
Explain this data migration escalation to a non-technical implementation consultant.
Issue: {issue}
Record: {json.dumps(record or {}, default=str)}
Give a concise explanation, why the agent stopped, and what decision the human needs to make.
'''
    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        temperature=0.1,
        messages=[
            {"role": "system", "content": "You explain data migration exceptions clearly and briefly."},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content
