from typing import Any

from backend.database import get_connection


METRIC_HISTORY_LIMIT = 60
INCIDENT_HISTORY_LIMIT = 20
RISK_HISTORY_LIMIT = 60


LATEST_METRICS_QUERY = """
    SELECT
        id,
        cpu,
        ram,
        disk,
        bytes_sent,
        bytes_received,
        recorded_at
    FROM metrics
    ORDER BY recorded_at DESC, id DESC
    LIMIT 1
"""


METRIC_HISTORY_QUERY = """
    SELECT
        id,
        cpu,
        ram,
        disk,
        bytes_sent,
        bytes_received,
        recorded_at
    FROM metrics
    ORDER BY recorded_at DESC, id DESC
    LIMIT %s
"""


INCIDENT_HISTORY_QUERY = """
    SELECT
        i.id AS incident_id,
        i.metric_id,
        i.incident_type,
        i.severity,
        i.description,
        i.started_at,
        i.resolved_at,
        i.status,

        COALESCE(
            i.risk_score,
            fp.risk_score
        ) AS risk_score,

        COALESCE(
            i.risk_level,
            fp.risk_level
        ) AS risk_level,

        ia.analysis AS ai_analysis,

        rd.action AS agent_action,
        rd.decision AS agent_decision,
        rd.reason AS agent_reason,

        ra.status AS remediation_status,
        ra.details AS remediation_details,

        rv.status AS recovery_status,
        rv.samples_checked AS recovery_samples,
        rv.details AS recovery_details

    FROM incidents i

    LEFT JOIN failure_predictions fp
        ON fp.id = (
            SELECT fp2.id
            FROM failure_predictions fp2
            WHERE fp2.metric_id = i.metric_id
            ORDER BY
                fp2.predicted_at DESC,
                fp2.id DESC
            LIMIT 1
        )

    LEFT JOIN incident_analysis ia
        ON ia.id = (
            SELECT ia2.id
            FROM incident_analysis ia2
            WHERE ia2.incident_id = i.id
            ORDER BY
                ia2.created_at DESC,
                ia2.id DESC
            LIMIT 1
        )

    LEFT JOIN remediation_decisions rd
        ON rd.id = (
            SELECT rd2.id
            FROM remediation_decisions rd2
            WHERE rd2.incident_id = i.id
            ORDER BY
                rd2.created_at DESC,
                rd2.id DESC
            LIMIT 1
        )

    LEFT JOIN remediation_actions ra
        ON ra.id = (
            SELECT ra2.id
            FROM remediation_actions ra2
            WHERE ra2.incident_id = i.id
            ORDER BY
                ra2.started_at DESC,
                ra2.id DESC
            LIMIT 1
        )

    LEFT JOIN recovery_verifications rv
        ON rv.id = (
            SELECT rv2.id
            FROM recovery_verifications rv2
            WHERE rv2.incident_id = i.id
            ORDER BY
                rv2.verified_at DESC,
                rv2.id DESC
            LIMIT 1
        )

    ORDER BY
        i.started_at DESC,
        i.id DESC

    LIMIT %s
"""


RISK_HISTORY_QUERY = """
    SELECT
        id,
        metric_id,
        risk_score,
        risk_level,
        predicted_at
    FROM failure_predictions
    ORDER BY
        predicted_at DESC,
        id DESC
    LIMIT %s
"""


INCIDENT_COUNT_QUERY = """
    SELECT
        COUNT(*) AS total_incidents,
        SUM(
            CASE
                WHEN status = 'OPEN'
                THEN 1
                ELSE 0
            END
        ) AS open_incidents,
        SUM(
            CASE
                WHEN status = 'RESOLVED'
                THEN 1
                ELSE 0
            END
        ) AS resolved_incidents
    FROM incidents
"""


ANOMALY_COUNT_QUERY = """
    SELECT
        COUNT(*) AS total_anomalies
    FROM anomaly_events
"""


REMEDIATION_COUNT_QUERY = """
    SELECT
        COUNT(*) AS total_actions,
        SUM(
            CASE
                WHEN status = 'SUCCESS'
                THEN 1
                ELSE 0
            END
        ) AS successful_actions,
        SUM(
            CASE
                WHEN status = 'FAILED'
                THEN 1
                ELSE 0
            END
        ) AS failed_actions,
        SUM(
            CASE
                WHEN status = 'BLOCKED'
                THEN 1
                ELSE 0
            END
        ) AS blocked_actions
    FROM remediation_actions
"""


RECOVERY_COUNT_QUERY = """
    SELECT
        COUNT(*) AS total_verifications,
        SUM(
            CASE
                WHEN status = 'RECOVERED'
                THEN 1
                ELSE 0
            END
        ) AS recovered,
        SUM(
            CASE
                WHEN status = 'NOT_RECOVERED'
                THEN 1
                ELSE 0
            END
        ) AS not_recovered,
        SUM(
            CASE
                WHEN status = 'TIMEOUT'
                THEN 1
                ELSE 0
            END
        ) AS timeouts
    FROM recovery_verifications
"""


def _fetch_one(
    cursor: Any,
    query: str,
) -> dict[str, Any] | None:
    cursor.execute(query)
    return cursor.fetchone()


def get_dashboard_data() -> dict[str, Any]:
    connection = get_connection()

    try:
        with connection.cursor(
            dictionary=True
        ) as cursor:

            # ---------------------------------------------
            # Latest resource values
            # ---------------------------------------------

            latest_metrics = _fetch_one(
                cursor,
                LATEST_METRICS_QUERY,
            )

            # ---------------------------------------------
            # Resource history
            # ---------------------------------------------

            cursor.execute(
                METRIC_HISTORY_QUERY,
                (METRIC_HISTORY_LIMIT,),
            )

            metric_history = cursor.fetchall()

            metric_history.reverse()

            # ---------------------------------------------
            # Incident + AI + Agent + Remediation +
            # Recovery history
            # ---------------------------------------------

            cursor.execute(
                INCIDENT_HISTORY_QUERY,
                (INCIDENT_HISTORY_LIMIT,),
            )

            incidents = cursor.fetchall()

            # ---------------------------------------------
            # Failure-risk history
            # ---------------------------------------------

            cursor.execute(
                RISK_HISTORY_QUERY,
                (RISK_HISTORY_LIMIT,),
            )

            risk_history = cursor.fetchall()

            risk_history.reverse()

            # ---------------------------------------------
            # Incident statistics
            # ---------------------------------------------

            incident_counts = _fetch_one(
                cursor,
                INCIDENT_COUNT_QUERY,
            )

            # ---------------------------------------------
            # Anomaly statistics
            # ---------------------------------------------

            anomaly_counts = _fetch_one(
                cursor,
                ANOMALY_COUNT_QUERY,
            )

            # ---------------------------------------------
            # Remediation statistics
            # ---------------------------------------------

            remediation_counts = _fetch_one(
                cursor,
                REMEDIATION_COUNT_QUERY,
            )

            # ---------------------------------------------
            # Recovery statistics
            # ---------------------------------------------

            recovery_counts = _fetch_one(
                cursor,
                RECOVERY_COUNT_QUERY,
            )

        return {
            "latest_metrics": latest_metrics,
            "metric_history": metric_history,
            "incidents": incidents,
            "risk_history": risk_history,
            "statistics": {
                "incidents": incident_counts,
                "anomalies": anomaly_counts,
                "remediation": remediation_counts,
                "recovery": recovery_counts,
            },
        }

    finally:
        connection.close()