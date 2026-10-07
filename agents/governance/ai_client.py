"""The one place that talks to Claude. Both agents use it.

All requests go through the Kylon proxy, never straight to Anthropic.
Settings come from agents/governance/.env and are never written in the code:
  KYLON_API_KEY   required; sent to Kylon in the x-api-key header
  KYLON_BASE_URL  optional; defaults to the Kylon Anthropic proxy below
  CLAUDE_MODEL    optional; defaults to claude-opus-5-5
"""

import os
import sys
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE / ".env"

# ---------------------------------------------------------------------------
# KYLON PROXY ADDRESS (change it here, or set KYLON_BASE_URL in .env)
# The Anthropic library adds "/v1/messages" to this, so requests go to
# https://api.kylon.io/proxy/anthropic/v1/messages
# ---------------------------------------------------------------------------
DEFAULT_BASE_URL = "https://api.kylon.io/proxy/anthropic"
DEFAULT_MODEL = "claude-opus-5-5"

Answer = TypeVar("Answer", bound=BaseModel)


def _load_env() -> None:
    # Reads .env and puts its values into the environment (without
    # overwriting values that are already set).
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE)


def model_name() -> str:
    _load_env()
    return os.environ.get("CLAUDE_MODEL") or DEFAULT_MODEL


def make_client():
    """An Anthropic client that sends every request to Kylon, with the Kylon key."""
    import anthropic

    _load_env()
    key = os.environ.get("KYLON_API_KEY")
    if not key:
        sys.exit(
            "No KYLON_API_KEY found. Copy .env.example to .env and add your Kylon key, "
            "or run with --use-sample to use the saved sample answers."
        )
    # api_key is sent as the x-api-key header. Passing it (and base_url)
    # explicitly means no other Anthropic key or address on this computer
    # is ever used.
    return anthropic.Anthropic(
        api_key=key,
        base_url=os.environ.get("KYLON_BASE_URL") or DEFAULT_BASE_URL,
    )


def ask_claude(system_prompt: str, user_message: str, answer_shape: type[Answer]) -> Answer:
    """Send one request through Kylon and get back an answer that fits `answer_shape`."""
    client = make_client()
    response = client.beta.messages.parse(
        model=model_name(),
        max_tokens=16000,
        output_config={"effort": "high"},  # careful work matters more than speed here
        # If Claude's safety filter wrongly declines, retry on a fallback model.
        # If Kylon rejects this, remove these two lines first.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        output_format=answer_shape,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        sys.exit(f"The AI did not return an answer (stop reason: {response.stop_reason}).")
    return response.parsed_output
