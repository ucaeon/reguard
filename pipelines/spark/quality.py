from datetime import datetime
import re
from zoneinfo import ZoneInfo


class QualityError(ValueError):
    pass


def text(value, required=False, maximum=None):
    if value is None:
        value = ""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise QualityError("INVALID_TEXT_TYPE")
    value = str(value).strip()
    if value in {"", "-", "해당없음", "데이터없음"}:
        if required:
            raise QualityError("MISSING_REQUIRED_FIELD")
        return None
    if "\x00" in value or (maximum and len(value) > maximum):
        raise QualityError("INVALID_TEXT_LENGTH_OR_NUL")
    return value


def timestamp(value, required=False, aware=False):
    value = text(value, required)
    if value is None:
        return None
    try:
        parsed = (
            datetime.strptime(value, "%Y%m%d")
            if re.fullmatch(r"\d{8}", value)
            else datetime.fromisoformat(value)
        )
        if parsed.tzinfo is None:
            if aware:
                raise QualityError("TIMEZONE_REQUIRED")
            parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        return parsed.isoformat()
    except ValueError:
        raise QualityError("INVALID_TIMESTAMP") from None


def image(value):
    value = text(value)
    if value is None:
        return None
    value = value.split(",")[0].strip()
    return value if re.fullmatch(r"https?://[^\s]+", value, re.IGNORECASE) else None
