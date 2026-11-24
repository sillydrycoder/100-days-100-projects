"""Structure-aware hierarchical textbook parser and chunker.

Preserves Book -> Chapter -> Section -> Page hierarchy and keeps complex educational
elements (Markdown tables, LaTeX equation blocks, and diagram descriptors) atomic so
equations and tables are never broken mid-structure during RAG ingestion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PAGE_RE = re.compile(r"^\[page:\s*(\d+)\]\s*$", re.IGNORECASE)
DIAGRAM_RE = re.compile(r"^\[diagram:\s*(.+)\]\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class KnowledgeChunk:
    chapter_title: str
    section_title: str
    page_number: int
    block_type: str  # prose | table | equation | diagram
    parent_context: str
    content: str


def _split_prose_with_overlap(text: str, max_chars: int = 550, overlap_chars: int = 80) -> list[str]:
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return [clean] if clean else []

    sentences = re.split(r"(?<=[.!?])\s+", clean)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            tail = current[-overlap_chars:].strip() if current and overlap_chars else ""
            current = f"{tail} {sentence}".strip() if tail else sentence

    if current:
        chunks.append(current)
    return chunks


def parse_textbook_markdown(textbook_title: str, subject: str, grade_level: str, raw_text: str) -> list[KnowledgeChunk]:
    """Parse structured textbook content into atomic, hierarchy-preserving chunks."""
    lines = raw_text.splitlines()
    chapter = "Introduction"
    section = "Overview"
    page_number = 1

    chunks: list[KnowledgeChunk] = []
    i = 0
    n = len(lines)

    def make_context(block_type: str) -> str:
        return f"{textbook_title} ({subject}, {grade_level}) > {chapter} > {section} [p.{page_number} | {block_type}]"

    while i < n:
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # 1. Chapter heading
        if line.startswith("# ") and not line.startswith("## "):
            chapter = line[2:].strip()
            section = "Overview"
            i += 1
            continue

        # 2. Section heading
        if line.startswith("## "):
            section = line[3:].strip()
            i += 1
            continue

        # 3. Page marker
        page_match = PAGE_RE.match(line)
        if page_match:
            page_number = int(page_match.group(1))
            i += 1
            continue

        # 4. Atomic Diagram descriptor block
        diag_match = DIAGRAM_RE.match(line)
        if diag_match:
            chunks.append(
                KnowledgeChunk(
                    chapter_title=chapter,
                    section_title=section,
                    page_number=page_number,
                    block_type="diagram",
                    parent_context=make_context("diagram"),
                    content=diag_match.group(1).strip(),
                )
            )
            i += 1
            continue

        # 5. Atomic LaTeX equation block ($$ ... $$)
        if line.startswith("$$"):
            eq_lines = [line]
            if line == "$$" or not line.endswith("$$") or len(line) == 2:
                i += 1
                while i < n:
                    eq_lines.append(lines[i].strip())
                    if lines[i].strip().endswith("$$"):
                        i += 1
                        break
                    i += 1
            else:
                i += 1
            eq_body = "\n".join(eq_lines).strip()
            chunks.append(
                KnowledgeChunk(
                    chapter_title=chapter,
                    section_title=section,
                    page_number=page_number,
                    block_type="equation",
                    parent_context=make_context("equation"),
                    content=eq_body,
                )
            )
            continue

        # 6. Atomic Markdown table block
        if line.startswith("|") and line.endswith("|"):
            table_lines = []
            while i < n and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            chunks.append(
                KnowledgeChunk(
                    chapter_title=chapter,
                    section_title=section,
                    page_number=page_number,
                    block_type="table",
                    parent_context=make_context("table"),
                    content="\n".join(table_lines),
                )
            )
            continue

        # 7. Prose paragraph (collect contiguous plain text lines)
        prose_lines = []
        while i < n:
            cur = lines[i].strip()
            if (
                not cur
                or cur.startswith("# ")
                or cur.startswith("## ")
                or cur.startswith("$$")
                or (cur.startswith("|") and cur.endswith("|"))
                or PAGE_RE.match(cur)
                or DIAGRAM_RE.match(cur)
            ):
                break
            prose_lines.append(cur)
            i += 1

        paragraph = " ".join(prose_lines)
        for piece in _split_prose_with_overlap(paragraph):
            chunks.append(
                KnowledgeChunk(
                    chapter_title=chapter,
                    section_title=section,
                    page_number=page_number,
                    block_type="prose",
                    parent_context=make_context("prose"),
                    content=piece,
                )
            )

    return chunks
