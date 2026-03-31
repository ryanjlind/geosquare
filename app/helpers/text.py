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

    tokens = base.split()

    if len(tokens) >= 2:
        for i, token in enumerate(tokens[2:], start=2):
            if token in {'de', 'del', 'da', 'do', 'di', 'du', 'of'}:
                alias = ' '.join(tokens[:i])
                keys.add(alias)
                keys.add(alias.replace(' ', ''))
                break

        if tokens[0] in {'la', 'las', 'los', 'el'}:
            alias = ' '.join(tokens[1:])
            if alias:
                keys.add(alias)
                keys.add(alias.replace(' ', ''))

        if tokens[0] in {'la', 'las', 'los'}:
            for article in {'la', 'las', 'los'} - {tokens[0]}:
                article_alias = ' '.join([article] + tokens[1:])
                keys.add(article_alias)
                keys.add(article_alias.replace(' ', ''))

    return {key for key in keys if key}