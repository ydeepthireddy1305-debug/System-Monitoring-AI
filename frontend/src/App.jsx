import {
    useCallback,
    useEffect,
    useState,
} from "react";

import {
    CartesianGrid,
    Line,
    LineChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";

import {
    fetchDashboardData,
} from "./services/dashboardApi";

import AuditTrail from "./AuditTrail";

import {
    getCurrentUser,
    login,
    logout,
} from "./services/authApi";

import "./App.css";


const REFRESH_INTERVAL = 5000;
const INCIDENTS_PER_PAGE = 10;


/* =========================================================
   Utility functions
========================================================= */

function formatNumber(
    value,
    digits = 1
) {
    if (
        value === null ||
        value === undefined ||
        Number.isNaN(Number(value))
    ) {
        return "—";
    }

    return Number(value).toFixed(digits);
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


function formatTime(value) {
    if (!value) {
        return "—";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return String(value);
    }

    return date.toLocaleTimeString(
        [],
        {
            hour: "2-digit",
            minute: "2-digit",
        }
    );
}


/* =========================================================
   Metric Cards
========================================================= */

function MetricCard({
    title,
    value,
    unit,
}) {
    return (
        <div className="metric-card">

            <div className="metric-title">
                {title}
            </div>

            <div className="metric-value">

                {formatNumber(value)}

                <span className="metric-unit">
                    {unit}
                </span>

            </div>

        </div>
    );
}


function RiskCard({
    metric,
}) {
    const riskScore =
        metric?.risk_score ?? null;

    const riskLevel =
        metric?.risk_level ||
        "UNKNOWN";

    return (
        <div className="metric-card risk-card">

            <div className="metric-title">
                Failure Risk
            </div>

            <div className="metric-value">

                {riskScore === null
                    ? "—"
                    : formatNumber(
                        riskScore,
                        3
                    )}

                {riskScore !== null && (
                    <span className="metric-unit">
                        / 1
                    </span>
                )}

            </div>

            <div
                className={
                    `risk-level ${String(
                        riskLevel
                    ).toLowerCase()}`
                }
            >
                {riskLevel}
            </div>

        </div>
    );
}


function StatCard({
    title,
    value,
}) {
    return (
        <div className="stat-card">

            <div className="stat-title">
                {title}
            </div>

            <div className="stat-value">
                {value ?? 0}
            </div>

        </div>
    );
}


/* =========================================================
   Incident lifecycle helpers
========================================================= */

function getLifecycleStatus(
    incident,
    stage
) {
    if (stage === "AI") {

        return incident.ai_analysis
            ? "COMPLETED"
            : "PENDING";
    }


    if (stage === "AGENT") {

        return incident.agent_decision
            ? incident.agent_decision
            : "NOT STARTED";
    }


    if (stage === "ACTION") {

        return incident.agent_action
            ? incident.agent_action
            : "NOT STARTED";
    }


    if (stage === "REMEDIATION") {

        if (incident.remediation_status) {
            return incident.remediation_status;
        }

        return incident.agent_decision
            ? "PENDING"
            : "NOT STARTED";
    }


    if (stage === "RECOVERY") {

        if (incident.recovery_status) {
            return incident.recovery_status;
        }

        if (
            String(
                incident.remediation_status || ""
            ).toUpperCase() === "SUCCESS"
        ) {
            return "PENDING";
        }

        return "NOT STARTED";
    }


    return "NOT STARTED";
}


function isLifecycleCompleted(
    status
) {
    const normalized =
        String(status || "").toUpperCase();

    return [
        "COMPLETED",
        "ALLOWED",
        "SUCCESS",
        "RECOVERED",
    ].includes(normalized);
}


function getLifecycleClass(
    status
) {
    return isLifecycleCompleted(status)
        ? "timeline-step completed"
        : "timeline-step";
}


/* =========================================================
   Incident Card
========================================================= */

function IncidentCard({
    incident,
    expanded,
    onToggle,
}) {
    const aiStatus =
        getLifecycleStatus(
            incident,
            "AI"
        );

    const agentStatus =
        getLifecycleStatus(
            incident,
            "AGENT"
        );

    const actionStatus =
        getLifecycleStatus(
            incident,
            "ACTION"
        );

    const remediationStatus =
        getLifecycleStatus(
            incident,
            "REMEDIATION"
        );

    const recoveryStatus =
        getLifecycleStatus(
            incident,
            "RECOVERY"
        );


    return (
        <div className="incident-wrapper">

            <article
                className={
                    `incident-card ${
                        expanded
                            ? "incident-expanded"
                            : ""
                    }`
                }
            >

                <div className="incident-main">

                    <div className="incident-title-row">

                        <h3>
                            {
                                incident.incident_type
                            }
                        </h3>


                        <span
                            className={
                                `severity ${String(
                                    incident.severity || ""
                                ).toLowerCase()}`
                            }
                        >
                            {
                                incident.severity
                            }
                        </span>


                        <span
                            className={
                                `incident-status ${String(
                                    incident.status || ""
                                ).toLowerCase()}`
                            }
                        >
                            {
                                incident.status
                            }
                        </span>

                    </div>


                    <p>
                        {
                            incident.description ||
                            "No incident description available."
                        }
                    </p>


                    <div className="incident-meta">

                        <span>
                            Incident #
                            {" "}
                            {
                                incident.incident_id
                            }
                        </span>


                        <span>
                            Started:
                            {" "}
                            {
                                formatDate(
                                    incident.started_at
                                )
                            }
                        </span>


                        <span>
                            Risk:
                            {" "}
                            {
                                incident.risk_level ||
                                "UNKNOWN"
                            }
                        </span>


                        <span>
                            Score:
                            {" "}
                            {
                                formatNumber(
                                    incident.risk_score,
                                    3
                                )
                            }
                        </span>

                    </div>

                </div>


                <div className="agent-panel">

                    <div className="agent-step">

                        <span>
                            AI Analysis
                        </span>

                        <strong>
                            {aiStatus}
                        </strong>

                    </div>


                    <div className="agent-step">

                        <span>
                            Agent
                        </span>

                        <strong>
                            {agentStatus}
                        </strong>

                    </div>


                    <div className="agent-step">

                        <span>
                            Action
                        </span>

                        <strong>
                            {actionStatus}
                        </strong>

                    </div>


                    <div className="agent-step">

                        <span>
                            Remediation
                        </span>

                        <strong>
                            {remediationStatus}
                        </strong>

                    </div>


                    <div className="agent-step">

                        <span>
                            Recovery
                        </span>

                        <strong>
                            {recoveryStatus}
                        </strong>

                    </div>

                </div>


                <div className="incident-action">

                    <button
                        type="button"
                        className="details-button"
                        onClick={onToggle}
                        aria-expanded={expanded}
                    >
                        {expanded
                            ? "Hide full details"
                            : "View full details"}
                    </button>

                </div>

            </article>


            {expanded && (

                <div className="incident-details">

                    {/* =================================================
                        Gemini Analysis
                    ================================================= */}

                    <div className="detail-section">

                        <div className="detail-section-header">

                            <h4>
                                Gemini Incident Analysis
                            </h4>

                            <span className="detail-label">
                                GenAI
                            </span>

                        </div>


                        <pre>
                            {
                                incident.ai_analysis ||
                                "No AI analysis is available for this incident."
                            }
                        </pre>

                    </div>


                    {/* =================================================
                        Incident details
                    ================================================= */}

                    <div className="detail-grid">

                        <div className="detail-item">

                            <span>
                                Agent decision
                            </span>

                            <strong>
                                {agentStatus}
                            </strong>

                        </div>


                        <div className="detail-item">

                            <span>
                                Recommended action
                            </span>

                            <strong>
                                {actionStatus}
                            </strong>

                        </div>


                        <div className="detail-item detail-item-wide">

                            <span>
                                Agent reason
                            </span>

                            <strong>
                                {
                                    incident.agent_reason ||
                                    "No agent reason recorded."
                                }
                            </strong>

                        </div>


                        <div className="detail-item">

                            <span>
                                Remediation status
                            </span>

                            <strong
                                className={
                                    String(
                                        remediationStatus
                                    ).toLowerCase()
                                }
                            >
                                {remediationStatus}
                            </strong>

                        </div>


                        <div className="detail-item">

                            <span>
                                Recovery status
                            </span>

                            <strong
                                className={
                                    String(
                                        recoveryStatus
                                    ).toLowerCase()
                                }
                            >
                                {recoveryStatus}
                            </strong>

                        </div>


                        <div className="detail-item detail-item-wide">

                            <span>
                                Remediation details
                            </span>

                            <strong>
                                {
                                    incident.remediation_details ||
                                    "No remediation details recorded."
                                }
                            </strong>

                        </div>


                        <div className="detail-item">

                            <span>
                                Recovery samples
                            </span>

                            <strong>
                                {
                                    incident.recovery_samples ??
                                    "—"
                                }
                            </strong>

                        </div>


                        <div className="detail-item">

                            <span>
                                Recovery details
                            </span>

                            <strong>
                                {
                                    incident.recovery_details ||
                                    (
                                        recoveryStatus ===
                                        "NOT STARTED"
                                            ? "Recovery has not started."
                                            : "No recovery details recorded."
                                    )
                                }
                            </strong>

                        </div>

                    </div>


                    {/* =================================================
                        Audit Trail
                    ================================================= */}

                    <AuditTrail
                        incidentId={
                            incident.incident_id
                        }
                    />


                    {/* =================================================
                        Lifecycle
                    ================================================= */}

                    <div className="incident-timeline">

                        <div className="timeline-title">
                            Incident Lifecycle
                        </div>


                        <div className="timeline">

                            <div className="timeline-step completed">

                                <span>
                                    01
                                </span>

                                <strong>
                                    Incident
                                </strong>

                            </div>


                            <div className="timeline-line" />


                            <div
                                className={
                                    getLifecycleClass(
                                        aiStatus
                                    )
                                }
                            >

                                <span>
                                    02
                                </span>

                                <strong>
                                    Gemini
                                </strong>

                                <small>
                                    {aiStatus}
                                </small>

                            </div>


                            <div className="timeline-line" />


                            <div
                                className={
                                    getLifecycleClass(
                                        agentStatus
                                    )
                                }
                            >

                                <span>
                                    03
                                </span>

                                <strong>
                                    Agent
                                </strong>

                                <small>
                                    {agentStatus}
                                </small>

                            </div>


                            <div className="timeline-line" />


                            <div
                                className={
                                    getLifecycleClass(
                                        remediationStatus
                                    )
                                }
                            >

                                <span>
                                    04
                                </span>

                                <strong>
                                    Remediation
                                </strong>

                                <small>
                                    {remediationStatus}
                                </small>

                            </div>


                            <div className="timeline-line" />


                            <div
                                className={
                                    getLifecycleClass(
                                        recoveryStatus
                                    )
                                }
                            >

                                <span>
                                    05
                                </span>

                                <strong>
                                    Recovery
                                </strong>

                                <small>
                                    {recoveryStatus}
                                </small>

                            </div>

                        </div>

                    </div>

                </div>

            )}

        </div>
    );
}


/* =========================================================
   Login Screen
========================================================= */

function LoginScreen({
    onLogin,
    loading,
    error,
}) {
    const [
        username,
        setUsername,
    ] = useState("");


    const [
        password,
        setPassword,
    ] = useState("");


    async function handleSubmit(
        event
    ) {
        event.preventDefault();


        if (
            !username.trim() ||
            !password
        ) {
            return;
        }


        await onLogin(
            username.trim(),
            password
        );
    }


    return (
        <div
            style={{
                minHeight: "100vh",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: "24px",
                background: "#0b1220",
                boxSizing: "border-box",
            }}
        >

            <div
                style={{
                    width: "100%",
                    maxWidth: "420px",
                    padding: "32px",
                    borderRadius: "16px",
                    background: "#111827",
                    border:
                        "1px solid rgba(255,255,255,0.10)",
                    boxShadow:
                        "0 20px 50px rgba(0,0,0,0.35)",
                    color: "#ffffff",
                }}
            >

                <div
                    style={{
                        marginBottom: "24px",
                    }}
                >

                    <div
                        style={{
                            fontSize: "12px",
                            letterSpacing: "0.14em",
                            fontWeight: 700,
                            opacity: 0.7,
                            marginBottom: "8px",
                        }}
                    >
                        SRE MONITORING PLATFORM
                    </div>


                    <h1
                        style={{
                            margin: 0,
                            fontSize: "28px",
                        }}
                    >
                        Sign in
                    </h1>


                    <p
                        style={{
                            marginTop: "10px",
                            marginBottom: 0,
                            opacity: 0.72,
                            lineHeight: 1.5,
                        }}
                    >
                        Authenticate to access the
                        AI-powered monitoring dashboard.
                    </p>

                </div>


                {error && (

                    <div
                        style={{
                            marginBottom: "16px",
                            padding: "12px 14px",
                            borderRadius: "10px",
                            background:
                                "rgba(220, 38, 38, 0.14)",
                            border:
                                "1px solid rgba(248, 113, 113, 0.30)",
                            color: "#fecaca",
                            fontSize: "14px",
                            lineHeight: 1.4,
                        }}
                    >
                        {error}
                    </div>

                )}


                <form
                    onSubmit={handleSubmit}
                >

                    <label
                        style={{
                            display: "block",
                            marginBottom: "7px",
                            fontSize: "14px",
                            fontWeight: 600,
                        }}
                    >
                        Username
                    </label>


                    <input
                        type="text"
                        value={username}
                        onChange={(event) =>
                            setUsername(
                                event.target.value
                            )
                        }
                        autoComplete="username"
                        placeholder="Enter username"
                        disabled={loading}
                        style={{
                            width: "100%",
                            boxSizing: "border-box",
                            padding: "12px 14px",
                            marginBottom: "16px",
                            borderRadius: "10px",
                            border:
                                "1px solid rgba(255,255,255,0.14)",
                            background: "#0f172a",
                            color: "#ffffff",
                            outline: "none",
                        }}
                    />


                    <label
                        style={{
                            display: "block",
                            marginBottom: "7px",
                            fontSize: "14px",
                            fontWeight: 600,
                        }}
                    >
                        Password
                    </label>


                    <input
                        type="password"
                        value={password}
                        onChange={(event) =>
                            setPassword(
                                event.target.value
                            )
                        }
                        autoComplete="current-password"
                        placeholder="Enter password"
                        disabled={loading}
                        style={{
                            width: "100%",
                            boxSizing: "border-box",
                            padding: "12px 14px",
                            marginBottom: "20px",
                            borderRadius: "10px",
                            border:
                                "1px solid rgba(255,255,255,0.14)",
                            background: "#0f172a",
                            color: "#ffffff",
                            outline: "none",
                        }}
                    />


                    <button
                        type="submit"
                        disabled={
                            loading ||
                            !username.trim() ||
                            !password
                        }
                        style={{
                            width: "100%",
                            border: 0,
                            borderRadius: "10px",
                            padding: "12px 16px",
                            fontSize: "15px",
                            fontWeight: 700,
                            cursor:
                                loading
                                    ? "default"
                                    : "pointer",
                            background: "#2563eb",
                            color: "#ffffff",
                            opacity:
                                loading ||
                                !username.trim() ||
                                !password
                                    ? 0.6
                                    : 1,
                        }}
                    >
                        {loading
                            ? "Signing in..."
                            : "Sign in"}
                    </button>

                </form>

            </div>

        </div>
    );
}


/* =========================================================
   Main App
========================================================= */

function App() {

    const [
        currentUser,
        setCurrentUser,
    ] = useState(null);


    const [
        authLoading,
        setAuthLoading,
    ] = useState(true);


    const [
        authError,
        setAuthError,
    ] = useState("");


    const [
        loginLoading,
        setLoginLoading,
    ] = useState(false);


    const [
        data,
        setData,
    ] = useState(null);


    const [
        loading,
        setLoading,
    ] = useState(true);


    const [
        error,
        setError,
    ] = useState("");


    const [
        expandedIncidentId,
        setExpandedIncidentId,
    ] = useState(null);


    /* =====================================================
       Incident management state
    ===================================================== */

    const [
        incidentFilter,
        setIncidentFilter,
    ] = useState("ALL");


    const [
        incidentResource,
        setIncidentResource,
    ] = useState("ALL");


    const [
        incidentSearch,
        setIncidentSearch,
    ] = useState("");


    const [
        incidentPage,
        setIncidentPage,
    ] = useState(1);


    /* =====================================================
       Authentication
    ===================================================== */

    const handleLogin =
        useCallback(
            async (
                username,
                password
            ) => {

                setLoginLoading(true);
                setAuthError("");


                try {

                    await login(
                        username,
                        password
                    );


                    const user =
                        await getCurrentUser();


                    setCurrentUser(
                        user
                    );

                    setData(null);
                    setLoading(true);
                    setError("");

                } catch (loginError) {

                    console.error(
                        "Login failed:",
                        loginError
                    );


                    logout();


                    setAuthError(
                        loginError.response
                            ?.data?.detail ||
                        "Invalid username or password."
                    );


                    setCurrentUser(
                        null
                    );

                } finally {

                    setLoginLoading(
                        false
                    );

                }

            },
            []
        );


    useEffect(() => {

        const token =
            sessionStorage.getItem(
                "access_token"
            );


        if (!token) {

            setAuthLoading(
                false
            );

            return;
        }


        getCurrentUser()

            .then((user) => {

                setCurrentUser(
                    user
                );

            })

            .catch((authRequestError) => {

                console.error(
                    "Authentication check failed:",
                    authRequestError
                );


                logout();


                setCurrentUser(
                    null
                );

            })

            .finally(() => {

                setAuthLoading(
                    false
                );

            });

    }, []);


    /* =====================================================
       Dashboard loading
    ===================================================== */

    const loadDashboard =
        useCallback(
            async () => {

                if (!currentUser) {
                    return;
                }


                try {

                    const dashboardData =
                        await fetchDashboardData();


                    setData(
                        dashboardData
                    );


                    setError("");

                } catch (requestError) {

                    console.error(
                        "Dashboard request failed:",
                        requestError
                    );


                    if (
                        requestError.response
                            ?.status === 401
                    ) {

                        logout();

                        setCurrentUser(
                            null
                        );

                        setData(
                            null
                        );

                        setError("");

                        return;
                    }


                    setError(
                        "Unable to connect to the monitoring API."
                    );

                } finally {

                    setLoading(
                        false
                    );

                }

            },
            [currentUser]
        );


    useEffect(() => {

        if (!currentUser) {
            return undefined;
        }


        loadDashboard();


        const intervalId =
            window.setInterval(
                loadDashboard,
                REFRESH_INTERVAL
            );


        return () => {

            window.clearInterval(
                intervalId
            );

        };

    }, [
        currentUser,
        loadDashboard,
    ]);


    /* =====================================================
       Logout
    ===================================================== */

    function handleLogout() {

        logout();

        setCurrentUser(
            null
        );

        setData(
            null
        );

        setError("");

        setAuthError("");

        setExpandedIncidentId(
            null
        );

        setIncidentFilter(
            "ALL"
        );

        setIncidentResource(
            "ALL"
        );

        setIncidentSearch("");

        setIncidentPage(
            1
        );
    }


    /* =====================================================
       Loading / Login
    ===================================================== */

    if (authLoading) {

        return (
            <div className="app-shell">

                <div className="loading">
                    Checking authentication...
                </div>

            </div>
        );
    }


    if (!currentUser) {

        return (
            <LoginScreen
                onLogin={handleLogin}
                loading={loginLoading}
                error={authError}
            />
        );
    }


    /* =====================================================
       Dashboard data
    ===================================================== */

    const latestMetrics =
        data?.latest_metrics || {};


    const metricHistory =
        data?.metric_history || [];


    const incidents =
        data?.incidents || [];


    const riskHistory =
        data?.risk_history || [];


    const statistics =
        data?.statistics || {};


    const incidentStats =
        statistics.incidents || {};


    const anomalyStats =
        statistics.anomalies || {};


    const remediationStats =
        statistics.remediation || {};


    const recoveryStats =
        statistics.recovery || {};


    const latestRisk =
        riskHistory[
            riskHistory.length - 1
        ];


    /* =====================================================
       Chart data
    ===================================================== */

    const metricChartData =
        metricHistory.map(
            (item) => ({
                time: formatTime(
                    item.recorded_at
                ),

                cpu: Number(
                    item.cpu || 0
                ),

                ram: Number(
                    item.ram || 0
                ),

                disk: Number(
                    item.disk || 0
                ),
            })
        );


    const riskChartData =
        riskHistory.map(
            (item) => ({
                time: formatTime(
                    item.predicted_at
                ),

                risk: Number(
                    item.risk_score || 0
                ),
            })
        );


    /* =====================================================
       Incident filtering
    ===================================================== */

    const normalizedSearch =
        incidentSearch
            .trim()
            .toLowerCase();


    const filteredIncidents =
        [...incidents]

            .sort(
                (a, b) =>
                    Number(
                        b.incident_id || 0
                    ) -
                    Number(
                        a.incident_id || 0
                    )
            )

            .filter(
                (incident) => {

                    const status =
                        String(
                            incident.status || ""
                        ).toUpperCase();


                    const resource =
                        String(
                            incident.incident_type || ""
                        ).toUpperCase();


                    const matchesStatus =
                        incidentFilter === "ALL" ||
                        status === incidentFilter;


                    const matchesResource =
                        incidentResource === "ALL" ||
                        resource === incidentResource;


                    const searchableText = [

                        incident.incident_id,

                        incident.incident_type,

                        incident.status,

                        incident.severity,

                        incident.description,

                    ]
                        .join(" ")
                        .toLowerCase();


                    const matchesSearch =
                        !normalizedSearch ||
                        searchableText.includes(
                            normalizedSearch
                        );


                    return (
                        matchesStatus &&
                        matchesResource &&
                        matchesSearch
                    );
                }
            );


    const totalIncidentPages =
        Math.max(
            1,
            Math.ceil(
                filteredIncidents.length /
                INCIDENTS_PER_PAGE
            )
        );


    const safeIncidentPage =
        Math.min(
            incidentPage,
            totalIncidentPages
        );


    const paginatedIncidents =
        filteredIncidents.slice(
            (
                safeIncidentPage - 1
            ) *
                INCIDENTS_PER_PAGE,

            safeIncidentPage *
                INCIDENTS_PER_PAGE
        );


    /* =====================================================
       Incident toggle
    ===================================================== */

    function toggleIncident(
        incidentId
    ) {

        setExpandedIncidentId(
            currentId =>
                currentId === incidentId
                    ? null
                    : incidentId
        );

    }


    /* =====================================================
       Main dashboard
    ===================================================== */

    return (

        <div className="app-shell">

            {/* =================================================
                Header
            ================================================= */}

            <header className="dashboard-header">

                <div>

                    <p className="eyebrow">
                        SRE MONITORING PLATFORM
                    </p>


                    <h1>
                        AI-Powered System Monitoring
                    </h1>


                    <p className="subtitle">
                        Real-time infrastructure
                        health, failure prediction,
                        incident analysis and
                        controlled remediation.
                    </p>

                </div>


                <div
                    className="system-status"
                    style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "14px",
                    }}
                >

                    <div>

                        <span className="status-dot" />

                        Monitoring Active

                    </div>


                    <div
                        style={{
                            fontSize: "13px",
                            opacity: 0.82,
                        }}
                    >

                        {currentUser.username}

                        {" "}

                        ·

                        {" "}

                        {currentUser.role}

                    </div>


                    <button
                        type="button"
                        onClick={
                            handleLogout
                        }
                        style={{
                            border:
                                "1px solid rgba(255,255,255,0.18)",
                            background:
                                "rgba(255,255,255,0.06)",
                            color: "inherit",
                            borderRadius: "8px",
                            padding:
                                "7px 10px",
                            cursor: "pointer",
                        }}
                    >
                        Logout
                    </button>

                </div>

            </header>


            {/* =================================================
                Error
            ================================================= */}

            {error && (

                <div className="error-banner">
                    {error}
                </div>

            )}


            {/* =================================================
                Metric cards
            ================================================= */}

            <section className="metric-grid">

                <MetricCard
                    title="CPU Usage"
                    value={
                        latestMetrics.cpu
                    }
                    unit="%"
                />


                <MetricCard
                    title="RAM Usage"
                    value={
                        latestMetrics.ram
                    }
                    unit="%"
                />


                <MetricCard
                    title="Disk Usage"
                    value={
                        latestMetrics.disk
                    }
                    unit="%"
                />


                <RiskCard
                    metric={
                        latestRisk
                    }
                />

            </section>


            {/* =================================================
                Statistics
            ================================================= */}

            <section className="stats-grid">

                <StatCard
                    title="Total Incidents"
                    value={
                        incidentStats.total_incidents
                    }
                />


                <StatCard
                    title="Open Incidents"
                    value={
                        incidentStats.open_incidents
                    }
                />


                <StatCard
                    title="Anomalies Detected"
                    value={
                        anomalyStats.total_anomalies
                    }
                />


                <StatCard
                    title="Remediation Actions"
                    value={
                        remediationStats.total_actions
                    }
                />


                <StatCard
                    title="Successful Actions"
                    value={
                        remediationStats.successful_actions
                    }
                />


                <StatCard
                    title="Recovered"
                    value={
                        recoveryStats.recovered
                    }
                />

            </section>


            {/* =================================================
                Resource usage + failure risk
            ================================================= */}

            <section className="chart-grid">


                <div className="panel">

                    <div className="panel-header">

                        <div>

                            <h2>
                                Resource Usage
                            </h2>

                            <p>
                                Real metrics collected
                                by psutil.
                            </p>

                        </div>

                    </div>


                    <div className="chart-container">

                        <ResponsiveContainer
                            width="100%"
                            height={320}
                        >

                            <LineChart
                                data={
                                    metricChartData
                                }
                            >

                                <CartesianGrid
                                    strokeDasharray="3 3"
                                />


                                <XAxis
                                    dataKey="time"
                                />


                                <YAxis
                                    domain={[
                                        0,
                                        100,
                                    ]}
                                />


                                <Tooltip />


                                <Line
                                    type="monotone"
                                    dataKey="cpu"
                                    name="CPU"
                                    strokeWidth={2}
                                    dot={false}
                                />


                                <Line
                                    type="monotone"
                                    dataKey="ram"
                                    name="RAM"
                                    strokeWidth={2}
                                    dot={false}
                                />


                                <Line
                                    type="monotone"
                                    dataKey="disk"
                                    name="Disk"
                                    strokeWidth={2}
                                    dot={false}
                                />

                            </LineChart>

                        </ResponsiveContainer>

                    </div>

                </div>


                <div className="panel">

                    <div className="panel-header">

                        <div>

                            <h2>
                                Failure Risk
                            </h2>

                            <p>
                                Risk scores generated
                                by the ML pipeline.
                            </p>

                        </div>

                    </div>


                    <div className="chart-container">

                        <ResponsiveContainer
                            width="100%"
                            height={320}
                        >

                            <LineChart
                                data={
                                    riskChartData
                                }
                            >

                                <CartesianGrid
                                    strokeDasharray="3 3"
                                />


                                <XAxis
                                    dataKey="time"
                                />


                                <YAxis
                                    domain={[
                                        0,
                                        1,
                                    ]}
                                />


                                <Tooltip />


                                <Line
                                    type="monotone"
                                    dataKey="risk"
                                    name="Risk"
                                    strokeWidth={3}
                                    dot={false}
                                />

                            </LineChart>

                        </ResponsiveContainer>

                    </div>

                </div>

            </section>


            {/* =================================================
                Incident Management
            ================================================= */}

            <section className="panel">

                <div className="panel-header">

                    <div>

                        <h2>
                            Incident & Agent Activity
                        </h2>

                        <p>
                            Incident → AI analysis →
                            agent decision →
                            remediation → recovery.
                        </p>

                    </div>

                </div>


                {/* =================================================
                    Filters
                ================================================= */}

                <div
                    style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "10px",
                        alignItems: "center",
                        marginBottom: "20px",
                    }}
                >

                    <button
                        type="button"
                        onClick={() => {

                            setIncidentFilter(
                                "OPEN"
                            );

                            setIncidentPage(
                                1
                            );

                        }}
                        style={{
                            padding:
                                "8px 14px",
                            borderRadius:
                                "8px",
                            border:
                                "1px solid rgba(255,255,255,0.15)",
                            background:
                                incidentFilter ===
                                "OPEN"
                                    ? "#2563eb"
                                    : "rgba(255,255,255,0.06)",
                            color: "#fff",
                            cursor:
                                "pointer",
                        }}
                    >
                        Open
                    </button>


                    <button
                        type="button"
                        onClick={() => {

                            setIncidentFilter(
                                "RESOLVED"
                            );

                            setIncidentPage(
                                1
                            );

                        }}
                        style={{
                            padding:
                                "8px 14px",
                            borderRadius:
                                "8px",
                            border:
                                "1px solid rgba(255,255,255,0.15)",
                            background:
                                incidentFilter ===
                                "RESOLVED"
                                    ? "#2563eb"
                                    : "rgba(255,255,255,0.06)",
                            color: "#fff",
                            cursor:
                                "pointer",
                        }}
                    >
                        Resolved
                    </button>


                    <button
                        type="button"
                        onClick={() => {

                            setIncidentFilter(
                                "ALL"
                            );

                            setIncidentPage(
                                1
                            );

                        }}
                        style={{
                            padding:
                                "8px 14px",
                            borderRadius:
                                "8px",
                            border:
                                "1px solid rgba(255,255,255,0.15)",
                            background:
                                incidentFilter ===
                                "ALL"
                                    ? "#2563eb"
                                    : "rgba(255,255,255,0.06)",
                            color: "#fff",
                            cursor:
                                "pointer",
                        }}
                    >
                        All
                    </button>


                    <select
                        value={
                            incidentResource
                        }
                        onChange={
                            (event) => {

                                setIncidentResource(
                                    event.target.value
                                );

                                setIncidentPage(
                                    1
                                );

                            }
                        }
                        style={{
                            padding:
                                "8px 12px",
                            borderRadius:
                                "8px",
                            border:
                                "1px solid rgba(255,255,255,0.15)",
                            background:
                                "#111827",
                            color:
                                "#fff",
                            outline:
                                "none",
                        }}
                    >

                        <option value="ALL">
                            All resources
                        </option>

                        <option value="CPU">
                            CPU
                        </option>

                        <option value="RAM">
                            RAM
                        </option>

                        <option value="DISK">
                            Disk
                        </option>

                    </select>


                    <input
                        type="text"
                        value={
                            incidentSearch
                        }
                        onChange={
                            (event) => {

                                setIncidentSearch(
                                    event.target.value
                                );

                                setIncidentPage(
                                    1
                                );

                            }
                        }
                        placeholder="Search incident, resource, status..."
                        style={{
                            flex:
                                "1 1 240px",
                            minWidth:
                                "220px",
                            padding:
                                "9px 12px",
                            borderRadius:
                                "8px",
                            border:
                                "1px solid rgba(255,255,255,0.15)",
                            background:
                                "#0f172a",
                            color:
                                "#fff",
                            outline:
                                "none",
                        }}
                    />

                </div>


                {/* =================================================
                    Result count
                ================================================= */}

                <div
                    style={{
                        display: "flex",
                        justifyContent:
                            "space-between",
                        alignItems:
                            "center",
                        marginBottom:
                            "14px",
                        fontSize:
                            "13px",
                        opacity:
                            0.75,
                    }}
                >

                    <span>

                        Showing{" "}

                        {
                            paginatedIncidents.length
                        }

                        {" "}

                        of{" "}

                        {
                            filteredIncidents.length
                        }

                        {" "}

                        incidents

                    </span>


                    <span>

                        Page{" "}

                        {
                            safeIncidentPage
                        }

                        {" "}

                        of{" "}

                        {
                            totalIncidentPages
                        }

                    </span>

                </div>


                {/* =================================================
                    Incident list
                ================================================= */}

                <div className="incident-list">

                    {paginatedIncidents.length === 0 ? (

                        <div className="empty-state">

                            {incidents.length === 0
                                ? "No incidents available."
                                : "No incidents match the selected filters."}

                        </div>

                    ) : (

                        paginatedIncidents.map(
                            (incident) => (

                                <IncidentCard

                                    key={
                                        incident.incident_id
                                    }

                                    incident={
                                        incident
                                    }

                                    expanded={
                                        expandedIncidentId ===
                                        incident.incident_id
                                    }

                                    onToggle={() =>
                                        toggleIncident(
                                            incident.incident_id
                                        )
                                    }

                                />

                            )
                        )

                    )}

                </div>


                {/* =================================================
                    Pagination
                ================================================= */}

                {totalIncidentPages > 1 && (

                    <div
                        style={{
                            display:
                                "flex",
                            justifyContent:
                                "center",
                            alignItems:
                                "center",
                            gap:
                                "12px",
                            marginTop:
                                "20px",
                        }}
                    >

                        <button
                            type="button"
                            disabled={
                                safeIncidentPage <=
                                1
                            }
                            onClick={() =>
                                setIncidentPage(
                                    current =>
                                        Math.max(
                                            1,
                                            current - 1
                                        )
                                )
                            }
                            style={{
                                padding:
                                    "8px 14px",
                                borderRadius:
                                    "8px",
                                border:
                                    "1px solid rgba(255,255,255,0.15)",
                                background:
                                    "rgba(255,255,255,0.06)",
                                color:
                                    "#fff",
                                cursor:
                                    safeIncidentPage <=
                                    1
                                        ? "not-allowed"
                                        : "pointer",
                                opacity:
                                    safeIncidentPage <=
                                    1
                                        ? 0.4
                                        : 1,
                            }}
                        >
                            Previous
                        </button>


                        <span
                            style={{
                                fontSize:
                                    "13px",
                                opacity:
                                    0.75,
                            }}
                        >
                            Page{" "}
                            {
                                safeIncidentPage
                            }{" "}
                            of{" "}
                            {
                                totalIncidentPages
                            }
                        </span>


                        <button
                            type="button"
                            disabled={
                                safeIncidentPage >=
                                totalIncidentPages
                            }
                            onClick={() =>
                                setIncidentPage(
                                    current =>
                                        Math.min(
                                            totalIncidentPages,
                                            current + 1
                                        )
                                )
                            }
                            style={{
                                padding:
                                    "8px 14px",
                                borderRadius:
                                    "8px",
                                border:
                                    "1px solid rgba(255,255,255,0.15)",
                                background:
                                    "rgba(255,255,255,0.06)",
                                color:
                                    "#fff",
                                cursor:
                                    safeIncidentPage >=
                                    totalIncidentPages
                                        ? "not-allowed"
                                        : "pointer",
                                opacity:
                                    safeIncidentPage >=
                                    totalIncidentPages
                                        ? 0.4
                                        : 1,
                            }}
                        >
                            Next
                        </button>

                    </div>

                )}

            </section>


            {/* =================================================
                Footer
            ================================================= */}

            <footer className="dashboard-footer">

                <span>
                    Last updated automatically
                    every 5 seconds
                </span>


                <span>
                    API:
                    {" "}
                    {
                        import.meta.env.VITE_API_BASE_URL
                    }
                </span>

            </footer>

        </div>
    );
}


export default App;