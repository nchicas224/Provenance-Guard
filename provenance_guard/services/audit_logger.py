"""SQLite audit logging service."""

import json
import sqlite3
from pathlib import Path
from typing import Any

from provenance_guard.models import (
    AppealRecord,
    AttributionDecisionLogRecord,
    RequestLogRecord,
    SignalOutputLogRecord,
    SystemEventRecord,
)


class AuditLogger:
    """Writes durable audit checkpoints to SQLite."""

    def __init__(self, database_path: str | Path = "provenance_guard.db"):
        self.database_path = Path(database_path)
        self.initialize()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS request_logs (
                    request_id TEXT PRIMARY KEY,
                    route TEXT NOT NULL,
                    method TEXT NOT NULL,
                    creator_id TEXT,
                    content_type TEXT,
                    status_code INTEGER,
                    request_status TEXT NOT NULL,
                    error_code TEXT,
                    received_at TEXT NOT NULL,
                    completed_at TEXT,
                    duration_ms INTEGER,
                    client_label TEXT
                );

                CREATE TABLE IF NOT EXISTS attribution_decisions (
                    audit_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    creator_id TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    attribution_result TEXT NOT NULL,
                    ai_likelihood REAL NOT NULL,
                    confidence_score REAL NOT NULL,
                    confidence_level TEXT NOT NULL,
                    transparency_label TEXT NOT NULL,
                    appeal_guidance TEXT,
                    degraded INTEGER NOT NULL,
                    degradation_reason TEXT,
                    caution_flags TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS signal_outputs (
                    signal_id TEXT PRIMARY KEY,
                    audit_id TEXT,
                    request_id TEXT NOT NULL,
                    signal_name TEXT NOT NULL,
                    signal_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    ai_likelihood REAL,
                    confidence REAL,
                    confidence_label TEXT,
                    raw_output TEXT NOT NULL,
                    explanation TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS appeals (
                    appeal_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL,
                    creator_id TEXT NOT NULL,
                    original_attribution_result TEXT NOT NULL,
                    original_ai_likelihood REAL NOT NULL,
                    original_confidence_score REAL NOT NULL,
                    original_confidence_level TEXT NOT NULL,
                    original_transparency_label TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL,
                    contact_email TEXT,
                    reviewer_notes TEXT,
                    resolution TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS system_events (
                    event_id TEXT PRIMARY KEY,
                    request_id TEXT,
                    audit_id TEXT,
                    creator_id TEXT,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def log_request_received(self, record: RequestLogRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO request_logs (
                    request_id, route, method, creator_id, content_type,
                    request_status, received_at, client_label
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.request_id,
                    record.route,
                    record.method,
                    record.creator_id,
                    record.content_type,
                    record.request_status,
                    record.received_at,
                    record.client_label,
                ),
            )

    def update_request_log(self, record: RequestLogRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE request_logs
                SET request_status = ?,
                    status_code = ?,
                    error_code = ?,
                    completed_at = ?,
                    duration_ms = ?,
                    creator_id = COALESCE(?, creator_id),
                    content_type = COALESCE(?, content_type)
                WHERE request_id = ?
                """,
                (
                    record.request_status,
                    record.status_code,
                    record.error_code,
                    record.completed_at,
                    record.duration_ms,
                    record.creator_id,
                    record.content_type,
                    record.request_id,
                ),
            )

    def log_signal_output(self, record: SignalOutputLogRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO signal_outputs (
                    signal_id, audit_id, request_id, signal_name, signal_version,
                    status, ai_likelihood, confidence, confidence_label,
                    raw_output, explanation, error, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.signal_id,
                    record.audit_id,
                    record.request_id,
                    record.signal.name,
                    record.signal.version,
                    record.signal.status,
                    record.signal.ai_likelihood,
                    record.signal.confidence,
                    record.signal.confidence_label,
                    self._to_json(record.signal.raw_output),
                    record.signal.explanation,
                    record.signal.error,
                    record.created_at,
                ),
            )

    def log_attribution_decision(self, record: AttributionDecisionLogRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO attribution_decisions (
                    audit_id, request_id, creator_id, content_type,
                    attribution_result, ai_likelihood, confidence_score,
                    confidence_level, transparency_label, appeal_guidance,
                    degraded, degradation_reason, caution_flags, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.decision.audit_id,
                    record.request_id,
                    record.decision.creator_id,
                    record.content_type,
                    record.decision.attribution_result,
                    record.decision.ai_likelihood,
                    record.decision.confidence_score,
                    record.decision.confidence_level,
                    record.transparency_label,
                    record.appeal_guidance,
                    int(record.decision.degraded),
                    record.decision.degradation_reason,
                    self._to_json(record.decision.caution_flags),
                    record.created_at,
                ),
            )

    def log_appeal(self, appeal: AppealRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO appeals (
                    appeal_id, audit_id, creator_id, original_attribution_result,
                    original_ai_likelihood, original_confidence_score,
                    original_confidence_level, original_transparency_label,
                    reason, status, contact_email, reviewer_notes, resolution,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    appeal.appeal_id,
                    appeal.audit_id,
                    appeal.creator_id,
                    appeal.original_attribution_result,
                    appeal.original_ai_likelihood,
                    appeal.original_confidence_score,
                    appeal.original_confidence_level,
                    appeal.original_transparency_label,
                    appeal.reason,
                    appeal.status,
                    appeal.contact_email,
                    appeal.reviewer_notes,
                    appeal.resolution,
                    appeal.created_at,
                    appeal.updated_at,
                ),
            )

    def log_system_event(self, record: SystemEventRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO system_events (
                    event_id, request_id, audit_id, creator_id, event_type,
                    severity, message, details, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.event_id,
                    record.request_id,
                    record.audit_id,
                    record.creator_id,
                    record.event_type,
                    record.severity,
                    record.message,
                    self._to_json(record.details),
                    record.created_at,
                ),
            )

    def get_attribution_decision(self, audit_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM attribution_decisions WHERE audit_id = ?",
                (audit_id,),
            ).fetchone()
            return dict(row) if row else None

    def has_active_appeal(self, audit_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM appeals
                WHERE audit_id = ? AND status = 'under_review'
                LIMIT 1
                """,
                (audit_id,),
            ).fetchone()
            return row is not None

    def is_reachable(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1")
            return True
        except sqlite3.Error:
            return False

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _to_json(self, value: Any) -> str:
        return json.dumps(value, sort_keys=True)
