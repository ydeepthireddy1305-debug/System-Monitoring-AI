import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil
from dotenv import load_dotenv

from agent.decision_engine import evaluate_incident
from backend.database import get_connection


load_dotenv()


ACTION_NO_ACTION = "NO_ACTION"
ACTION_COLLECT_DIAGNOSTICS = "COLLECT_DIAGNOSTICS"
ACTION_RESTART_SERVICE = "RESTART_CONFIGURED_SERVICE"

ACTION_STOP_CPU_TEST = "STOP_CPU_TEST"
ACTION_STOP_RAM_TEST = "STOP_RAM_TEST"
ACTION_STOP_DISK_TEST = "STOP_DISK_TEST"


STATUS_RUNNING = "RUNNING"
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"
STATUS_BLOCKED = "BLOCKED"


PROJECT_ROOT = Path(__file__).resolve().parents[1]


TEST_PID_FILES = {
    ACTION_STOP_CPU_TEST:
        PROJECT_ROOT / ".remediation_cpu.pid",

    ACTION_STOP_RAM_TEST:
        PROJECT_ROOT / ".remediation_ram.pid",

    ACTION_STOP_DISK_TEST:
        PROJECT_ROOT / ".remediation_disk.pid",
}


TEST_ACTION_MODES = {
    ACTION_STOP_CPU_TEST: "cpu",
    ACTION_STOP_RAM_TEST: "ram",
    ACTION_STOP_DISK_TEST: "disk",
}


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
            "Service restart is currently supported "
            "only on Windows."
        )

    service_name = os.getenv(
        "REMEDIATION_SERVICE_NAME"
    )

    if not service_name:
        raise RuntimeError(
            "REMEDIATION_SERVICE_NAME is not configured."
        )

    service_name = service_name.strip()

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
        f"Service '{service_name}' "
        "was restarted successfully."
    )


def read_test_workload_info(
    action: str,
) -> tuple[int, str]:
    pid_file = TEST_PID_FILES.get(
        action
    )

    expected_mode = TEST_ACTION_MODES.get(
        action
    )

    if pid_file is None or expected_mode is None:
        raise ValueError(
            f"Unsupported test remediation action: "
            f"{action}"
        )

    if not pid_file.exists():
        raise RuntimeError(
            f"No controlled {expected_mode.upper()} "
            "workload is running."
        )

    content = pid_file.read_text(
        encoding="utf-8"
    ).strip()

    try:
        pid = int(content)
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid PID file for "
            f"{expected_mode.upper()} workload."
        ) from exc

    return pid, expected_mode


def stop_controlled_test_workload(
    action: str,
) -> str:
    test_mode_enabled = (
        os.getenv(
            "REMEDIATION_TEST_MODE",
            "false",
        ).strip().lower()
        == "true"
    )

    if not test_mode_enabled:
        raise RuntimeError(
            "Test remediation mode is disabled."
        )

    pid, expected_mode = (
        read_test_workload_info(action)
    )

    try:
        process = psutil.Process(pid)

    except psutil.NoSuchProcess as exc:
        TEST_PID_FILES[action].unlink(
            missing_ok=True
        )

        raise RuntimeError(
            f"Controlled {expected_mode.upper()} "
            "workload process no longer exists."
        ) from exc

    try:
        command_line = " ".join(
            process.cmdline()
        ).lower()

    except (
        psutil.AccessDenied,
        psutil.NoSuchProcess,
    ) as exc:
        raise RuntimeError(
            "Unable to verify the controlled "
            "test workload."
        ) from exc

    if "remediation.test_workload" not in command_line:
        raise RuntimeError(
            "Safety check failed: target process does "
            "not belong to remediation.test_workload."
        )

    mode_argument = (
        f"--mode {expected_mode}"
    )

    if mode_argument not in command_line:
        raise RuntimeError(
            "Safety check failed: target process does "
            f"not match the {expected_mode.upper()} workload."
        )

    children = process.children(
        recursive=True
    )

    for child in children:
        try:
            child.terminate()
        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
        ):
            pass

    _, alive_children = psutil.wait_procs(
        children,
        timeout=5,
    )

    for child in alive_children:
        try:
            child.kill()
        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
        ):
            pass

    try:
        process.terminate()
        process.wait(timeout=10)

    except psutil.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)

    except psutil.NoSuchProcess:
        pass

    TEST_PID_FILES[action].unlink(
        missing_ok=True
    )

    return (
        f"Controlled {expected_mode.upper()} "
        f"test workload (PID {pid}) "
        "was stopped successfully."
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

    supported_actions = {
        ACTION_NO_ACTION,
        ACTION_COLLECT_DIAGNOSTICS,
        ACTION_RESTART_SERVICE,
        ACTION_STOP_CPU_TEST,
        ACTION_STOP_RAM_TEST,
        ACTION_STOP_DISK_TEST,
    }

    if action not in supported_actions:
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

        elif action == ACTION_RESTART_SERVICE:
            remediation_enabled = (
                os.getenv(
                    "REMEDIATION_ENABLED",
                    "false",
                ).strip().lower()
                == "true"
            )

            if not remediation_enabled:
                raise RuntimeError(
                    "Automatic service remediation "
                    "is disabled."
                )

            details = (
                restart_configured_service()
            )

        else:
            details = (
                stop_controlled_test_workload(
                    action
                )
            )

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
            decision["decision"]
            == "ALLOWED"
        ),
    )

    return {
        "incident_id": incident_id,
        "incident_type": decision[
            "incident_type"
        ],
        "action": decision["action"],
        "decision": decision["decision"],
        "risk_score": decision["risk_score"],
        "risk_level": decision["risk_level"],
        "status": result["status"],
        "details": result["details"],
        "action_id": result["action_id"],
    }


def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Usage: "
            "python -m remediation.runner <incident_id>"
        )
        return

    try:
        incident_id = int(
            sys.argv[1]
        )
    except ValueError:
        print(
            "Incident ID must be an integer."
        )
        return

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
        f"Incident    : {result['incident_type']}"
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