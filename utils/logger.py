import logging
from pathlib import Path

LOG_PATH = Path(__file__).parent.parent / "run.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)


def get(name: str) -> logging.Logger:
    return logging.getLogger(name)
