import { useEffect, useState } from "react";

const API_BASE_URL = (
    import.meta.env.VITE_API_BASE_URL ||
    "http://127.0.0.1:8000"
).replace(/\/+$/, "");


function getAccessToken() {
    return (
        sessionStorage.getItem("access_token") ||
        sessionStorage.getItem("token") ||
        sessionStorage.getItem("auth_token") ||
        sessionStorage.getItem("jwt") ||
        ""
    );
}


function formatDate(value) {
    if (!value) {
        return "—";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return String(value);
    }

    return date.toLocaleString();
}


function AuditTrail({ incidentId }) {
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    useEffect(() => {
        let cancelled = false;

        async function loadAuditTrail() {
            if (!incidentId) {
                setLogs([]);
                setLoading(false);
                return;
            }

            setLoading(true);
            setError("");

            const token = getAccessToken();

            const endpoint =
                `${API_BASE_URL}/audit/logs/${incidentId}`;

            console.log(
                "AuditTrail request:",
                endpoint
            );

            try {
                const response = await fetch(
                    endpoint,
                    {
                        method: "GET",
                        headers: {
                            Accept: "application/json",
                            ...(token
                                ? {
                                    Authorization:
                                        `Bearer ${token}`,
                                }
                                : {}),
                        },
                    }
                );

                if (response.status === 401) {
                    throw new Error(
                        "Authentication expired. Please sign in again."
                    );
                }

                if (response.status === 403) {
                    throw new Error(
                        "You are not authorized to view the audit trail."
                    );
                }

                if (response.status === 404) {
                    throw new Error(
                        `Audit endpoint returned 404: ${endpoint}`
                    );
                }

                if (!response.ok) {
                    throw new Error(
                        `Audit request failed with HTTP ${response.status}.`
                    );
                }

                const payload =
                    await response.json();

                const auditLogs =
                    Array.isArray(payload)
                        ? payload
                        : Array.isArray(payload.logs)
                            ? payload.logs
                            : Array.isArray(payload.data)
                                ? payload.data
                                : [];

                if (!cancelled) {
                    setLogs(auditLogs);
                }

            } catch (requestError) {
                console.error(
                    "Audit trail request failed:",
                    requestError
                );

                if (!cancelled) {
                    setLogs([]);
                    setError(
                        requestError.message ||
                        "Unable to load audit trail."
                    );
                }

            } finally {
                if (!cancelled) {
                    setLoading(false);
                }
            }
        }

        loadAuditTrail();

        return () => {
            cancelled = true;
        };
    }, [incidentId]);


    return (
        <div className="audit-trail">

            <div className="detail-section-header">

                <div>
                    <h4>
                        Audit Trail
                    </h4>

                    <p
                        style={{
                            margin: "4px 0 0",
                            fontSize: "13px",
                            opacity: 0.65,
                        }}
                    >
                        Complete system activity
                        for incident #{incidentId}
                    </p>
                </div>

            </div>


            {loading && (
                <div className="empty-state">
                    Loading audit activity...
                </div>
            )}


            {!loading && error && (
                <div className="empty-state">
                    <strong>
                        Audit Trail Error
                    </strong>

                    <div
                        style={{
                            marginTop: "6px",
                            fontSize: "13px",
                            opacity: 0.8,
                        }}
                    >
                        {error}
                    </div>
                </div>
            )}


            {!loading &&
                !error &&
                logs.length === 0 && (
                    <div className="empty-state">
                        No audit events recorded
                        for this incident yet.
                    </div>
                )
            }


            {!loading &&
                !error &&
                logs.length > 0 && (

                    <div
                        style={{
                            display: "grid",
                            gap: "10px",
                            marginTop: "14px",
                        }}
                    >

                        {logs.map((log) => (

                            <div
                                key={log.id}
                                style={{
                                    border:
                                        "1px solid rgba(127,127,127,0.18)",
                                    borderRadius: "10px",
                                    padding: "12px 14px",
                                }}
                            >

                                <div
                                    style={{
                                        display: "flex",
                                        justifyContent:
                                            "space-between",
                                        gap: "12px",
                                        flexWrap: "wrap",
                                    }}
                                >

                                    <strong>
                                        {log.event_type ||
                                            "SYSTEM_EVENT"}
                                    </strong>

                                    <span
                                        style={{
                                            fontSize: "12px",
                                            opacity: 0.65,
                                        }}
                                    >
                                        {formatDate(
                                            log.created_at
                                        )}
                                    </span>

                                </div>


                                <div
                                    style={{
                                        marginTop: "8px",
                                        fontSize: "13px",
                                    }}
                                >
                                    <strong>
                                        Actor:
                                    </strong>{" "}
                                    {log.actor || "SYSTEM"}
                                </div>


                                {log.action && (
                                    <div
                                        style={{
                                            marginTop: "4px",
                                            fontSize: "13px",
                                        }}
                                    >
                                        <strong>
                                            Action:
                                        </strong>{" "}
                                        {log.action}
                                    </div>
                                )}


                                {log.status && (
                                    <div
                                        style={{
                                            marginTop: "4px",
                                            fontSize: "13px",
                                        }}
                                    >
                                        <strong>
                                            Status:
                                        </strong>{" "}
                                        {log.status}
                                    </div>
                                )}


                                {log.message && (
                                    <div
                                        style={{
                                            marginTop: "7px",
                                            fontSize: "13px",
                                            opacity: 0.78,
                                            lineHeight: 1.5,
                                        }}
                                    >
                                        {log.message}
                                    </div>
                                )}

                            </div>

                        ))}

                    </div>
                )
            }

        </div>
    );
}


export default AuditTrail;