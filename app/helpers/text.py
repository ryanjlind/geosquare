import re
import unicodedata


def strip_accents(value: str) -> str:
    return ''.join(
        ch for ch in unicodedata.normalize('NFKD', value)
        if not unicodedata.combining(ch)
    )


def normalize_place_name(value: str) -> str:
    value = value.replace('ß', 'ss')
    value = strip_accents(value).lower().strip()
    value = value.replace('&', ' and ')
    value = re.sub(r"[’'`]", '', value)
    value = re.sub(r'[^a-z0-9]+', ' ', value)
    value = re.sub(r'\s+', ' ', value).strip()
    return value