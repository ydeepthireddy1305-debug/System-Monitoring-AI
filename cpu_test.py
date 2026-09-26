import multiprocessing
import time


TEST_DURATION = 60


def stress_cpu() -> None:
    end_time = time.time() + TEST_DURATION
    value = 0

    while time.time() < end_time:
        value = (
            value * 1664525 + 1013904223
        ) & 0xFFFFFFFF


def main() -> None:
    cpu_count = multiprocessing.cpu_count()

    processes = [
        multiprocessing.Process(
            target=stress_cpu
        )
        for _ in range(cpu_count)
    ]

    print(
        f"Detected logical CPUs: {cpu_count}"
    )
    print(
        f"Starting {len(processes)} CPU workers..."
    )
    print(
        f"CPU load test running for {TEST_DURATION} seconds..."
    )

    for process in processes:
        process.start()

    for process in processes:
        process.join()

    print("CPU test completed.")


if __name__ == "__main__":
    main()