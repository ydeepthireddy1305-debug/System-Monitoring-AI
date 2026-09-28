import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from backend.auth.dependencies import require_roles
from backend.auth.router import router as auth_router
from backend.database import get_connection
from backend.models import Metrics
from backend.services.dashboard_service import (
    get_dashboard_data,
)
from backend.services.monitoring_service import (
    save_metrics,
)


app = FastAPI(
    title="AI-Powered SRE Monitoring API",
    version="1.0.0",
)


FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://localhost:5174,http://localhost:3000",
    ).split(",")
    if origin.strip()
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)


@app.get("/")
def home() -> dict[str, str]:
    return {
        "status": "running",
        "service": "AI-Powered SRE Monitoring API",
    }


@app.post("/metrics")
def receive_metrics(
    data: Metrics,
) -> dict[str, str]:
    save_metrics(data)

    return {
        "status": "success",
        "message": "Metrics received and processed",
    }


@app.get("/dashboard")
def dashboard(
    current_user=Depends(
        require_roles(
            "VIEWER",
            "OPERATOR",
            "ADMIN",
        )
    ),
) -> dict:
    return get_dashboard_data()


@app.get("/audit/logs")
def get_audit_logs(
    incident_id: int | None = Query(
        default=None,
        description="Filter audit events by incident ID.",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of audit events to return.",
    ),
    current_user=Depends(
        require_roles(
            "VIEWER",
            "OPERATOR",
            "ADMIN",
        )
    ),
) -> dict:
    connection = get_connection()

    try:
        with connection.cursor(
            dictionary=True
        ) as cursor:

            if incident_id is not None:
                cursor.execute(
                    """
                    SELECT
                        id,
                        incident_id,
                        event_type,
                        actor,
                        action,
                        status,
                        message,
                        created_at
                    FROM audit_logs
                    WHERE incident_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                    (
                        incident_id,
                        limit,
                    ),
                )

            else:
                cursor.execute(
                    """
                    SELECT
                        id,
                        incident_id,
                        event_type,
                        actor,
                        action,
                        status,
                        message,
                        created_at
                    FROM audit_logs
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )

            logs = cursor.fetchall()

        return {
            "count": len(logs),
            "logs": logs,
        }

    finally:
        connection.close()


@app.get("/audit/logs/{incident_id}")
def get_incident_audit_logs(
    incident_id: int,
    current_user=Depends(
        require_roles(
            "VIEWER",
            "OPERATOR",
            "ADMIN",
        )
    ),
) -> dict:
    connection = get_connection()

    try:
        with connection.cursor(
            dictionary=True
        ) as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    incident_id,
                    event_type,
                    actor,
                    action,
                    status,
                    message,
                    created_at
                FROM audit_logs
                WHERE incident_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (incident_id,),
            )

            logs = cursor.fetchall()

        return {
            "incident_id": incident_id,
            "count": len(logs),
            "logs": logs,
        }

    finally:
        connection.close()
