import argparse
import time

from agent.decision_engine import evaluate_incident
from audit.logger import log_event
from backend.database import get_connection
from genai.incident_analyzer import analyze_incident
from remediation.runner import execute_action
from recovery.verifier import verify_recovery


# =========================================================
# Pipeline configuration
# =========================================================

PIPELINE_INTERVAL = 10
MAX_INCIDENTS_PER_CYCLE = 10
MAX_ATTEMPTS = 3
STALE_RUN_MINUTES = 5


RECOVERY_ACTIONS = {
    "RESTART_CONFIGURED_SERVICE",
    "STOP_CPU_TEST",
    "STOP_RAM_TEST",
    "STOP_DISK_TEST",
}


RUNNING_STATUSES = (
    "AI_RUNNING",
    "AGENT_RUNNING",
    "REMEDIATION_RUNNING",
    "RECOVERY_RUNNING",
)


# =========================================================
# Audit logging
# =========================================================

def audit_event(
    incident_id: int | None,
    event_type: str,
    action: str | None = None,
    status: str | None = None,
    message: str | None = None,
) -> None:
    """
    Write an audit event.

    Audit failures must never stop the main pipeline.
    """

    try:
        log_event(
            incident_id=incident_id,
            event_type=event_type,
            actor="SYSTEM",
            action=action,
            status=status,
            message=message,
        )

    except Exception as exc:
        print(
            f"Audit logging failed for incident "
            f"{incident_id}: {exc}"
        )


# =========================================================
# Incident data
# =========================================================

def get_incident_context(
    incident_id: int,
) -> dict | None:
    """
    Load the incident information required by the agent.
    """

    connection = get_connection()

    try:
        with connection.cursor(dictionary=True) as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    metric_id,
                    incident_type,
                    severity,
                    description,
                    started_at,
                    resolved_at,
                    status,
                    risk_score,
                    risk_level
                FROM incidents
                WHERE id = %s
                """,
                (incident_id,),
            )

            row = cursor.fetchone()

            if not row:
                return None

            return dict(row)

    finally:
        connection.close()


# =========================================================
# Stale pipeline recovery
# =========================================================

def reset_stale_runs() -> None:
    """
    Reset pipeline runs that were left in a running state
    because the process stopped unexpectedly.

    Runs with attempts remaining are returned to PENDING.
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                UPDATE incident_pipeline_runs
                SET
                    status = 'PENDING',
                    error_message = %s
                WHERE status IN (
                    'AI_RUNNING',
                    'AGENT_RUNNING',
                    'REMEDIATION_RUNNING',
                    'RECOVERY_RUNNING'
                )
                AND updated_at <
                    NOW() - INTERVAL %s MINUTE
                AND attempt_count < %s
                """,
                (
                    "Previous pipeline execution became stale.",
                    STALE_RUN_MINUTES,
                    MAX_ATTEMPTS,
                ),
            )

        connection.commit()

    finally:
        connection.close()


# =========================================================
# Pipeline record
# =========================================================

def create_pipeline_record(
    incident_id: int,
) -> None:
    """
    Create a pipeline tracking row when one does not exist.
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                INSERT IGNORE INTO incident_pipeline_runs (
                    incident_id,
                    status
                )
                VALUES (
                    %s,
                    'PENDING'
                )
                """,
                (incident_id,),
            )

        connection.commit()

    finally:
        connection.close()


# =========================================================
# Candidate incidents
# =========================================================

def get_candidate_incident_ids() -> list[int]:
    """
    Find incidents that still require pipeline processing.

    New incidents are eligible.

    Failed pipeline runs are retried until MAX_ATTEMPTS.

    Incidents already containing AI analysis are excluded
    from starting the pipeline again.
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    i.id
                FROM incidents i

                LEFT JOIN incident_analysis ia
                    ON ia.incident_id = i.id

                LEFT JOIN incident_pipeline_runs pr
                    ON pr.incident_id = i.id

                WHERE ia.id IS NULL

                  AND i.started_at >=
                      NOW() - INTERVAL 30 MINUTE

                  AND (
                        pr.id IS NULL

                        OR (
                            pr.status = 'PENDING'
                            AND pr.attempt_count < %s
                        )

                        OR (
                            pr.status = 'FAILED'
                            AND pr.attempt_count < %s
                        )
                  )

                ORDER BY
                    i.started_at ASC,
                    i.id ASC

                LIMIT %s
                """,
                (
                    MAX_ATTEMPTS,
                    MAX_ATTEMPTS,
                    MAX_INCIDENTS_PER_CYCLE,
                ),
            )

            rows = cursor.fetchall()

        return [
            int(row[0])
            for row in rows
        ]

    finally:
        connection.close()


# =========================================================
# Claim incident
# =========================================================

def claim_incident(
    incident_id: int,
) -> bool:
    """
    Atomically claim an incident.

    This prevents multiple pipeline processes from
    processing the same incident simultaneously.
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                INSERT IGNORE INTO incident_pipeline_runs (
                    incident_id,
                    status
                )
                VALUES (
                    %s,
                    'PENDING'
                )
                """,
                (incident_id,),
            )

            cursor.execute(
                """
                UPDATE incident_pipeline_runs
                SET
                    status = 'AI_RUNNING',
                    attempt_count = attempt_count + 1,
                    started_at = NOW(),
                    completed_at = NULL,
                    error_message = NULL
                WHERE incident_id = %s
                  AND status IN (
                      'PENDING',
                      'FAILED'
                  )
                  AND attempt_count < %s
                """,
                (
                    incident_id,
                    MAX_ATTEMPTS,
                ),
            )

            claimed = (
                cursor.rowcount == 1
            )

        connection.commit()

        return claimed

    finally:
        connection.close()


# =========================================================
# Pipeline status
# =========================================================

def update_pipeline_status(
    incident_id: int,
    status: str,
    error_message: str | None = None,
) -> None:
    """
    Update the pipeline lifecycle state.
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            terminal_statuses = {
                "COMPLETED",
                "FAILED",
                "MANUAL_REVIEW",
            }

            if status in terminal_statuses:

                cursor.execute(
                    """
                    UPDATE incident_pipeline_runs
                    SET
                        status = %s,
                        completed_at = NOW(),
                        error_message = %s
                    WHERE incident_id = %s
                    """,
                    (
                        status,
                        error_message,
                        incident_id,
                    ),
                )

            else:

                cursor.execute(
                    """
                    UPDATE incident_pipeline_runs
                    SET
                        status = %s,
                        error_message = %s
                    WHERE incident_id = %s
                    """,
                    (
                        status,
                        error_message,
                        incident_id,
                    ),
                )

        connection.commit()

    finally:
        connection.close()


# =========================================================
# Manual review
# =========================================================

def mark_manual_review_if_needed(
    incident_id: int,
) -> None:
    """
    Stop automatic retries after MAX_ATTEMPTS failures.
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    attempt_count
                FROM incident_pipeline_runs
                WHERE incident_id = %s
                """,
                (incident_id,),
            )

            row = cursor.fetchone()

            if row and int(row[0]) >= MAX_ATTEMPTS:

                cursor.execute(
                    """
                    UPDATE incident_pipeline_runs
                    SET
                        status = 'MANUAL_REVIEW',
                        completed_at = NOW(),
                        error_message = %s
                    WHERE incident_id = %s
                    """,
                    (
                        "Maximum pipeline attempts reached.",
                        incident_id,
                    ),
                )

                audit_event(
                    incident_id=incident_id,
                    event_type="PIPELINE_MANUAL_REVIEW",
                    action="STOP_RETRY",
                    status="MANUAL_REVIEW",
                    message=(
                        "Maximum pipeline attempts reached."
                    ),
                )

        connection.commit()

    finally:
        connection.close()


# =========================================================
# Main incident processing
# =========================================================

def process_incident(
    incident_id: int,
) -> None:

    print(
        "\n========================================"
    )

    print(
        f"Processing incident {incident_id}"
    )

    print(
        "========================================"
    )

    audit_event(
        incident_id=incident_id,
        event_type="PIPELINE_STARTED",
        action="START_PIPELINE",
        status="STARTED",
        message=(
            f"Incident {incident_id} entered "
            "automatic processing."
        ),
    )

    # -----------------------------------------------------
    # Validate incident exists
    # -----------------------------------------------------

    incident = get_incident_context(
        incident_id
    )

    if incident is None:

        message = (
            f"Incident {incident_id} was not found."
        )

        update_pipeline_status(
            incident_id,
            "FAILED",
            message,
        )

        audit_event(
            incident_id=incident_id,
            event_type="PIPELINE_FAILED",
            action="LOAD_INCIDENT",
            status="FAILED",
            message=message,
        )

        return

    # -----------------------------------------------------
    # Claim incident
    # -----------------------------------------------------

    create_pipeline_record(
        incident_id
    )

    if not claim_incident(
        incident_id
    ):

        print(
            f"Incident {incident_id} is already "
            "being processed."
        )

        audit_event(
            incident_id=incident_id,
            event_type="PIPELINE_SKIPPED",
            action="CLAIM_INCIDENT",
            status="SKIPPED",
            message=(
                "Incident could not be claimed "
                "because another pipeline execution "
                "already owns it."
            ),
        )

        return

    try:

        # =================================================
        # 1. GenAI analysis
        # =================================================

        update_pipeline_status(
            incident_id,
            "AI_RUNNING",
        )

        audit_event(
            incident_id=incident_id,
            event_type="AI_ANALYSIS_STARTED",
            action="GENERATE_ANALYSIS",
            status="STARTED",
            message=(
                "Incident analysis generation started."
            ),
        )

        print(
            "[1/4] Running GenAI analysis..."
        )

        analyze_incident(
            incident_id
        )

        update_pipeline_status(
            incident_id,
            "AI_COMPLETED",
        )

        audit_event(
            incident_id=incident_id,
            event_type="AI_ANALYSIS_COMPLETED",
            action="SAVE_ANALYSIS",
            status="COMPLETED",
            message=(
                "Incident analysis generated and saved."
            ),
        )

        print(
            "GenAI analysis completed."
        )

        # =================================================
        # 2. Agent safety decision
        # =================================================

        update_pipeline_status(
            incident_id,
            "AGENT_RUNNING",
        )

        audit_event(
            incident_id=incident_id,
            event_type="AGENT_DECISION_STARTED",
            action="EVALUATE_INCIDENT",
            status="STARTED",
            message=(
                "Agent safety decision evaluation started."
            ),
        )

        print(
            "[2/4] Running agent decision..."
        )

        # IMPORTANT:
        # The new decision engine expects incident data,
        # not just the numeric incident ID.
        decision = evaluate_incident(
            incident
        )

        decision_status = decision.get(
            "decision",
            "BLOCKED",
        )

        action = decision.get(
            "action",
            "NO_ACTION",
        )

        reason = decision.get(
            "reason",
            "No decision reason supplied.",
        )

        print(
            f"Agent decision: "
            f"{decision_status} | "
            f"Action: {action}"
        )

        print(
            f"Agent reason: {reason}"
        )

        update_pipeline_status(
            incident_id,
            "AGENT_COMPLETED",
        )

        audit_event(
            incident_id=incident_id,
            event_type="AGENT_DECISION_COMPLETED",
            action=action,
            status=decision_status,
            message=reason,
        )

        # =================================================
        # 3. Safety gate before remediation
        # =================================================

        # BLOCKED decisions must never execute an action.
        if decision_status != "ALLOWED":

            print(
                "Agent blocked automated remediation."
            )

            update_pipeline_status(
                incident_id,
                "MANUAL_REVIEW",
                reason,
            )

            audit_event(
                incident_id=incident_id,
                event_type="REMEDIATION_BLOCKED",
                action=action,
                status="BLOCKED",
                message=(
                    f"Automated remediation blocked: "
                    f"{reason}"
                ),
            )

            audit_event(
                incident_id=incident_id,
                event_type="PIPELINE_MANUAL_REVIEW",
                action="MANUAL_REVIEW",
                status="MANUAL_REVIEW",
                message=(
                    "Pipeline stopped because the "
                    "agent did not authorize remediation."
                ),
            )

            print(
                f"Incident {incident_id} requires "
                "manual review."
            )

            return

        # =================================================
        # 3. Controlled remediation
        # =================================================

        update_pipeline_status(
            incident_id,
            "REMEDIATION_RUNNING",
        )

        audit_event(
            incident_id=incident_id,
            event_type="REMEDIATION_STARTED",
            action=action,
            status="STARTED",
            message=(
                "Controlled remediation execution started."
            ),
        )

        print(
            "[3/4] Executing remediation..."
        )

        remediation_result = execute_action(
            incident_id=incident_id,
            action=action,
            allowed=True,
        )

        remediation_status = remediation_result.get(
            "status",
            "FAILED",
        )

        remediation_message = remediation_result.get(
            "message",
            remediation_result.get(
                "details",
                "Remediation execution completed.",
            ),
        )

        print(
            f"Remediation status: "
            f"{remediation_status}"
        )

        # -------------------------------------------------
        # Remediation success
        # -------------------------------------------------

        if remediation_status == "SUCCESS":

            update_pipeline_status(
                incident_id,
                "REMEDIATION_SUCCESS",
            )

            audit_event(
                incident_id=incident_id,
                event_type="REMEDIATION_COMPLETED",
                action=action,
                status="SUCCESS",
                message=remediation_message,
            )

        # -------------------------------------------------
        # Remediation blocked
        # -------------------------------------------------

        elif remediation_status == "BLOCKED":

            update_pipeline_status(
                incident_id,
                "MANUAL_REVIEW",
                remediation_message,
            )

            audit_event(
                incident_id=incident_id,
                event_type="REMEDIATION_COMPLETED",
                action=action,
                status="BLOCKED",
                message=remediation_message,
            )

            audit_event(
                incident_id=incident_id,
                event_type="PIPELINE_MANUAL_REVIEW",
                action="MANUAL_REVIEW",
                status="MANUAL_REVIEW",
                message=(
                    "Remediation was blocked by the "
                    "safety controls."
                ),
            )

            print(
                f"Incident {incident_id} requires "
                "manual review."
            )

            return

        # -------------------------------------------------
        # Remediation failed
        # -------------------------------------------------

        else:

            update_pipeline_status(
                incident_id,
                "FAILED",
                remediation_message,
            )

            audit_event(
                incident_id=incident_id,
                event_type="REMEDIATION_COMPLETED",
                action=action,
                status="FAILED",
                message=remediation_message,
            )

            mark_manual_review_if_needed(
                incident_id
            )

            print(
                f"Incident {incident_id} remediation "
                "failed."
            )

            return

        # =================================================
        # 4. Recovery verification
        # =================================================

        if (
            action in RECOVERY_ACTIONS
        ):

            action_id = remediation_result.get(
                "action_id"
            )

            if not action_id:

                message = (
                    "Remediation succeeded but no "
                    "remediation action ID was returned. "
                    "Recovery verification cannot continue."
                )

                update_pipeline_status(
                    incident_id,
                    "FAILED",
                    message,
                )

                audit_event(
                    incident_id=incident_id,
                    event_type="PIPELINE_FAILED",
                    action="RECOVERY_VERIFY",
                    status="FAILED",
                    message=message,
                )

                return

            update_pipeline_status(
                incident_id,
                "RECOVERY_RUNNING",
            )

            audit_event(
                incident_id=incident_id,
                event_type="RECOVERY_VERIFICATION_STARTED",
                action="VERIFY_RECOVERY",
                status="STARTED",
                message=(
                    "Post-remediation recovery verification started."
                ),
            )

            print(
                "[4/4] Starting recovery verification..."
            )

            recovery_result = verify_recovery(
                action_id
            )

            recovery_status = recovery_result.get(
                "status",
                "FAILED",
            )

            samples_checked = recovery_result.get(
                "samples_checked",
                0,
            )

            recovery_message = recovery_result.get(
                "message",
                recovery_result.get(
                    "details",
                    "Recovery verification completed.",
                ),
            )

            print(
                f"Recovery status: "
                f"{recovery_status}"
            )

            print(
                f"Recovery samples checked: "
                f"{samples_checked}"
            )

            audit_event(
                incident_id=incident_id,
                event_type="RECOVERY_VERIFICATION_COMPLETED",
                action="VERIFY_RECOVERY",
                status=recovery_status,
                message=(
                    f"{recovery_message} "
                    f"Samples checked: "
                    f"{samples_checked}."
                ),
            )

            # -------------------------------------------------
            # Recovery succeeded
            # -------------------------------------------------

            if recovery_status in {
                "RECOVERED",
                "SUCCESS",
            }:

                update_pipeline_status(
                    incident_id,
                    "COMPLETED",
                )

                audit_event(
                    incident_id=incident_id,
                    event_type="PIPELINE_COMPLETED",
                    action="COMPLETE_PIPELINE",
                    status="COMPLETED",
                    message=(
                        f"Incident {incident_id} "
                        "was remediated and recovery "
                        "was verified successfully."
                    ),
                )

                print(
                    f"Incident {incident_id} "
                    "pipeline completed successfully."
                )

                return

            # -------------------------------------------------
            # Recovery failed
            # -------------------------------------------------

            update_pipeline_status(
                incident_id,
                "FAILED",
                (
                    f"Recovery verification returned "
                    f"{recovery_status}."
                ),
            )

            audit_event(
                incident_id=incident_id,
                event_type="PIPELINE_FAILED",
                action="RECOVERY_VERIFY",
                status="FAILED",
                message=(
                    f"Recovery verification returned "
                    f"{recovery_status}."
                ),
            )

            mark_manual_review_if_needed(
                incident_id
            )

            print(
                f"Incident {incident_id} recovery "
                "verification failed."
            )

            return

        # =================================================
        # No recovery action required
        # =================================================

        update_pipeline_status(
            incident_id,
            "COMPLETED",
        )

        audit_event(
            incident_id=incident_id,
            event_type="RECOVERY_VERIFICATION_SKIPPED",
            action="VERIFY_RECOVERY",
            status="SKIPPED",
            message=(
                "No recovery verification action was "
                "required for the selected remediation."
            ),
        )

        audit_event(
            incident_id=incident_id,
            event_type="PIPELINE_COMPLETED",
            action="COMPLETE_PIPELINE",
            status="COMPLETED",
            message=(
                f"Incident {incident_id} completed "
                "the automatic pipeline."
            ),
        )

        print(
            f"Incident {incident_id} "
            "pipeline completed."
        )

    except Exception as exc:

        error_message = str(exc)

        print(
            f"Incident {incident_id} failed: "
            f"{error_message}"
        )

        update_pipeline_status(
            incident_id,
            "FAILED",
            error_message,
        )

        audit_event(
            incident_id=incident_id,
            event_type="PIPELINE_FAILED",
            action="PIPELINE_ERROR",
            status="FAILED",
            message=error_message,
        )

        mark_manual_review_if_needed(
            incident_id
        )


# =========================================================
# Single processing cycle
# =========================================================

def run_cycle() -> None:

    reset_stale_runs()

    incident_ids = (
        get_candidate_incident_ids()
    )

    if not incident_ids:

        print(
            "No new incidents to process."
        )

        return

    print(
        f"Found {len(incident_ids)} "
        f"incident(s) to process."
    )

    for incident_id in incident_ids:

        try:

            process_incident(
                incident_id
            )

        except Exception as exc:

            print(
                f"Unexpected pipeline error "
                f"for incident {incident_id}: "
                f"{exc}"
            )

            audit_event(
                incident_id=incident_id,
                event_type="PIPELINE_UNEXPECTED_ERROR",
                action="RUN_CYCLE",
                status="FAILED",
                message=str(exc),
            )


# =========================================================
# Continuous mode
# =========================================================

def run_continuously() -> None:

    print(
        "Starting automatic incident pipeline..."
    )

    print(
        f"Check interval: "
        f"{PIPELINE_INTERVAL} seconds"
    )

    print(
        f"Maximum attempts: "
        f"{MAX_ATTEMPTS}"
    )

    try:

        while True:

            run_cycle()

            time.sleep(
                PIPELINE_INTERVAL
            )

    except KeyboardInterrupt:

        print(
            "\nAutomatic incident pipeline stopped."
        )


# =========================================================
# Entry point
# =========================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Automatic SRE incident processing pipeline."
        ),
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Run one processing cycle "
            "and exit."
        ),
    )

    args = parser.parse_args()

    if args.once:

        run_cycle()

        return

    run_continuously()


if __name__ == "__main__":
    main()