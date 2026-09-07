import asyncio

from app.settings.config import settings
from app.settings.logging_config import setup_logging
from app.worker.consumer import run_forever


def main() -> None:
    setup_logging(settings.log_level)
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
