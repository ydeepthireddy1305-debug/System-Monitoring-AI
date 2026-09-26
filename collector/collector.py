import time

import psutil
import requests


API_URL = "http://127.0.0.1:8000/metrics"
COLLECTION_INTERVAL = 2


def collect_metrics():
    cpu_usage = psutil.cpu_percent()
    ram_usage = psutil.virtual_memory().percent
    disk_usage = psutil.disk_usage("C:\\")
    network = psutil.net_io_counters()

    return {
        "cpu": cpu_usage,
        "ram": ram_usage,
        "disk": disk_usage.percent,
        "bytes_sent": network.bytes_sent,
        "bytes_received": network.bytes_recv,
    }


def main():
    print("Starting system monitor...")

    while True:
        data = collect_metrics()

        requests.post(
            API_URL,
            json=data
        )

        print(
            f"CPU: {data['cpu']}% | "
            f"RAM: {data['ram']}% | "
            f"Disk: {data['disk']}%"
        )

        time.sleep(COLLECTION_INTERVAL)


if __name__ == "__main__":
    main()