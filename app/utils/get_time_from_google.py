import logging
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

# Reliable providers with Date header
TIME_PROVIDERS = [
    "https://www.cloudflare.com",
    "https://www.google.com",
    "https://www.apple.com",
]


def get_time_from_google():
    """Fetch current UTC time from external HTTP headers with fallback providers."""
    for url in TIME_PROVIDERS:
        try:
            response = httpx.head(url, timeout=5, follow_redirects=True)
            response.raise_for_status()
            date_header = response.headers.get("Date")
            if date_header:
                logger.debug("Got time from %s: %s", url, date_header)
                return datetime.strptime(date_header, "%a, %d %b %Y %H:%M:%S GMT")
        except Exception as e:
            logger.warning("Failed to get time from %s: %s", url, e)
            continue

    logger.error("All time providers failed")
    raise ValueError("All time providers failed")


if __name__ == "__main__":
    current_time = get_time_from_google()
    print("Ora corrente:", current_time)
