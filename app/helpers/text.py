import re
import unicodedata


def strip_accents(value: str) -> str:
    return ''.join(
        ch for ch in unicodedata.normalize('NFKD', value)
        if not unicodedata.combining(ch)
    )


def normalize_place_name(value: str) -> str:
    value = strip_accents(value).lower().strip()
    value = value.replace('&', ' and ')
    value = re.sub(r"[’'`]", '', value)
    value = re.sub(r'[^a-z0-9]+', ' ', value)
    value = re.sub(r'\s+', ' ', value).strip()
    return value


def build_match_keys(value: str) -> set[str]:
    base = normalize_place_name(value)
    compact = base.replace(' ', '')

    keys = {base, compact}

    if base.endswith('s'):
        keys.add(base[:-1])
    else:
        keys.add(base + 's')

    if base.startswith('st '):
        keys.add(base.replace('st ', 'saint ', 1))
    if base.startswith('saint '):
        keys.add(base.replace('saint ', 'st ', 1))

    return {key for key in keys if key}
