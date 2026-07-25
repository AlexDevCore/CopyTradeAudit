"""Entry point: prints environment status on startup."""

import platform
from pathlib import Path

from anthropic import Anthropic

from src.config import PROJECT_NAME, env_file_exists, get_env, load_environment
from src.logger import get_logger

log = get_logger(__name__)


def call_claude(prompt: str) -> str | None:
    """Send a single prompt to Claude and return the reply text.

    Returns None (without making a network call) if ANTHROPIC_API_KEY is not
    set, so the project stays runnable in CI/clean environments without a key.
    """
    api_key = get_env("ANTHROPIC_API_KEY")
    if not api_key:
        log.info("ANTHROPIC_API_KEY not set - skipping Claude call")
        return None

    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def main() -> None:
    load_environment()
    log.info("project name: %s", PROJECT_NAME)
    log.info("Python version: %s", platform.python_version())
    log.info("working directory: %s", Path.cwd())
    log.info(".env exists: %s", env_file_exists())

    reply = call_claude("Say a short one-sentence hello from ai-command-center.")
    if reply is not None:
        log.info("Claude replied: %s", reply)

    log.info("AI command center ready")


if __name__ == "__main__":
    main()
