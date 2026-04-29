import json
import logging
from datetime import datetime

# Set up a basic logger
logger = logging.getLogger("voyagemate_cache")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def log_cache_event(event_type: str, data: dict):
    """Logs a structured cache event."""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": event_type,
        **data
    }
    logger.info(json.dumps(log_entry))
