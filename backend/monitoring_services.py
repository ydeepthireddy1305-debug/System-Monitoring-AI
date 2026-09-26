from typing import Any

from backend.database import get_connection
from backend.models import Metrics


ALERT_RULES = {
    "cpu": {
        "threshold": 80.0,
        "alert_type": "CPU",
        "message": "High CPU usage detected",
        "severity": "WARNING",
    },
    "ram": {
        "threshold": 85.0,
        "alert_type": "RAM",
        "message": "High RAM usage detected",
        "severity": "WARNING",
    },
    "disk": {
        "threshold": 90.0,
        "alert_type": "DISK",
        "message": "High disk usage detected",
        "severity": "CRITICAL",
    },
}


INSERT_METRIC_QUERY = """
    INSERT INTO metrics
        (cpu, ram, disk, bytes_sent, bytes_received)
    VALUES
        (%s, %s, %s, %s, %s)
"""


SELECT_OPEN_ALERTS_QUERY = """
    SELECT alert_type
    FROM alerts
    WHERE status = 'OPEN'
      AND alert_type IN (%s, %s, %s)
"""


INSERT_ALERT_QUERY = """
    INSERT INTO alerts
        (metric_id, alert_type, message, severity, status)
    VALUES
        (%s, %s, %s, %s, 'OPEN')
"""


RESOLVE_ALERT_QUERY = """
    UPDATE alerts
    SET status = 'RESOLVED',
        resolved_at = CURRENT_TIMESTAMP
    WHERE alert_type = %s
      AND status = 'OPEN'
"""


INSERT_INCIDENT_QUERY = """
    INSERT INTO incidents
        (metric_id, incident_type, severity, description, status)
    VALUES
        (%s, %s, %s, %s, 'OPEN')
"""


SELECT_OPEN_INCIDENTS_QUERY = """
    SELECT incident_type
    FROM incidents
    WHERE status = 'OPEN'
      AND incident_type IN (%s, %s, %s)
"""


def save_metrics(data: Metrics) -> None:
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            metric_id = insert_metric(cursor, data)

            process_alerts(
                cursor,
                data,
                metric_id,
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def insert_metric(cursor: Any, data: Metrics) -> int:
    cursor.execute(
        INSERT_METRIC_QUERY,
        (
            data.cpu,
            data.ram,
            data.disk,
            data.bytes_sent,
            data.bytes_received,
        ),
    )

    return cursor.lastrowid


def get_open_alert_types(cursor: Any) -> set[str]:
    alert_types = tuple(
        rule["alert_type"]
        for rule in ALERT_RULES.values()
    )

    cursor.execute(
        SELECT_OPEN_ALERTS_QUERY,
        alert_types,
    )

    return {
        row[0]
        for row in cursor.fetchall()
    }


def get_open_incident_types(cursor: Any) -> set[str]:
    incident_types = tuple(
        rule["alert_type"]
        for rule in ALERT_RULES.values()
    )

    cursor.execute(
        SELECT_OPEN_INCIDENTS_QUERY,
        incident_types,
    )

    return {
        row[0]
        for row in cursor.fetchall()
    }


def process_alerts(
    cursor: Any,
    data: Metrics,
    metric_id: int,
) -> None:
    open_alert_types = get_open_alert_types(cursor)
    open_incident_types = get_open_incident_types(cursor)

    alerts_to_create = []
    alerts_to_resolve = []
    incidents_to_create = []

    for metric_name, rule in ALERT_RULES.items():
        metric_value = getattr(data, metric_name)
        alert_type = rule["alert_type"]

        if metric_value > rule["threshold"]:
            if alert_type not in open_alert_types:
                alerts_to_create.append(
                    (
                        metric_id,
                        alert_type,
                        rule["message"],
                        rule["severity"],
                    )
                )

            if alert_type not in open_incident_types:
                incidents_to_create.append(
                    (
                        metric_id,
                        alert_type,
                        rule["severity"],
                        rule["message"],
                    )
                )

        elif alert_type in open_alert_types:
            alerts_to_resolve.append(
                (alert_type,)
            )

    if alerts_to_create:
        cursor.executemany(
            INSERT_ALERT_QUERY,
            alerts_to_create,
        )

    if alerts_to_resolve:
        cursor.executemany(
            RESOLVE_ALERT_QUERY,
            alerts_to_resolve,
        )

    if incidents_to_create:
        cursor.executemany(
            INSERT_INCIDENT_QUERY,
            incidents_to_create,
        )
