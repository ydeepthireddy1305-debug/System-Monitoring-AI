import pandas as pd
from sklearn.ensemble import IsolationForest
from backend.database import get_connection
MINIMUM_RECORDS = 50
Window_size=500
FEATURES = [
    "cpu",
    "ram",
    "disk",
    "bytes_sent_rate",
    "bytes_received_rate",
]
def load_metrics() -> pd.DataFrame:
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
            cursor.execute(query, (Window_size,))
            rows = cursor.fetchall()

        data = pd.DataFrame(rows)

        return data.sort_values(
            "recorded_at"
        ).reset_index(drop=True)

    finally:
        connection.close()


def prepare_features(data: pd.DataFrame) -> pd.DataFrame:
    data = data.copy()

    data["recorded_at"] = pd.to_datetime(data["recorded_at"])

    elapsed_seconds = (
        data["recorded_at"]
        .diff()
        .dt.total_seconds()
    )

    elapsed_seconds = elapsed_seconds.replace(0, pd.NA)

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

    return data
def detect_anomalies(data: pd.DataFrame) -> pd.DataFrame:
    data = prepare_features(data)

    model = IsolationForest(
        n_estimators=100,
        contamination="auto",
        random_state=42,
        n_jobs=-1,
    )

    model.fit(data[FEATURES])

    data["anomaly_score"] = model.decision_function(
        data[FEATURES]
    )

    data["is_anomaly"] = model.predict(
        data[FEATURES]
    ) == -1

    return data
def save_anomalies(data: pd.DataFrame) -> None:
    anomalies = data[data["is_anomaly"]]

    if anomalies.empty:
        return

    connection = get_connection()

    check_query = """
        SELECT metric_id
        FROM anomaly_events
        WHERE metric_id = %s
    """

    insert_query = """
        INSERT INTO anomaly_events
            (metric_id, anomaly_score)
        VALUES
            (%s, %s)
    """

    try:
        with connection.cursor() as cursor:
            new_records = []

            for _, row in anomalies.iterrows():
                metric_id = int(row["id"])
                anomaly_score = float(row["anomaly_score"])

                cursor.execute(
                    check_query,
                    (metric_id,),
                )

                if cursor.fetchone() is None:
                    new_records.append(
                        (
                            metric_id,
                            anomaly_score,
                        )
                    )

            if new_records:
                cursor.executemany(
                    insert_query,
                    new_records,
                )

        connection.commit()

        print(
            f"New anomaly events saved: {len(new_records)}"
        )

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def main() -> None:
    data = load_metrics()

    if len(data) < MINIMUM_RECORDS:
        print(
            f"At least {MINIMUM_RECORDS} metric records are required."
        )
        return

    results = detect_anomalies(data)
    anomalies = results[results["is_anomaly"]]
    print(f"Rolling window size: {len(results)}")
    print(f"Anomalies detected: {len(anomalies)}")
    save_anomalies(results)


    if anomalies.empty:
        print("No anomalies detected.")
        return

    print("\nAnomalous records:")

    print(
        anomalies[
            [
                "id",
                "cpu",
                "ram",
                "disk",
                "bytes_sent_rate",
                "bytes_received_rate",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()

