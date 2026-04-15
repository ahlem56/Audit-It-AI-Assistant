import re
from datetime import datetime


def slugify(value: str, max_length: int = 60) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:max_length] if value else "export"


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")