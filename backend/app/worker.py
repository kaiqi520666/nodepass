import argparse
import logging
import time

from app.core.database import get_session_factory
from app.services.task_execution import process_next_task

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="NodePass generation task worker")
    parser.add_argument("--once", action="store_true", help="Process one due task and exit")
    parser.add_argument("--interval", type=float, default=2.0, help="Idle polling interval")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    while True:
        try:
            with get_session_factory()() as session:
                processed = process_next_task(session)
        except Exception as exc:
            # Exception text can contain credentials, SQL parameters or upstream URLs.
            logger.error("worker_iteration_failed error_type=%s", type(exc).__name__)
            if args.once:
                return 1
            time.sleep(max(0.5, args.interval))
            continue
        if args.once or not processed:
            if args.once:
                return 0
            time.sleep(max(0.5, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
