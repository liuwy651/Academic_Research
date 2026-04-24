def estimate_tokens(text: str) -> int:
    """Estimate token count for mixed Chinese/English text.

    Uses a conservative heuristic: each Unicode code point counts as 1 token
    for CJK characters (they compress poorly), and 1 token per 4 characters
    for ASCII. This overestimates slightly, which is the safe direction for
    budget enforcement.
    """
    if not text:
        return 0
    cjk = sum(1 for ch in text if '一' <= ch <= '鿿' or '㐀' <= ch <= '䶿')
    ascii_chars = len(text) - cjk
    return cjk + max(1, ascii_chars // 4)


def count_messages_tokens(messages: list[dict]) -> int:
    """Sum token estimates across a list of {role, content} message dicts."""
    return sum(estimate_tokens(m.get("content", "")) + 4 for m in messages)
    # +4 per message accounts for role/formatting overhead (mirrors OpenAI's counting)


def trim_to_budget(
    history: list[dict],
    user_content: str,
    budget: int,
) -> tuple[list[dict], bool]:
    """Drop oldest messages from history so the total fits within budget.

    Args:
        history: list of {role, content} dicts ordered oldest → newest.
        user_content: the new user message that will be appended after history.
        budget: maximum token count for history (does NOT include user_content).

    Returns:
        (trimmed_history, was_truncated)
    """
    user_tokens = estimate_tokens(user_content) + 4
    available = budget - user_tokens

    if available <= 0:
        return [], True

    kept: list[dict] = []
    tokens_used = 0

    # Walk newest → oldest, stop when budget exhausted
    for msg in reversed(history):
        msg_tokens = estimate_tokens(msg.get("content", "")) + 4
        if tokens_used + msg_tokens > available:
            return list(reversed(kept)), True
        kept.append(msg)
        tokens_used += msg_tokens

    return list(reversed(kept)), False
