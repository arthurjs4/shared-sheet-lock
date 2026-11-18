"""Normalisers used by the duplicate barrier."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse


def normalize_phone(value: object) -> str:
    """Digits only, keeping the last 10 (drops country code). '' if too short."""
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[-10:] if len(digits) >= 10 else ""


def normalize_domain(value: object) -> str:
    """Lower-case host without scheme, 'www.' or path. '' if empty."""
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "//" not in text:
        text = "//" + text
    host = urlparse(text).netloc.split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def normalize_name(value: object) -> str:
    """Lower-case, accent-free, alphanumerics only."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", text.lower())
