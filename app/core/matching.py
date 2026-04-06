from app.helpers.text import build_match_keys, normalize_place_name


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

    print(f'\n=== GUESS: {guess_text}')
    print(f'Precision filter: {precision_filter}')
    print(f'Normalized: {normalized_guess}')
    print(f'Keys: {guess_keys}')
    print(f'Phonetic Keys: {guess_phonetic_keys}')

    candidate_rows = rows
    if precision_filter:
        print(f'Trying "{guess_text}, {precision_filter}" with province code filter...')
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

        print(f'Province code matches: {len(province_filtered_rows)}')

        if province_filtered_rows:
            candidate_rows = province_filtered_rows
        else:
            print(f'Trying "{guess_text}, {precision_filter}" with country code filter...')
            country_filtered_rows = [
                r for r in rows
                if (r.CountryCode or '').upper() == precision_filter
            ]
            print(f'Country code matches: {len(country_filtered_rows)}')
            candidate_rows = country_filtered_rows

    for row in candidate_rows:
        city_keys = build_match_keys(row.CityName)

        if guess_keys & city_keys:
            print(f'MATCH (direct): {row.CityName}')
            return row

    print('No direct match. Trying exact phonetic...')

    for row in candidate_rows:
        city_keys = build_match_keys(row.CityName)

        if getattr(row, 'AlternateNames', None):
            for alt_name in row.AlternateNames.split('|||'):
                city_keys |= build_match_keys(alt_name)

        city_phonetic_keys = {
            phonetic_key(key)
            for key in city_keys
            if len(key.replace(' ', '')) >= 3
        }

        if guess_phonetic_keys & city_phonetic_keys:
            print(f'MATCH (phonetic): {row.CityName}')
            return row

    print('REJECTED')
    return None