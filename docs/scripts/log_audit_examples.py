from pathlib import Path
from typing import Any
import sqlite3

from provenance_guard.services.audit_logger import AuditLogger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
print(PROJECT_ROOT)
DATABASE_PATH = PROJECT_ROOT / "provenance_guard.db"

def get_audit_summary_rows() -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT
            d.created_at,
            d.audit_id,
            d.request_id,
            d.creator_id,
            d.content_type,
            d.attribution_result,
            ROUND(d.ai_likelihood, 4) AS final_ai_likelihood,
            ROUND(d.confidence_score, 4) AS confidence_score,
            d.confidence_level,
            d.degraded,
            ROUND(g.ai_likelihood, 4) AS groq_ai_likelihood,
            ROUND(g.confidence, 4) AS groq_confidence,
            ROUND(s.ai_likelihood, 4) AS stylometric_ai_likelihood,
            ROUND(s.confidence, 4) AS stylometric_confidence,
            COALESCE(a.status, 'no_appeal') AS appeal_status
            FROM attribution_decisions d
            LEFT JOIN signal_outputs g
            ON g.audit_id = d.audit_id
            AND g.signal_name = 'groq_semantic'
            LEFT JOIN signal_outputs s
            ON s.audit_id = d.audit_id
            AND s.signal_name = 'stylometric'
            LEFT JOIN appeals a
            ON a.audit_id = d.audit_id
            ORDER BY d.created_at DESC
            LIMIT 5;
            """
        )
        return [dict(row) for row in rows ]

def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection

def log_audits():
    results = get_audit_summary_rows()
    records = [
        "\n".join(f"[{key}: {value}]" for key, value in row.items())
        for row in results
    ]
    for record in records:
        print(f"{record}\n")

if __name__ == "__main__":
    log_audits()
