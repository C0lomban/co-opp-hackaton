"""Paste mode: use a Kylon agent's answer without an API key.

1. build_paste_prompt() writes the exact prompt a live call would send,
   plus the JSON format the answer must follow, as one block of text to
   paste into a Kylon agent.
2. parse_pasted_answer() reads the agent's reply and checks it against the
   same answer shape a live call uses. Anything wrong gives a readable
   error instead of a crash.

After that, the pasted answer goes through exactly the same code as a live
answer (quote checks, math, statuses).
"""

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

Answer = TypeVar("Answer", bound=BaseModel)

# Where each answer came from, recorded in reports and evidence.
SOURCE_SAMPLE = "sample"
SOURCE_PASTED = "kylon-agent-pasted"
SOURCE_API = "kylon-api"


class PastedAnswerError(ValueError):
    """The pasted answer can't be used. The message says why, in plain words."""


def build_paste_prompt(system_prompt: str, user_message: str,
                       answer_shape: type[BaseModel]) -> str:
    schema = json.dumps(answer_shape.model_json_schema(), indent=2)
    return (
        f"{system_prompt.strip()}\n\n"
        f"{user_message.strip()}\n\n"
        "## Answer format\n\n"
        "Answer with ONE JSON object and nothing else: no explanation before or "
        "after it. It must match this JSON Schema exactly. Include every field; "
        "use null where a field doesn't apply.\n\n"
        f"```json\n{schema}\n```\n"
    )


def _extract_json_text(text: str) -> str:
    """Agents often wrap JSON in ```json fences or add a sentence around it."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise PastedAnswerError("The pasted answer doesn't contain a JSON object ({ ... }).")
    return text[start:end + 1]


def _where(location: tuple) -> str:
    # ("rules", 2, "days") -> "rules[2].days"
    out = ""
    for part in location:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out or "(the whole answer)"


def parse_pasted_answer(text: str, answer_shape: type[Answer]) -> Answer:
    """Check the pasted text is valid JSON with exactly the expected shape."""
    raw = _extract_json_text(text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise PastedAnswerError(
            f"The pasted answer is not valid JSON (line {error.lineno}, "
            f"column {error.colno}: {error.msg}).") from None
    try:
        return answer_shape.model_validate(data)
    except ValidationError as error:
        problems = [f"  - {_where(e['loc'])}: {e['msg']}" for e in error.errors()]
        raise PastedAnswerError(
            "The pasted answer doesn't match the required format:\n"
            + "\n".join(problems[:15])
            + ("\n  - ..." if len(problems) > 15 else "")) from None
