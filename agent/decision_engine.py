import psutil

from pathlib import Path
from typing import Any


# =========================================================
# Actions
# =========================================================

ACTION_NO_ACTION = "NO_ACTION"
ACTION_STOP_RAM_TEST = "STOP_RAM_TEST"


# =========================================================
# Project paths
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAM_PID_FILE = (
    PROJECT_ROOT / ".remediation_ram.pid"
)


# =========================================================
# Helpers
# =========================================================

def _get_value(
    source: Any,
    key: str,
    default: Any = None,
) -> Any:

    if source is None:
        return default

    if isinstance(source, dict):
        return source.get(
            key,
            default,
        )

    return getattr(
        source,
        key,
        default,
    )


def _text(value: Any) -> str:

    if value is None:
        return ""

    return str(value).strip().lower()


def is_controlled_ram_workload_running() -> bool:
    """
    Verify that the controlled RAM test workload is really running.

    Safety requirements:

    1. PID file exists.
    2. PID is valid.
    3. Process exists.
    4. Process belongs to remediation.test_workload.
    5. Process was started with --mode ram.
    """

    if not RAM_PID_FILE.exists():
        return False

    try:

        pid = int(
            RAM_PID_FILE.read_text(
                encoding="utf-8"
            ).strip()
        )

    except (
        ValueError,
        OSError,
    ):

        return False

    try:

        process = psutil.Process(pid)

    except (
        psutil.NoSuchProcess,
        psutil.AccessDenied,
    ):

        return False

    try:

        command_line = " ".join(
            process.cmdline()
        ).lower()

    except (
        psutil.NoSuchProcess,
        psutil.AccessDenied,
    ):

        return False

    if "remediation.test_workload" not in command_line:
        return False

    if "--mode ram" not in command_line:
        return False

    return True


def _is_ram_incident(
    incident: Any,
) -> bool:

    incident_type = _text(
        _get_value(
            incident,
            "incident_type",
        )
    )

    description = _text(
        _get_value(
            incident,
            "description",
        )
    )

    combined = (
        f"{incident_type} {description}"
    )

    return any(
        keyword in combined
        for keyword in (
            "ram",
            "memory",
            "out of memory",
            "oom",
        )
    )


# =========================================================
# Main decision engine
# =========================================================

def evaluate_incident(
    incident: Any,
    analysis: Any = None,
) -> dict[str, Any]:
    """
    Make a safe remediation decision.

    The agent only authorizes STOP_RAM_TEST when
    a real controlled RAM workload is confirmed.
    """

    status = _text(
        _get_value(
            incident,
            "status",
        )
    )

    # -----------------------------------------------------
    # Already resolved
    # -----------------------------------------------------

    if status == "resolved":

        return {
            "decision": "BLOCKED",
            "action": ACTION_NO_ACTION,
            "reason": (
                "Incident is already resolved; "
                "automated remediation is not required."
            ),
        }

    # -----------------------------------------------------
    # RAM incident
    # -----------------------------------------------------

    if _is_ram_incident(incident):

        workload_running = (
            is_controlled_ram_workload_running()
        )

        if not workload_running:

            return {
                "decision": "BLOCKED",
                "action": ACTION_NO_ACTION,
                "reason": (
                    "RAM incident detected, but no controlled "
                    "RAM test workload is confirmed as running. "
                    "STOP_RAM_TEST is therefore blocked to "
                    "prevent unsafe process termination."
                ),
            }

        return {
            "decision": "ALLOWED",
            "action": ACTION_STOP_RAM_TEST,
            "reason": (
                "RAM incident detected and the controlled "
                "RAM test workload was verified using its "
                "PID file and process command line."
            ),
        }

    # -----------------------------------------------------
    # Conservative default
    # -----------------------------------------------------

    return {
        "decision": "BLOCKED",
        "action": ACTION_NO_ACTION,
        "reason": (
            "No approved controlled remediation action "
            "matched this incident. Manual review is required."
        ),
    }


# =========================================================
# Local tests
# =========================================================

if __name__ == "__main__":

    print(
        "\n=== Agent Decision Engine Test ===\n"
    )

    incident = {
        "incident_type": "RAM",
        "severity": "WARNING",
        "status": "OPEN",
        "description": "High RAM usage detected",
        "risk_score": 0.82,
        "risk_level": "HIGH",
    }

    result = evaluate_incident(
        incident
    )

    print(
        f"Controlled RAM workload running: "
        f"{is_controlled_ram_workload_running()}"
    )

    print(
        f"Decision: {result['decision']}"
    )

    print(
        f"Action: {result['action']}"
    )

    print(
        f"Reason: {result['reason']}"
    )