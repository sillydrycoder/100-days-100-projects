"""Multi-tenant SQLite storage with mandatory TenantContext isolation.

Mirrors the PostgreSQL Row-Level Security contract in schema/postgres_rls.sql so local
DEMO_MODE execution enforces the exact same tenant boundaries on every query.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chunker import parse_textbook_markdown

BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_DIR = BASE_DIR / "sample_data"
VALID_ROLES = {"admin", "teacher", "student"}


@dataclass(frozen=True)
class TenantContext:
    """Explicit tenant scope required for every school-scoped database operation."""

    school_id: str

    def __post_init__(self) -> None:
        if not self.school_id or not self.school_id.strip():
            raise ValueError("TenantContext.school_id must be a non-empty tenant identifier.")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class MultiTenantStore:
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schools (
                school_id       TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                curriculum      TEXT NOT NULL,
                grades_json     TEXT NOT NULL,
                classes_json    TEXT NOT NULL,
                created_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id       TEXT NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
                external_id     TEXT NOT NULL,
                role            TEXT NOT NULL CHECK (role IN ('admin', 'teacher', 'student')),
                grade_level     TEXT NOT NULL,
                class_section   TEXT NOT NULL,
                display_name    TEXT NOT NULL,
                email           TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                UNIQUE (school_id, external_id),
                UNIQUE (school_id, email)
            );

            CREATE TABLE IF NOT EXISTS textbooks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id       TEXT NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
                title           TEXT NOT NULL,
                subject         TEXT NOT NULL,
                grade_level     TEXT NOT NULL,
                checksum_sha256 TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                UNIQUE (school_id, checksum_sha256)
            );

            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id       TEXT NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
                textbook_id     INTEGER NOT NULL REFERENCES textbooks(id) ON DELETE CASCADE,
                textbook_title  TEXT NOT NULL,
                subject         TEXT NOT NULL,
                grade_level     TEXT NOT NULL,
                chapter_title   TEXT NOT NULL,
                section_title   TEXT NOT NULL,
                page_number     INTEGER NOT NULL,
                block_type      TEXT NOT NULL,
                parent_context  TEXT NOT NULL,
                content         TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_school ON knowledge_chunks (school_id, subject, grade_level);

            CREATE TABLE IF NOT EXISTS vision_extractions (
                school_id       TEXT NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
                image_sha256    TEXT NOT NULL,
                model_used      TEXT NOT NULL,
                structured_json TEXT NOT NULL,
                tokens_spent    INTEGER NOT NULL,
                created_at      TEXT NOT NULL,
                PRIMARY KEY (school_id, image_sha256)
            );

            CREATE TABLE IF NOT EXISTS tutoring_turns (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id           TEXT NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
                session_id          TEXT NOT NULL,
                student_ref         TEXT NOT NULL,
                attempt_number      INTEGER NOT NULL,
                hint_level          INTEGER NOT NULL,
                model_tier          TEXT NOT NULL,
                vision_cache_hit    INTEGER NOT NULL DEFAULT 0,
                estimated_cost_usd  REAL NOT NULL DEFAULT 0.0,
                pii_redacted        INTEGER NOT NULL DEFAULT 0,
                redacted_prompt     TEXT NOT NULL,
                socratic_response   TEXT NOT NULL,
                citations_json      TEXT NOT NULL,
                created_at          TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    # ---- Schools ----
    def upsert_school(
        self,
        school_id: str,
        name: str,
        curriculum: str,
        grades: list[str],
        classes: list[str],
    ) -> dict[str, Any]:
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO schools (school_id, name, curriculum, grades_json, classes_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(school_id) DO UPDATE SET
                name = excluded.name,
                curriculum = excluded.curriculum,
                grades_json = excluded.grades_json,
                classes_json = excluded.classes_json
            """,
            (school_id.strip(), name.strip(), curriculum.strip(), json.dumps(grades), json.dumps(classes), now),
        )
        self.conn.commit()
        return self.get_school(TenantContext(school_id))

    def list_schools(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM schools ORDER BY name ASC").fetchall()
        result = []
        for r in rows:
            sid = r["school_id"]
            user_count = self.conn.execute(
                "SELECT COUNT(*) FROM users WHERE school_id = ?", (sid,)
            ).fetchone()[0]
            chunk_count = self.conn.execute(
                "SELECT COUNT(*) FROM knowledge_chunks WHERE school_id = ?", (sid,)
            ).fetchone()[0]
            book_count = self.conn.execute(
                "SELECT COUNT(*) FROM textbooks WHERE school_id = ?", (sid,)
            ).fetchone()[0]
            result.append(
                {
                    "school_id": sid,
                    "name": r["name"],
                    "curriculum": r["curriculum"],
                    "grades": json.loads(r["grades_json"]),
                    "classes": json.loads(r["classes_json"]),
                    "user_count": user_count,
                    "textbook_count": book_count,
                    "chunk_count": chunk_count,
                }
            )
        return result

    def get_school(self, tenant: TenantContext) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM schools WHERE school_id = ?", (tenant.school_id,)
        ).fetchone()
        if not row:
            raise KeyError(f"School tenant '{tenant.school_id}' does not exist.")
        return {
            "school_id": row["school_id"],
            "name": row["name"],
            "curriculum": row["curriculum"],
            "grades": json.loads(row["grades_json"]),
            "classes": json.loads(row["classes_json"]),
        }

    # ---- Bulk CSV Roster Onboarding (Tenant-Isolated) ----
    def import_roster_csv(self, tenant: TenantContext, csv_text: str) -> dict[str, Any]:
        self.get_school(tenant)
        reader = csv.DictReader(io.StringIO(csv_text.strip()))
        required_cols = {"external_id", "role", "grade_level", "class_section", "display_name", "email"}
        if not reader.fieldnames or not required_cols.issubset({c.strip() for c in reader.fieldnames}):
            raise ValueError(f"CSV must contain columns: {sorted(required_cols)}")

        inserted = 0
        updated = 0
        errors: list[str] = []
        now = utc_now()

        for row_num, raw in enumerate(reader, start=2):
            row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
            role = row["role"].lower()
            if role not in VALID_ROLES:
                errors.append(f"Row {row_num}: invalid role '{row['role']}'")
                continue
            if not row["external_id"] or not row["display_name"] or "@" not in row["email"]:
                errors.append(f"Row {row_num}: missing external_id, display_name, or valid email")
                continue

            existing = self.conn.execute(
                "SELECT id FROM users WHERE school_id = ? AND external_id = ?",
                (tenant.school_id, row["external_id"]),
            ).fetchone()
            if existing:
                self.conn.execute(
                    """
                    UPDATE users
                    SET role = ?, grade_level = ?, class_section = ?, display_name = ?, email = ?
                    WHERE id = ? AND school_id = ?
                    """,
                    (
                        role,
                        row["grade_level"],
                        row["class_section"],
                        row["display_name"],
                        row["email"],
                        existing["id"],
                        tenant.school_id,
                    ),
                )
                updated += 1
            else:
                self.conn.execute(
                    """
                    INSERT INTO users (school_id, external_id, role, grade_level, class_section, display_name, email, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tenant.school_id,
                        row["external_id"],
                        role,
                        row["grade_level"],
                        row["class_section"],
                        row["display_name"],
                        row["email"],
                        now,
                    ),
                )
                inserted += 1

        self.conn.commit()
        return {
            "school_id": tenant.school_id,
            "inserted": inserted,
            "updated": updated,
            "errors": errors,
            "total_users": len(self.list_users(tenant)),
        }

    def list_users(self, tenant: TenantContext) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT external_id, role, grade_level, class_section, display_name, email
            FROM users
            WHERE school_id = ?
            ORDER BY role ASC, external_id ASC
            """,
            (tenant.school_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- Hierarchical Textbook Ingestion (Tenant-Isolated) ----
    def ingest_textbook(
        self,
        tenant: TenantContext,
        title: str,
        subject: str,
        grade_level: str,
        raw_markdown: str,
    ) -> dict[str, Any]:
        self.get_school(tenant)
        checksum = hashlib.sha256(raw_markdown.encode("utf-8")).hexdigest()
        existing = self.conn.execute(
            "SELECT id FROM textbooks WHERE school_id = ? AND checksum_sha256 = ?",
            (tenant.school_id, checksum),
        ).fetchone()
        if existing:
            textbook_id = existing["id"]
            self.conn.execute(
                "DELETE FROM knowledge_chunks WHERE school_id = ? AND textbook_id = ?",
                (tenant.school_id, textbook_id),
            )
            deduplicated = True
        else:
            cur = self.conn.execute(
                """
                INSERT INTO textbooks (school_id, title, subject, grade_level, checksum_sha256, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (tenant.school_id, title.strip(), subject.strip(), grade_level.strip(), checksum, utc_now()),
            )
            textbook_id = int(cur.lastrowid)
            deduplicated = False

        parsed = parse_textbook_markdown(title.strip(), subject.strip(), grade_level.strip(), raw_markdown)
        counts_by_type: dict[str, int] = {"prose": 0, "table": 0, "equation": 0, "diagram": 0}

        for ch in parsed:
            counts_by_type[ch.block_type] = counts_by_type.get(ch.block_type, 0) + 1
            self.conn.execute(
                """
                INSERT INTO knowledge_chunks (
                    school_id, textbook_id, textbook_title, subject, grade_level,
                    chapter_title, section_title, page_number, block_type, parent_context, content
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant.school_id,
                    textbook_id,
                    title.strip(),
                    subject.strip(),
                    grade_level.strip(),
                    ch.chapter_title,
                    ch.section_title,
                    ch.page_number,
                    ch.block_type,
                    ch.parent_context,
                    ch.content,
                ),
            )

        self.conn.commit()
        return {
            "school_id": tenant.school_id,
            "textbook_id": textbook_id,
            "title": title.strip(),
            "subject": subject.strip(),
            "grade_level": grade_level.strip(),
            "deduplicated": deduplicated,
            "chunk_count": len(parsed),
            "counts_by_type": counts_by_type,
        }

    def list_chunks(
        self,
        tenant: TenantContext,
        subject: str | None = None,
        grade_level: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM knowledge_chunks WHERE school_id = ?"
        params: list[Any] = [tenant.school_id]
        if subject:
            query += " AND LOWER(subject) = LOWER(?)"
            params.append(subject)
        if grade_level:
            query += " AND LOWER(grade_level) = LOWER(?)"
            params.append(grade_level)
        query += " ORDER BY id ASC"
        return [dict(r) for r in self.conn.execute(query, params).fetchall()]

    # ---- Vision Extraction Content-Addressed Cache (Tenant-Isolated) ----
    def get_vision_cache(self, tenant: TenantContext, image_sha256: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT model_used, structured_json, tokens_spent, created_at
            FROM vision_extractions
            WHERE school_id = ? AND image_sha256 = ?
            """,
            (tenant.school_id, image_sha256),
        ).fetchone()
        if not row:
            return None
        return {
            "model_used": row["model_used"],
            "structured_json": json.loads(row["structured_json"]),
            "tokens_spent": row["tokens_spent"],
            "created_at": row["created_at"],
        }

    def put_vision_cache(
        self,
        tenant: TenantContext,
        image_sha256: str,
        model_used: str,
        structured_json: dict[str, Any],
        tokens_spent: int,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO vision_extractions (school_id, image_sha256, model_used, structured_json, tokens_spent, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(school_id, image_sha256) DO UPDATE SET
                structured_json = excluded.structured_json
            """,
            (tenant.school_id, image_sha256, model_used, json.dumps(structured_json), tokens_spent, utc_now()),
        )
        self.conn.commit()

    # ---- Tutoring Audit Log & Session History (Tenant-Isolated) ----
    def get_session_attempt_count(self, tenant: TenantContext, session_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM tutoring_turns WHERE school_id = ? AND session_id = ?",
            (tenant.school_id, session_id),
        ).fetchone()
        return int(row[0])

    def log_turn(
        self,
        tenant: TenantContext,
        session_id: str,
        student_ref: str,
        attempt_number: int,
        hint_level: int,
        model_tier: str,
        vision_cache_hit: bool,
        estimated_cost_usd: float,
        pii_redacted: bool,
        redacted_prompt: str,
        socratic_response: str,
        citations: list[dict[str, Any]],
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO tutoring_turns (
                school_id, session_id, student_ref, attempt_number, hint_level,
                model_tier, vision_cache_hit, estimated_cost_usd, pii_redacted,
                redacted_prompt, socratic_response, citations_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant.school_id,
                session_id,
                student_ref,
                attempt_number,
                hint_level,
                model_tier,
                1 if vision_cache_hit else 0,
                estimated_cost_usd,
                1 if pii_redacted else 0,
                redacted_prompt,
                socratic_response,
                json.dumps(citations),
                utc_now(),
            ),
        )
        self.conn.commit()

    def list_turns(self, tenant: TenantContext, limit: int = 25) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM tutoring_turns
            WHERE school_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (tenant.school_id, limit),
        ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["vision_cache_hit"] = bool(item["vision_cache_hit"])
            item["pii_redacted"] = bool(item["pii_redacted"])
            item["citations"] = json.loads(item.pop("citations_json"))
            out.append(item)
        return out

    # ---- Initial Sample Data Seeder ----
    def seed_sample_data(self) -> None:
        if self.list_schools():
            return
        schools = json.loads((SAMPLE_DIR / "schools_seed.json").read_text(encoding="utf-8"))
        for sc in schools:
            tenant = TenantContext(sc["school_id"])
            self.upsert_school(
                school_id=sc["school_id"],
                name=sc["name"],
                curriculum=sc["curriculum"],
                grades=sc["grades"],
                classes=sc["classes"],
            )
            csv_path = SAMPLE_DIR / sc["roster_csv"]
            if csv_path.exists():
                self.import_roster_csv(tenant, csv_path.read_text(encoding="utf-8"))
            for book in sc.get("textbooks", []):
                book_path = SAMPLE_DIR / book["file"]
                if book_path.exists():
                    self.ingest_textbook(
                        tenant=tenant,
                        title=book["title"],
                        subject=book["subject"],
                        grade_level=book["grade_level"],
                        raw_markdown=book_path.read_text(encoding="utf-8"),
                    )
