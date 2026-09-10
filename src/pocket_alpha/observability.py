import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Deliberately allowlist fields: no request bodies, URLs or exception credentials.
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "event": record.getMessage(),
                "correlation_id": getattr(record, "correlation_id", None),
                "status_code": getattr(record, "status_code", None),
            }
        )


def configure_logging() -> None:
    logger = logging.getLogger("pocket_alpha")
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
