"""Redact secrets from any text before it is cached, logged, or returned.

Upstream APIs echo the request api_key back in their response bodies (PVWatts
under `inputs`, EIA under `request.params`), so the raw body must never be
persisted to the on-disk cache or surfaced to the agent verbatim. One helper,
used at every boundary where a body or error string could carry the key.
"""

from urllib.parse import quote

REDACTED = "REDACTED"


def scrub_secret(text: str, secret: str | None) -> str:
    """Replace `secret` and its URL-encoded form with a placeholder.

    Fails safe: an empty/None secret returns the text unchanged. Redacting the
    key's string value inside a JSON body keeps the body valid JSON (a quoted
    value is swapped for another quoted value), so callers can still parse it.
    """
    if not secret:
        return text
    cleaned = text.replace(secret, REDACTED)
    encoded = quote(secret, safe="")
    if encoded != secret:
        cleaned = cleaned.replace(encoded, REDACTED)
    return cleaned
