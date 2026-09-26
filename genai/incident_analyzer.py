import json
import os
import sys
from typing import Any

from dotenv import load_dotenv
from google import genai

from backend.database import get_connection


load_dotenv()


MODEL_NAME = "gemini-3.5-flash"


# ---------------------------------------------------------
# GenAI execution mode
#
# gemini = use Google Gemini API
# mock   = use local deterministic analysis for testing
# ---------------------------------------------------------
GENAI_MODE = os.getenv(
    "GENAI_MODE",
    "mock",
).strip().lower()


# ---------------------------------------------------------
# Query incident and its related monitoring data
# ---------------------------------------------------------
INCIDENT_QUERY = """
    SELECT
        i.id AS incident_id,
        i.incident_type,
        i.severity,
        i.description AS incident_description,
        i.started_at,
        i.status AS incident_status,

        m.id AS metric_id,
        m.cpu,
        m.ram,
        m.disk,
        m.bytes_sent,
        m.bytes_received,
        m.recorded_at,

        ae.anomaly_score,
        ae.detected_at AS anomaly_detected_at,

        fp.risk_score AS failure_risk_score,
        fp.risk_level AS failure_risk_level,
        fp.predicted_at AS prediction_at

    FROM incidents i

    INNER JOIN metrics m
        ON m.id = i.metric_id

    LEFT JOIN anomaly_events ae
        ON ae.metric_id = m.id

    LEFT JOIN failure_predictions fp
        ON fp.id = (
            SELECT fp2.id
            FROM failure_predictions fp2
            WHERE fp2.metric_id = m.id
            ORDER BY fp2.predicted_at DESC, fp2.id DESC
            LIMIT 1
        )

    WHERE i.id = %s
"""


# ---------------------------------------------------------
# Get latest open incident first
# ---------------------------------------------------------
LATEST_INCIDENT_QUERY = """
    SELECT id
    FROM incidents
    ORDER BY
        CASE
            WHEN status = 'OPEN' THEN 0
            ELSE 1
        END,
        started_at DESC,
        id DESC
    LIMIT 1
"""


# ---------------------------------------------------------
# Save one analysis per incident
#
# Requires:
# UNIQUE KEY uq_incident_analysis_incident (incident_id)
#
# First time:
#     INSERT
#
# Same incident again:
#     UPDATE existing analysis
# ---------------------------------------------------------
INSERT_ANALYSIS_QUERY = """
    INSERT INTO incident_analysis (
        incident_id,
        analysis
    )
    VALUES (
        %s,
        %s
    )
    ON DUPLICATE KEY UPDATE
        analysis = VALUES(analysis)
"""


def get_client() -> genai.Client:
    """
    Create and return the Gemini client.

    GEMINI_API_KEY is loaded from the .env file.
    """

    api_key = os.getenv(
        "GEMINI_API_KEY"
    )

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not configured in the .env file."
        )

    return genai.Client()


def get_latest_incident_id() -> int | None:
    """
    Return the latest incident ID.

    Open incidents are preferred.
    """

    connection = get_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                LATEST_INCIDENT_QUERY
            )

            row = cursor.fetchone()

        if row is None:
            return None

        return int(row[0])

    finally:

        connection.close()


def get_incident_context(
    incident_id: int,
) -> dict[str, Any] | None:
    """
    Load all relevant telemetry and prediction
    information for an incident.
    """

    connection = get_connection()

    try:

        with connection.cursor(
            dictionary=True
        ) as cursor:

            cursor.execute(
                INCIDENT_QUERY,
                (incident_id,),
            )

            row = cursor.fetchone()

        return row

    finally:

        connection.close()


def build_prompt(
    incident: dict[str, Any],
) -> str:
    """
    Build the prompt used for Gemini analysis.
    """

    incident_json = json.dumps(
        incident,
        default=str,
        indent=2,
    )

    return f"""
You are an SRE incident analysis assistant.

Analyze the following incident using ONLY
the data provided below.

Do not invent metrics, causes, events,
or system behavior.

Clearly distinguish observed evidence
from reasonable inference.

Do not claim that a failure definitely
occurred unless the data proves it.

Do not execute or provide destructive commands.

Incident data:
{incident_json}

Produce the analysis using exactly
these sections:

1. INCIDENT SUMMARY
Give a concise description of what happened.

2. OBSERVED EVIDENCE
List the important metric, anomaly,
and failure-risk signals.

3. PROBABLE ROOT CAUSE
Explain the most likely cause based
on the available evidence.

State uncertainty when the data
is insufficient.

4. POTENTIAL IMPACT
Explain what could happen if
the condition continues.

5. RECOMMENDED ACTION
Suggest a safe, operationally reasonable
next action.

Do not perform the action.

6. RECOVERY CHECK
State what metrics or conditions
should be checked to confirm recovery.

Keep the analysis practical and suitable
for an SRE monitoring dashboard.
"""


def generate_mock_analysis(
    incident: dict[str, Any],
) -> str:
    """
    Generate a deterministic local analysis.

    This is used for testing the pipeline when
    Gemini quota is unavailable.

    No external API request is made.
    """

    incident_id = incident.get(
        "incident_id",
        "UNKNOWN",
    )

    incident_type = incident.get(
        "incident_type",
        "UNKNOWN",
    )

    severity = incident.get(
        "severity",
        "UNKNOWN",
    )

    description = (
        incident.get(
            "incident_description"
        )
        or "No description available."
    )

    cpu = incident.get(
        "cpu"
    )

    ram = incident.get(
        "ram"
    )

    disk = incident.get(
        "disk"
    )

    risk_score = incident.get(
        "failure_risk_score"
    )

    risk_level = incident.get(
        "failure_risk_level"
    )

    anomaly_score = incident.get(
        "anomaly_score"
    )

    return f"""
1. INCIDENT SUMMARY

Incident {incident_id} is a {severity} {incident_type}
incident.

Description:
{description}

2. OBSERVED EVIDENCE

CPU usage: {cpu}
RAM usage: {ram}
Disk usage: {disk}
Anomaly score: {anomaly_score}
Failure risk score: {risk_score}
Failure risk level: {risk_level}

These values represent the telemetry associated
with the incident record.

3. PROBABLE ROOT CAUSE

The available telemetry indicates that the
{incident_type} resource exceeded the monitoring
threshold associated with this incident.

The exact underlying system cause cannot be
confirmed from the available telemetry alone.

4. POTENTIAL IMPACT

If the abnormal resource condition continues,
application performance may degrade and services
may experience resource exhaustion or instability.

5. RECOMMENDED ACTION

Review the affected resource and identify the
processes or workloads responsible for the abnormal
usage.

Any automated remediation should be performed only
through the project's approved safety controls.

6. RECOVERY CHECK

Confirm that the affected resource returns below
its configured threshold for multiple consecutive
monitoring samples.

Also verify that no new incident is generated
for the same resource during the recovery window.
""".strip()


def generate_gemini_analysis(
    incident: dict[str, Any],
) -> str:
    """
    Generate analysis using Gemini.
    """

    client = get_client()

    prompt = build_prompt(
        incident
    )

    interaction = client.interactions.create(
        model=MODEL_NAME,
        input=prompt,
    )

    analysis = interaction.output_text

    if not analysis or not analysis.strip():

        raise ValueError(
            "Gemini returned an empty analysis."
        )

    return analysis.strip()


def generate_analysis(
    incident: dict[str, Any],
) -> str:
    """
    Select the configured GenAI execution mode.
    """

    if GENAI_MODE == "mock":

        print(
            "GenAI mode: MOCK "
            "(no Gemini API request)"
        )

        return generate_mock_analysis(
            incident
        )

    if GENAI_MODE == "gemini":

        print(
            f"GenAI mode: GEMINI "
            f"({MODEL_NAME})"
        )

        return generate_gemini_analysis(
            incident
        )

    raise ValueError(
        "Invalid GENAI_MODE. "
        "Use 'mock' or 'gemini'."
    )


def save_analysis(
    incident_id: int,
    analysis: str,
) -> None:
    """
    Insert or update the analysis for an incident.

    The database unique constraint on incident_id
    guarantees one analysis row per incident.
    """

    connection = get_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                INSERT_ANALYSIS_QUERY,
                (
                    incident_id,
                    analysis,
                ),
            )

        connection.commit()

    except Exception:

        connection.rollback()

        raise

    finally:

        connection.close()


def analyze_incident(
    incident_id: int,
) -> str:
    """
    Load incident context, generate analysis,
    and save the result.
    """

    incident = get_incident_context(
        incident_id
    )

    if incident is None:

        raise ValueError(
            f"Incident {incident_id} was not found."
        )

    analysis = generate_analysis(
        incident
    )

    save_analysis(
        incident_id,
        analysis,
    )

    return analysis


def main() -> None:
    """
    Command-line entry point.

    Usage:

        python -m genai.incident_analyzer

    or:

        python -m genai.incident_analyzer 191
    """

    if len(sys.argv) > 1:

        try:

            incident_id = int(
                sys.argv[1]
            )

        except ValueError:

            print(
                "Incident ID must be an integer."
            )

            return

    else:

        incident_id = (
            get_latest_incident_id()
        )

    if incident_id is None:

        print(
            "No incidents available."
        )

        return

    print(
        f"Analyzing incident ID: "
        f"{incident_id}"
    )

    analysis = analyze_incident(
        incident_id
    )

    print(
        "\n" + "=" * 70
    )

    print(
        "GENAI INCIDENT ANALYSIS"
    )

    print(
        "=" * 70
    )

    print(
        analysis
    )

    print(
        "=" * 70
    )

    print(
        "\nAnalysis saved to "
        "incident_analysis."
    )


if __name__ == "__main__":

    main()

