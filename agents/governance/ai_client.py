"""The one place that talks to Claude. Both agents use it.

The API key is read from agents/governance/.env (ANTHROPIC_API_KEY).
It is never written in the code.
"""

import os
import sys
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
MODEL = "claude-opus-5-5"

Answer = TypeVar("Answer", bound=BaseModel)


def ask_claude(system_prompt: str, user_message: str, answer_shape: type[Answer]) -> Answer:
    """Send one request and get back an answer that fits `answer_shape`."""
    # Imported here so the rest of the project (and the tests) work even
    # without the anthropic library or an API key.
    import anthropic
    from dotenv import load_dotenv

    # Reads .env and puts its values into the environment.
    load_dotenv(HERE / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(
            "No ANTHROPIC_API_KEY found. Copy .env.example to .env and add your key, "
            "or run with --use-sample to use the saved sample answer."
        )

    client = anthropic.Anthropic()  # picks up ANTHROPIC_API_KEY automatically
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "high"},  # careful work matters more than speed here
        # If Claude's safety filter wrongly declines, retry on a fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        output_format=answer_shape,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        sys.exit(f"The AI did not return an answer (stop reason: {response.stop_reason}).")
    return response.parsed_output
