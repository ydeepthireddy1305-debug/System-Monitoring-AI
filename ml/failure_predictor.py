import pandas as pd
from sklearn.ensemble import IsolationForest

from backend.database import get_connection


WINDOW_SIZE = 50
MINIMUM_RECORDS = 20

RISK_THRESHOLD_LOW = 0.30
RISK_THRESHOLD_HIGH = 0.70

FEATURES = [
    "cpu",
    "ram",
    "disk",
    "bytes_sent_rate",
    "bytes_received_rate",
    "cpu_trend",
    "ram_trend",
    "disk_trend",
]


def load_recent_metrics() -> pd.DataFrame:
    connection = get_connection()

    query = """
        SELECT
            id,
            cpu,
            ram,
            disk,
            bytes_sent,
            bytes_received,
            recorded_at
        FROM metrics
        ORDER BY recorded_at DESC
        LIMIT %s
    """

    try:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(query, (WINDOW_SIZE,))
            rows = cursor.fetchall()

        data = pd.DataFrame(rows)

        if data.empty:
            return data

        return data.sort_values(
            "recorded_at"
        ).reset_index(drop=True)

    finally:
        connection.close()


def prepare_features(data: pd.DataFrame) -> pd.DataFrame:
    data = data.copy()

    data["recorded_at"] = pd.to_datetime(
        data["recorded_at"]
    )

    elapsed_seconds = (
        data["recorded_at"]
        .diff()
        .dt.total_seconds()
    )

    elapsed_seconds = elapsed_seconds.replace(
        0,
        pd.NA,
    )

    data["bytes_sent_rate"] = (
        data["bytes_sent"]
        .diff()
        .div(elapsed_seconds)
        .fillna(0)
        .clip(lower=0)
    )

    data["bytes_received_rate"] = (
        data["bytes_received"]
        .diff()
        .div(elapsed_seconds)
        .fillna(0)
        .clip(lower=0)
    )

    data["cpu_trend"] = (
        data["cpu"]
        .diff()
        .fillna(0)
    )

    data["ram_trend"] = (
        data["ram"]
        .diff()
        .fillna(0)
    )

    data["disk_trend"] = (
        data["disk"]
        .diff()
        .fillna(0)
    )

    return data


def calculate_anomaly_signal(
    data: pd.DataFrame,
) -> pd.Series:
    model = IsolationForest(
        n_estimators=100,
        contamination="auto",
        random_state=42,
        n_jobs=-1,
    )

    model.fit(data[FEATURES])

    predictions = model.predict(data[FEATURES])

    return pd.Series(
        (predictions == -1).astype(float),
        index=data.index,
    )


def calculate_resource_risk(
    data: pd.DataFrame,
) -> pd.Series:
    cpu_risk = data["cpu"].clip(0, 100) / 100
    ram_risk = data["ram"].clip(0, 100) / 100
    disk_risk = data["disk"].clip(0, 100) / 100

    return (
        cpu_risk * 0.30
        + ram_risk * 0.40
        + disk_risk * 0.30
    )


def calculate_trend_risk(
    data: pd.DataFrame,
) -> pd.Series:
    cpu_trend = data["cpu_trend"].clip(lower=0)
    ram_trend = data["ram_trend"].clip(lower=0)
    disk_trend = data["disk_trend"].clip(lower=0)

    trend_risk = (
        cpu_trend / 10 * 0.30
        + ram_trend / 5 * 0.50
        + disk_trend / 5 * 0.20
    )

    return trend_risk.clip(0, 1)


def calculate_risk_score(
    data: pd.DataFrame,
) -> pd.DataFrame:
    data = data.copy()

    data["anomaly_signal"] = (
        calculate_anomaly_signal(data)
    )

    data["resource_risk"] = (
        calculate_resource_risk(data)
    )

    data["trend_risk"] = (
        calculate_trend_risk(data)
    )

    data["risk_score"] = (
        data["resource_risk"] * 0.45
        + data["trend_risk"] * 0.35
        + data["anomaly_signal"] * 0.20
    ).clip(0, 1)

    data["risk_level"] = pd.cut(
        data["risk_score"],
        bins=[
            -float("inf"),
            RISK_THRESHOLD_LOW,
            RISK_THRESHOLD_HIGH,
            float("inf"),
        ],
        labels=[
            "LOW",
            "MEDIUM",
            "HIGH",
        ],
    )

    return data


def predict_failure_risk(
    data: pd.DataFrame,
) -> dict[str, float | str | int]:
    if data.empty:
        raise ValueError(
            "No metrics available for prediction."
        )

    prepared_data = prepare_features(data)
    results = calculate_risk_score(prepared_data)
    latest = results.iloc[-1]

    return {
        "metric_id": int(latest["id"]),
        "risk_score": float(latest["risk_score"]),
        "risk_level": str(latest["risk_level"]),
    }


def save_prediction(
    prediction: dict[str, float | str | int],
) -> None:
    connection = get_connection()

    query = """
        INSERT INTO failure_predictions
            (metric_id, risk_score, risk_level)
        VALUES
            (%s, %s, %s)
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                (
                    prediction["metric_id"],
                    prediction["risk_score"],
                    prediction["risk_level"],
                ),
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def main() -> None:
    data = load_recent_metrics()

    if len(data) < MINIMUM_RECORDS:
        print(
            f"At least {MINIMUM_RECORDS} metric records "
            "are required for failure prediction."
        )
        return

    prediction = predict_failure_risk(data)

    print(
        f"Latest metric ID: "
        f"{prediction['metric_id']}"
    )

    print(
        f"Failure risk score: "
        f"{prediction['risk_score']:.3f}"
    )

    print(
        f"Failure risk level: "
        f"{prediction['risk_level']}"
    )

    save_prediction(prediction)


if __name__ == "__main__":
    main()