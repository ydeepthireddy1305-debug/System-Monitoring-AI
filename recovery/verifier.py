import time
from datetime import datetime
from typing import Any

from backend.database import get_connection
from backend.services.monitoring_service import ALERT_RULES


RECOVERY_SAMPLE_COUNT = 3
SAMPLE_INTERVAL = 5
VERIFICATION_TIMEOUT = 60

STATUS_RECOVERED = "RECOVERED"
STATUS_NOT_RECOVERED = "NOT_RECOVERED"
STATUS_TIMEOUT = "TIMEOUT"


INCIDENT_ACTION_QUERY = """
    SELECT
        ra.id AS action_id,
        ra.incident_id,
        ra.status AS action_status,
        ra.completed_at,
        i.incident_type
    FROM remediation_actions ra
    INNER JOIN incidents i
        ON i.id = ra.incident_id
    WHERE ra.id = %s
"""


INSERT_RECOVERY_QUERY = """
    INSERT INTO recovery_verifications
        (
            incident_id,
            remediation_action_id,
            status,
            samples_checked,
            details
        )
    VALUES
        (%s, %s, %s, %s, %s)
"""


METRIC_QUERY_TEMPLATE = """
    SELECT
        id,
        {metric_name},
        recorded_at
    FROM metrics
    WHERE recorded_at > %s
    ORDER BY recorded_at ASC
"""


def get_action_context(
    action_id: int,
) -> dict[str, Any] | None:
    connection = get_connection()

    try:
        with connection.cursor(
            dictionary=True
        ) as cursor:
            cursor.execute(
                INCIDENT_ACTION_QUERY,
                (action_id,),
            )
            return cursor.fetchone()

    finally:
        connection.close()


def get_new_metric_samples(
    metric_name: str,
    completed_at: datetime,
) -> list[dict[str, Any]]:
    connection = get_connection()

    query = METRIC_QUERY_TEMPLATE.format(
        metric_name=metric_name
    )

    try:
        with connection.cursor(
            dictionary=True
        ) as cursor:
            cursor.execute(
                query,
                (completed_at,),
            )

            return cursor.fetchall()

    finally:
        connection.close()


def is_metric_recovered(
    metric_name: str,
    value: float,
) -> bool:
    rule = ALERT_RULES.get(metric_name)

    if rule is None:
        raise ValueError(
            f"No recovery rule exists for {metric_name}."
        )

    return value <= rule["threshold"]


def save_verification(
    incident_id: int,
    action_id: int,
    status: str,
    samples_checked: int,
    details: str,
) -> None:
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                INSERT_RECOVERY_QUERY,
                (
                    incident_id,
                    action_id,
                    status,
                    samples_checked,
                    details,
                ),
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def verify_recovery(
    action_id: int,
) -> dict[str, Any]:
    action = get_action_context(action_id)

    if action is None:
        raise ValueError(
            f"Remediation action {action_id} was not found."
        )

    if action["action_status"] != "SUCCESS":
        result = {
            "incident_id": action["incident_id"],
            "action_id": action_id,
            "status": STATUS_NOT_RECOVERED,
            "samples_checked": 0,
            "details": (
                "Recovery verification was skipped because "
                "the remediation action did not succeed."
            ),
        }

        save_verification(**result)

        return result

    completed_at = action["completed_at"]

    if completed_at is None:
        raise ValueError(
            "Successful remediation has no completion timestamp."
        )

    incident_type = str(
        action["incident_type"]
    ).upper()

    metric_name = incident_type.lower()

    if metric_name not in ALERT_RULES:
        result = {
            "incident_id": action["incident_id"],
            "action_id": action_id,
            "status": STATUS_NOT_RECOVERED,
            "samples_checked": 0,
            "details": (
                f"No recovery metric is configured for "
                f"incident type '{incident_type}'."
            ),
        }

        save_verification(**result)

        return result

    deadline = (
        time.monotonic()
        + VERIFICATION_TIMEOUT
    )

    while time.monotonic() < deadline:
        samples = get_new_metric_samples(
            metric_name,
            completed_at,
        )

        recent_samples = samples[
            -RECOVERY_SAMPLE_COUNT:
        ]

        if len(recent_samples) >= RECOVERY_SAMPLE_COUNT:
            recovered = all(
                is_metric_recovered(
                    metric_name,
                    float(sample[metric_name]),
                )
                for sample in recent_samples
            )

            if recovered:
                result = {
                    "incident_id": action["incident_id"],
                    "action_id": action_id,
                    "status": STATUS_RECOVERED,
                    "samples_checked": len(
                        recent_samples
                    ),
                    "details": (
                        f"{metric_name.upper()} remained at or "
                        f"below its recovery threshold for "
                        f"{len(recent_samples)} consecutive samples."
                    ),
                }

                save_verification(**result)

                return result

            result = {
                "incident_id": action["incident_id"],
                "action_id": action_id,
                "status": STATUS_NOT_RECOVERED,
                "samples_checked": len(
                    recent_samples
                ),
                "details": (
                    f"{metric_name.upper()} is still above "
                    f"its configured recovery threshold."
                ),
            }

            save_verification(**result)

            return result

        time.sleep(SAMPLE_INTERVAL)

    result = {
        "incident_id": action["incident_id"],
        "action_id": action_id,
        "status": STATUS_TIMEOUT,
        "samples_checked": len(samples),
        "details": (
            "Not enough fresh metric samples were available "
            "before the recovery verification timeout."
        ),
    }

    save_verification(**result)

    return result


def main() -> None:
    import sys

    if len(sys.argv) != 2:
        print(
            "Usage: python -m recovery.verifier <action_id>"
        )
        return

    action_id = int(sys.argv[1])

    result = verify_recovery(
        action_id
    )

    print("\n" + "=" * 70)
    print("RECOVERY VERIFICATION")
    print("=" * 70)
    print(
        f"Incident ID      : {result['incident_id']}"
    )
    print(
        f"Action ID        : {result['action_id']}"
    )
    print(
        f"Status           : {result['status']}"
    )
    print(
        f"Samples checked  : {result['samples_checked']}"
    )
    print(
        f"Details          : {result['details']}"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()