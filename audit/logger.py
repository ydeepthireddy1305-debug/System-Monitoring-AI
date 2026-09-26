from backend.database import get_connection


def log_event(
    incident_id: int | None,
    event_type: str,
    actor: str = "SYSTEM",
    action: str | None = None,
    status: str | None = None,
    message: str | None = None,
) -> None:
    """
    Store an event in the audit_logs table.
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO audit_logs (
                    incident_id,
                    event_type,
                    actor,
                    action,
                    status,
                    message
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    incident_id,
                    event_type,
                    actor,
                    action,
                    status,
                    message,
                ),
            )

        connection.commit()

    finally:
        connection.close()