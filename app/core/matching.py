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

    country_filter = None
    if ',' in guess_text:
        parts = [p.strip() for p in guess_text.split(',', 1)]
        if len(parts) == 2:
            guess_text, country_part = parts
            country_filter = country_part.upper()

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
    print(f'Country filter: {country_filter}')
    print(f'Normalized: {normalized_guess}')
    print(f'Keys: {guess_keys}')
    print(f'Phonetic Keys: {guess_phonetic_keys}')

    candidate_rows = rows
    if country_filter:
        candidate_rows = [r for r in rows if r.CountryCode.upper() == country_filter]

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