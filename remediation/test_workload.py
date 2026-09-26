import argparse
import multiprocessing
import os
import tempfile
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

PID_FILES = {
    "cpu": PROJECT_ROOT / ".remediation_cpu.pid",
    "ram": PROJECT_ROOT / ".remediation_ram.pid",
    "disk": PROJECT_ROOT / ".remediation_disk.pid",
}

DEFAULT_RAM_MB = 512
DISK_TEST_SIZE_MB = 100


def cpu_worker() -> None:
    value = 0

    while True:
        for number in range(500_000):
            value = (
                value * 1664525
                + number
                + 1013904223
            ) & 0xFFFFFFFF


def create_ram_load(
    size_mb: int,
) -> bytearray:
    if size_mb <= 0:
        raise ValueError(
            "RAM size must be greater than zero."
        )

    size_bytes = (
        size_mb * 1024 * 1024
    )

    data = bytearray(size_bytes)

    for index in range(
        0,
        len(data),
        4096,
    ):
        data[index] = 1

    return data


def create_disk_test_file() -> Path:
    file_path = (
        Path(tempfile.gettempdir())
        / "system_monitoring_disk_test.bin"
    )

    block_size = 1024 * 1024

    with file_path.open("wb") as file:
        block = os.urandom(block_size)

        for _ in range(DISK_TEST_SIZE_MB):
            file.write(block)

    return file_path


def write_pid_file(
    mode: str,
) -> None:
    PID_FILES[mode].write_text(
        str(os.getpid()),
        encoding="utf-8",
    )


def remove_pid_file(
    mode: str,
) -> None:
    PID_FILES[mode].unlink(
        missing_ok=True
    )


def cleanup_processes(
    processes: list[
        multiprocessing.Process
    ],
) -> None:
    for process in processes:
        if process.is_alive():
            process.terminate()

    for process in processes:
        process.join(
            timeout=5
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Controlled CPU, RAM and Disk "
            "workloads for remediation testing."
        )
    )

    parser.add_argument(
        "--mode",
        choices=[
            "cpu",
            "ram",
            "disk",
        ],
        required=True,
    )

    parser.add_argument(
        "--ram-mb",
        type=int,
        default=DEFAULT_RAM_MB,
    )

    args = parser.parse_args()

    mode = args.mode

    processes = []
    ram_data = None
    disk_file = None

    try:
        write_pid_file(mode)

        if mode == "cpu":
            worker_count = max(
                1,
                multiprocessing.cpu_count(),
            )

            processes = [
                multiprocessing.Process(
                    target=cpu_worker
                )
                for _ in range(worker_count)
            ]

            for process in processes:
                process.start()

            print(
                f"Controlled CPU workload started "
                f"with {worker_count} workers."
            )

        elif mode == "ram":
            ram_data = create_ram_load(
                args.ram_mb
            )

            print(
                f"Controlled RAM workload started "
                f"with approximately {args.ram_mb} MB."
            )

        else:
            disk_file = (
                create_disk_test_file()
            )

            print(
                "Controlled Disk workload started."
            )

            print(
                f"Temporary file: {disk_file}"
            )

        print(
            f"Controller PID: {os.getpid()}"
        )

        print(
            f"Controlled {mode.upper()} "
            "test workload is running."
        )

        print(
            "The remediation agent can stop this "
            "specific resource workload."
        )

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print(
            "\nManual stop requested."
        )

    finally:
        cleanup_processes(
            processes
        )

        ram_data = None

        if disk_file is not None:
            try:
                disk_file.unlink(
                    missing_ok=True
                )
            except OSError:
                pass

        remove_pid_file(
            mode
        )

        print(
            f"Controlled {mode.upper()} "
            "workload stopped."
        )


if __name__ == "__main__":
    main()