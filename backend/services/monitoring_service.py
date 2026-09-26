from datetime import datetime
from typing import Any

from backend.database import get_connection
from backend.models import Metrics


# ---------------------------------------------------------------------------
# Monitoring configuration
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Anti-flapping configuration
# ---------------------------------------------------------------------------

# Require 3 consecutive abnormal samples before opening.
ABNORMAL_SAMPLES_REQUIRED = 3

# Require 3 consecutive normal samples before resolving.
NORMAL_SAMPLES_REQUIRED = 3

# After resolving an incident, wait before allowing a new one.
RESOLUTION_COOLDOWN_SECONDS = 60


# ---------------------------------------------------------------------------
# In-memory consecutive-sample state
# ---------------------------------------------------------------------------

# State is maintained independently for CPU, RAM and DISK.
#
# Example:
# CPU -> abnormal=2, normal=0
# RAM -> abnormal=0, normal=1
# DISK -> abnormal=3, normal=0
#
# This prevents a single fluctuating metric from repeatedly opening
# and resolving incidents.
STREAK_STATE: dict[str, dict[str, int]] = {
    rule["alert_type"]: {
        "abnormal": 0,
        "normal": 0,
    }
    for rule in ALERT_RULES.values()
}


# ---------------------------------------------------------------------------
# SQL queries
# ---------------------------------------------------------------------------

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


RESOLVE_INCIDENT_QUERY = """
    UPDATE incidents
    SET status = 'RESOLVED',
        resolved_at = CURRENT_TIMESTAMP
    WHERE incident_type = %s
      AND status = 'OPEN'
"""


SELECT_LAST_RESOLVED_INCIDENTS_QUERY = """
    SELECT
        incident_type,
        MAX(resolved_at) AS last_resolved_at
    FROM incidents
    WHERE status = 'RESOLVED'
      AND incident_type IN (%s, %s, %s)
    GROUP BY incident_type
"""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def save_metrics(data: Metrics) -> None:
    """
    Save the incoming monitoring metric and process alert/incident state.
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            metric_id = insert_metric(cursor, data)

            process_alerts(
                cursor=cursor,
                data=data,
                metric_id=metric_id,
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Metric persistence
# ---------------------------------------------------------------------------

def insert_metric(cursor: Any, data: Metrics) -> int:
    """
    Insert a monitoring sample into the metrics table.
    """

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


# ---------------------------------------------------------------------------
# Current database state
# ---------------------------------------------------------------------------

def get_open_alert_types(cursor: Any) -> set[str]:
    """
    Return currently OPEN alert types.
    """

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
    """
    Return currently OPEN incident types.
    """

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


def get_last_resolved_incident_times(
    cursor: Any,
) -> dict[str, datetime]:
    """
    Return the most recent resolution time for each incident type.

    This makes the cooldown survive a backend restart because the
    information comes from MySQL rather than only from memory.
    """

    incident_types = tuple(
        rule["alert_type"]
        for rule in ALERT_RULES.values()
    )

    cursor.execute(
        SELECT_LAST_RESOLVED_INCIDENTS_QUERY,
        incident_types,
    )

    return {
        row[0]: row[1]
        for row in cursor.fetchall()
        if row[1] is not None
    }


# ---------------------------------------------------------------------------
# Cooldown handling
# ---------------------------------------------------------------------------

def is_in_resolution_cooldown(
    alert_type: str,
    last_resolved_times: dict[str, datetime],
) -> bool:
    """
    Check whether a resource is still inside its post-resolution cooldown.
    """

    last_resolved_at = last_resolved_times.get(alert_type)

    if last_resolved_at is None:
        return False

    elapsed_seconds = (
        datetime.now() - last_resolved_at
    ).total_seconds()

    return elapsed_seconds < RESOLUTION_COOLDOWN_SECONDS


# ---------------------------------------------------------------------------
# Consecutive-sample tracking
# ---------------------------------------------------------------------------

def register_abnormal_sample(alert_type: str) -> int:
    """
    Register one abnormal sample and reset the normal streak.
    """

    state = STREAK_STATE[alert_type]

    state["abnormal"] += 1
    state["normal"] = 0

    return state["abnormal"]


def register_normal_sample(alert_type: str) -> int:
    """
    Register one normal sample and reset the abnormal streak.
    """

    state = STREAK_STATE[alert_type]

    state["normal"] += 1
    state["abnormal"] = 0

    return state["normal"]


def reset_streak(alert_type: str) -> None:
    """
    Reset both streak counters.
    """

    STREAK_STATE[alert_type]["abnormal"] = 0
    STREAK_STATE[alert_type]["normal"] = 0


# ---------------------------------------------------------------------------
# Main alert / incident state machine
# ---------------------------------------------------------------------------

def process_alerts(
    cursor: Any,
    data: Metrics,
    metric_id: int,
) -> None:
    """
    Process CPU, RAM and DISK using a stateful anti-flapping lifecycle.

    Lifecycle:

        NORMAL
           |
           | 3 consecutive abnormal samples
           v
        OPEN
           |
           | 3 consecutive normal samples
           v
        RESOLVED
           |
           | cooldown
           v
        NORMAL
    """

    open_alert_types = get_open_alert_types(cursor)
    open_incident_types = get_open_incident_types(cursor)
    last_resolved_times = get_last_resolved_incident_times(cursor)

    alerts_to_create = []
    alerts_to_resolve = []
    incidents_to_create = []
    incidents_to_resolve = []

    for metric_name, rule in ALERT_RULES.items():
        metric_value = getattr(data, metric_name)
        alert_type = rule["alert_type"]

        has_open_alert = alert_type in open_alert_types
        has_open_incident = alert_type in open_incident_types

        # ---------------------------------------------------------------
        # Abnormal metric
        # ---------------------------------------------------------------

        if metric_value > rule["threshold"]:

            # When an incident is already open, there is no reason to
            # continue accumulating an opening streak.
            if has_open_incident:
                STREAK_STATE[alert_type]["abnormal"] = (
                    ABNORMAL_SAMPLES_REQUIRED
                )
                STREAK_STATE[alert_type]["normal"] = 0
                continue

            # During cooldown, do not accumulate abnormal samples.
            # This forces a fresh 3-sample abnormal streak after cooldown.
            if is_in_resolution_cooldown(
                alert_type,
                last_resolved_times,
            ):
                reset_streak(alert_type)
                continue

            abnormal_count = register_abnormal_sample(
                alert_type
            )

            # Do nothing until 3 consecutive abnormal samples occur.
            if abnormal_count < ABNORMAL_SAMPLES_REQUIRED:
                continue

            # -----------------------------------------------------------
            # Open alert
            # -----------------------------------------------------------

            if not has_open_alert:
                alerts_to_create.append(
                    (
                        metric_id,
                        alert_type,
                        rule["message"],
                        rule["severity"],
                    )
                )

            # -----------------------------------------------------------
            # Open incident
            # -----------------------------------------------------------

            if not has_open_incident:
                incidents_to_create.append(
                    (
                        metric_id,
                        alert_type,
                        rule["severity"],
                        rule["message"],
                    )
                )

        # ---------------------------------------------------------------
        # Normal metric
        # ---------------------------------------------------------------

        else:
            normal_count = register_normal_sample(
                alert_type
            )

            # Do not resolve immediately after one normal sample.
            if normal_count < NORMAL_SAMPLES_REQUIRED:
                continue

            # -----------------------------------------------------------
            # Resolve alert
            # -----------------------------------------------------------

            if has_open_alert:
                alerts_to_resolve.append(
                    (alert_type,)
                )

            # -----------------------------------------------------------
            # Resolve incident
            # -----------------------------------------------------------

            if has_open_incident:
                incidents_to_resolve.append(
                    (alert_type,)
                )

            # Once the resource is resolved, start from a clean state.
            if has_open_alert or has_open_incident:
                reset_streak(alert_type)

    # -------------------------------------------------------------------
    # Database writes
    # -------------------------------------------------------------------

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

    if incidents_to_resolve:
        cursor.executemany(
            RESOLVE_INCIDENT_QUERY,
            incidents_to_resolve,
        )

