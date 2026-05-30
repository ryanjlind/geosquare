from app.helpers.text import build_match_keys, normalize_place_name
from app.helpers.logging import debug as log_debug


def phonetic_key(text: str) -> str:
    text = normalize_place_name(text).replace(' ', '')
    if not text:
        return ''

    result = []
    i = 0

    while i < len(text):
        c = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ''

        if c == 'p' and nxt == 'h':
            result.append('f')
            i += 2
            continue

        if c == 'c':
            result.append('s' if nxt in 'iey' else 'k')
            i += 1
            continue

        if c == 'k':
            result.append('k')
            i += 1
            continue

        if c == 'q':
            result.append('k')
            if nxt == 'u':
                i += 2
            else:
                i += 1
            continue

        if c == 'x':
            result.append('ks')
            i += 1
            continue

        if c == 'z':
            result.append('s')
            i += 1
            continue

        if c == 'g':
            result.append('j' if nxt in 'iey' else 'g')
            i += 1
            continue

        result.append(c)
        i += 1

    collapsed = []
    prev = None
    for chunk in result:
        if chunk != prev:
            collapsed.append(chunk)
        prev = chunk

    return ''.join(collapsed)


def find_matching_city(rows, guess_text: str):
    guess_text = guess_text.strip()

    precision_filter = None
    if ',' in guess_text:
        parts = [p.strip() for p in guess_text.split(',', 1)]
        if len(parts) == 2:
            guess_text, precision_part = parts
            precision_filter = precision_part.upper()

    guess_keys = build_match_keys(guess_text)
    normalized_guess = normalize_place_name(guess_text)

    if 'city' not in normalized_guess.split():
        guess_keys.add(f'{normalized_guess} city')
        guess_keys.add(f'{normalized_guess}city')

    guess_phonetic_keys = {
        phonetic_key(key)
        for key in guess_keys
        if len(key.replace(' ', '')) >= 3
    }

    log_debug(f'\n=== GUESS: {guess_text}')
    log_debug(f'Precision filter: {precision_filter}')
    log_debug(f'Normalized: {normalized_guess}')
    log_debug(f'Keys: {guess_keys}')
    log_debug(f'Phonetic Keys: {guess_phonetic_keys}')

    candidate_rows = rows
    if precision_filter:
        log_debug(f'Trying "{guess_text}, {precision_filter}" with province code filter...')
        province_filtered_rows = []

        for r in rows:
            province_codes_raw = getattr(r, 'ProvinceCodes', None) or ''
            province_codes = {
                code.strip().upper()
                for code in province_codes_raw.split(',')
                if code.strip()
            }

            if precision_filter in province_codes:
                province_filtered_rows.append(r)

        log_debug(f'Province code matches: {len(province_filtered_rows)}')

        if province_filtered_rows:
            candidate_rows = province_filtered_rows
        else:
            log_debug(f'Trying "{guess_text}, {precision_filter}" with country code filter...')
            country_filtered_rows = [
                r for r in rows
                if (r.CountryCode or '').upper() == precision_filter
            ]
            log_debug(f'Country code matches: {len(country_filtered_rows)}')
            candidate_rows = country_filtered_rows

    for row in candidate_rows:
        city_keys = build_match_keys(row.CityName)

        if guess_keys & city_keys:
            log_debug(f'MATCH (direct): {row.CityName}')
            return {
                "type": "match",
                "row": row,
            }

    log_debug('No direct match. Trying exact phonetic...')

    confirmation_candidates = []

    for row in candidate_rows:
        city_keys = build_match_keys(row.CityName)

        direct_alt_match = False

        if getattr(row, 'AlternateNames', None):
            for alt_name in row.AlternateNames.split('|||'):
                alt_keys = build_match_keys(alt_name)

                if guess_keys & alt_keys:
                    direct_alt_match = True

                city_keys |= alt_keys

        city_phonetic_keys = {
            phonetic_key(key)
            for key in city_keys
            if len(key.replace(' ', '')) >= 3
        }

        if guess_phonetic_keys & city_phonetic_keys:

            if direct_alt_match:
                normalized_city = normalize_place_name(row.CityName)

                first_differs = (
                    normalized_guess
                    and normalized_city
                    and normalized_guess[0] != normalized_city[0]
                )

                last_differs = (
                    normalized_guess
                    and normalized_city
                    and normalized_guess[-1] != normalized_city[-1]
                )

                if first_differs or last_differs:
                    print(f'CONFIRMATION REQUIRED: {guess_text} -> {row.CityName}')

                    confirmation_candidates.append({
                        "city_id": int(row.CityId),
                        "city": row.CityName,
                        "country_code": row.CountryCode,
                    })

                    continue

            print(f'MATCH (phonetic): {row.CityName}')

            return {
                "type": "match",
                "row": row,
            }

    if confirmation_candidates:
        return {
            "type": "confirmation_required",
            "suggestions": confirmation_candidates,
        }

    print('REJECTED')
    return {
        "type": "no_match",
    }