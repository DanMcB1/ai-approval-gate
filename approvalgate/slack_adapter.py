"""Optional real-Slack adapter. Off by default. Never used in the demo path.

This exists so a later production version has a documented seam. The
running app uses a mock Slack-style inbox in Streamlit. This module
does not open a network connection unless APPROVAL_GATE_SLACK_ENABLED=true
*and* SLACK_BOT_TOKEN is set. The demo and the tests leave those unset.
"""

from __future__ import annotations

from typing import Any

from approvalgate import settings


def slack_is_enabled() -> bool:
    return bool(
        settings.slack_enabled()
        and settings.slack_bot_token()
        and settings.slack_signing_secret()
        and settings.slack_channel()
    )


def maybe_notify_slack(row: dict[str, Any]) -> None:
    """No-op unless the real Slack adapter is explicitly enabled."""
    if not slack_is_enabled():
        return
    # Intentionally not implemented for this demo: we refuse to post
    # even if someone turns the flag on without reviewing the code.
    raise RuntimeError(
        "Real Slack delivery is documented but not implemented in this portfolio demo. "
        "Clear APPROVAL_GATE_SLACK_ENABLED and use the mock inbox in the app."
    )


def describe() -> str:
    if slack_is_enabled():
        return "Real Slack adapter flag is on — this demo will refuse to post (see README)."
    return "Real Slack adapter is off (default). Approvals go through the mock inbox in the app."
