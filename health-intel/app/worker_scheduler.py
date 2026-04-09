import logging
import time

from app.services.scheduler import start_scheduler, stop_scheduler


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pcube.scheduler_worker")


def main() -> None:
    start_scheduler()
    logger.info("PCUBE scheduler worker started")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        logger.info("PCUBE scheduler worker stopping")
    finally:
        stop_scheduler()
if __name__ == "__main__":
    main()
