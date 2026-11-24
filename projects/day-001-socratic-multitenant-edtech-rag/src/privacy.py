"""FERPA/COPPA-aware PII redaction layer executed before external LLM/VLM calls."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")
STUDENT_ID_RE = re.compile(r"\b(?:STU|TCH)-\d{2,8}\b", re.IGNORECASE)


@dataclass(frozen=True)
class RedactionResult:
    redacted_text: str
    redacted_types: list[str]
    pii_detected: bool


def pseudonymize_student(school_id: str, student_ref: str) -> str:
    """Create a deterministic, non-reversible tenant-scoped student hash for audit logs."""
    digest = hashlib.sha256(f"{school_id}::{student_ref}".encode("utf-8")).hexdigest()[:12]
    return f"anon_{digest}"


def redact_pii(text: str, known_names: list[str] | None = None) -> RedactionResult:
    """Strip emails, phone numbers, roster IDs, and known student/teacher names."""
    cleaned = text
    found: list[str] = []

    if EMAIL_RE.search(cleaned):
        cleaned = EMAIL_RE.sub("[REDACTED_EMAIL]", cleaned)
        found.append("email")

    if PHONE_RE.search(cleaned):
        cleaned = PHONE_RE.sub("[REDACTED_PHONE]", cleaned)
        found.append("phone")

    if STUDENT_ID_RE.search(cleaned):
        cleaned = STUDENT_ID_RE.sub("[REDACTED_ID]", cleaned)
        found.append("roster_id")

    for name in known_names or []:
        trimmed = name.strip()
        if len(trimmed) < 3:
            continue
        pattern = re.compile(rf"\b{re.escape(trimmed)}\b", re.IGNORECASE)
        if pattern.search(cleaned):
            cleaned = pattern.sub("[REDACTED_NAME]", cleaned)
            if "roster_name" not in found:
                found.append("roster_name")

    return RedactionResult(
        redacted_text=cleaned,
        redacted_types=found,
        pii_detected=bool(found),
    )
