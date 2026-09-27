import re

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render(template: str, context: dict) -> str:
    """Minimal `{{var}}` substitution -- no control flow, no code execution.

    A missing variable renders as an empty string rather than raising, since a template
    is user-edited config (PATCH /notification-templates) and must never turn a typo'd
    placeholder into a 500 at send time.
    """
    return _PLACEHOLDER_RE.sub(lambda m: str(context.get(m.group(1), "")), template)
