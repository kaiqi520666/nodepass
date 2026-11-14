import argparse
import time

from app.core.database import get_session_factory
from app.services.task_execution import process_next_task


def main() -> None:
    parser = argparse.ArgumentParser(description="NodePass generation task worker")
    parser.add_argument("--once", action="store_true", help="Process one due task and exit")
    parser.add_argument("--interval", type=float, default=2.0, help="Idle polling interval")
    args = parser.parse_args()
    while True:
        with get_session_factory()() as session:
            processed = process_next_task(session)
        if args.once or not processed:
            if args.once:
                return
            time.sleep(max(0.5, args.interval))


if __name__ == "__main__":
    main()
