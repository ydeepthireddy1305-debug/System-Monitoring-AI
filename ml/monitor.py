import time

from ml.anomaly_detector import (
    load_metrics,
    detect_anomalies,
    save_anomalies,
)


MONITOR_INTERVAL = 10
def run_monitoring_cycle():
    data = load_metrics()

    if data.empty:
        print("No metrics available.")
        return

    results = detect_anomalies(data)

    anomalies = results[results["is_anomaly"]]

    print(
        f"Metrics analyzed: {len(results)} | "
        f"Anomalies detected: {len(anomalies)}"
    )

    save_anomalies(results)
def main():
    print("Starting ML monitoring...")

    try:
        while True:
            run_monitoring_cycle()
            time.sleep(MONITOR_INTERVAL)

    except KeyboardInterrupt:
        print("\nML monitoring stopped.")


if __name__ == "__main__":
    main()