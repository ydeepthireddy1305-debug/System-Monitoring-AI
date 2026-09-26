import os
import platform
import subprocess
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

from agent.decision_engine import (
    evaluate_incident,
)
from backend.database import get_connection


load_dotenv()


ACTION_NO_ACTION = "NO_ACTION"
ACTION_COLLECT_DIAGNOSTICS = "COLLECT_DIAGNOSTICS"
ACTION_RESTART_SERVICE = "RESTART_CONFIGURED_SERVICE"

STATUS_RUNNING = "RUNNING"
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"
STATUS_BLOCKED = "BLOCKED"


INSERT_ACTION_QUERY = """
    INSERT INTO remediation_actions
        (
            incident_id,
            action,
            status,
            details
        )
    VALUES
        (%s, %s, %s, %s)
"""


UPDATE_ACTION_QUERY = """
    UPDATE remediation_actions
    SET
        status = %s,
        details = %s,
        completed_at = CURRENT_TIMESTAMP
    WHERE id = %s
"""


def insert_action_record(
    incident_id: int,
    action: str,
    status: str,
    details: str,
) -> int:
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                INSERT_ACTION_QUERY,
                (
                    incident_id,
                    action,
                    status,
                    details,
                ),
            )

            action_id = cursor.lastrowid

        connection.commit()

        return int(action_id)

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def update_action_record(
    action_id: int,
    status: str,
    details: str,
) -> None:
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                UPDATE_ACTION_QUERY,
                (
                    status,
                    details,
                    action_id,
                ),
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def collect_diagnostics() -> str:
    return (
        f"Diagnostic collection requested at "
        f"{datetime.now().isoformat()}. "
        f"Operating system: {platform.system()} "
        f"{platform.release()}. "
        f"Machine: {platform.machine()}."
    )


def restart_configured_service() -> str:
    if platform.system() != "Windows":
        raise RuntimeError(
            "Configured service restart is currently "
            "supported only on Windows."
        )

    service_name = os.getenv(
        "REMEDIATION_SERVICE_NAME"
    )

    if not service_name:
        raise RuntimeError(
            "REMEDIATION_SERVICE_NAME is not configured."
        )

    service_name = service_name.strip()

    if not service_name:
        raise RuntimeError(
            "REMEDIATION_SERVICE_NAME is empty."
        )

    allowed_services = {
        name.strip()
        for name in os.getenv(
            "ALLOWED_REMEDIATION_SERVICES",
            "",
        ).split(",")
        if name.strip()
    }

    if service_name not in allowed_services:
        raise RuntimeError(
            "Configured service is not present in "
            "ALLOWED_REMEDIATION_SERVICES."
        )

    subprocess.run(
        [
            "sc.exe",
            "stop",
            service_name,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    subprocess.run(
        [
            "sc.exe",
            "start",
            service_name,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    return (
        f"Service '{service_name}' was restarted successfully."
    )


def execute_action(
    incident_id: int,
    action: str,
    allowed: bool,
) -> dict[str, Any]:
    if not allowed:
        action_id = insert_action_record(
            incident_id=incident_id,
            action=action,
            status=STATUS_BLOCKED,
            details=(
                "Action was blocked by the agent "
                "safety decision."
            ),
        )

        return {
            "action_id": action_id,
            "status": STATUS_BLOCKED,
            "details": (
                "Action was blocked by the agent "
                "safety decision."
            ),
        }

    if action not in {
        ACTION_NO_ACTION,
        ACTION_COLLECT_DIAGNOSTICS,
        ACTION_RESTART_SERVICE,
    }:
        raise ValueError(
            f"Unsupported remediation action: {action}"
        )

    action_id = insert_action_record(
        incident_id=incident_id,
        action=action,
        status=STATUS_RUNNING,
        details="Remediation action started.",
    )

    try:
        if action == ACTION_NO_ACTION:
            details = (
                "No remediation action was required."
            )

        elif action == ACTION_COLLECT_DIAGNOSTICS:
            details = collect_diagnostics()

        else:
            remediation_enabled = os.getenv(
                "REMEDIATION_ENABLED",
                "false",
            ).lower() == "true"

            if not remediation_enabled:
                raise RuntimeError(
                    "Automatic remediation is disabled."
                )

            details = restart_configured_service()

        update_action_record(
            action_id=action_id,
            status=STATUS_SUCCESS,
            details=details,
        )

        return {
            "action_id": action_id,
            "status": STATUS_SUCCESS,
            "details": details,
        }

    except Exception as exc:
        details = (
            f"Remediation failed: {exc}"
        )

        update_action_record(
            action_id=action_id,
            status=STATUS_FAILED,
            details=details,
        )

        return {
            "action_id": action_id,
            "status": STATUS_FAILED,
            "details": details,
        }


def remediate_incident(
    incident_id: int,
) -> dict[str, Any]:
    decision = evaluate_incident(
        incident_id
    )

    result = execute_action(
        incident_id=incident_id,
        action=decision["action"],
        allowed=(
            decision["decision"] == "ALLOWED"
        ),
    )

    return {
        "incident_id": incident_id,
        "action": decision["action"],
        "decision": decision["decision"],
        "risk_score": decision["risk_score"],
        "risk_level": decision["risk_level"],
        "status": result["status"],
        "details": result["details"],
        "action_id": result["action_id"],
    }


def main() -> None:
    import sys

    if len(sys.argv) != 2:
        print(
            "Usage: python -m remediation.runner <incident_id>"
        )
        return

    incident_id = int(sys.argv[1])

    result = remediate_incident(
        incident_id
    )

    print("\n" + "=" * 70)
    print("REMEDIATION RESULT")
    print("=" * 70)
    print(
        f"Incident ID : {result['incident_id']}"
    )
    print(
        f"Action      : {result['action']}"
    )
    print(
        f"Decision    : {result['decision']}"
    )
    print(
        f"Risk score  : {result['risk_score']:.3f}"
    )
    print(
        f"Risk level  : {result['risk_level']}"
    )
    print(
        f"Status      : {result['status']}"
    )
    print(
        f"Details     : {result['details']}"
    )
    print(
        f"Action ID   : {result['action_id']}"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()