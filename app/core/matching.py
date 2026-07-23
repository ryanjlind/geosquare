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

    if ',' in guess_text:
        parts = [p.strip() for p in guess_text.split(',', 1)]
        if len(parts) == 2:
            guess_text, precision_part = parts
            precision_filter = precision_part.upper()
        else:
            precision_filter = None
    else:
        precision_filter = None

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

    print(f'=== GUESS: {guess_text}', flush=True)
    print(f'Precision filter: {precision_filter}', flush=True)
    print(f'Normalized: {normalized_guess}', flush=True)
    print(f'Keys: {guess_keys}', flush=True)
    print(f'Phonetic keys: {guess_phonetic_keys}', flush=True)

    candidate_rows = rows
    if precision_filter:
        print(f'Trying "{guess_text}, {precision_filter}" with province code filter...', flush=True)
        province_filtered_rows = []

        for r in rows:
            province_codes_raw = r.ProvinceCodes or ''
            province_codes = {
                code.strip().upper()
                for code in province_codes_raw.split(',')
                if code.strip()
            }

            if precision_filter in province_codes:
                province_filtered_rows.append(r)

        print(f'Province code matches: {len(province_filtered_rows)}', flush=True)

        if province_filtered_rows:
            candidate_rows = province_filtered_rows
        else:
            print(f'Trying "{guess_text}, {precision_filter}" with country code filter...', flush=True)
            country_filtered_rows = [
                r for r in rows
                if (r.CountryCode or '').upper() == precision_filter
            ]
            print(f'Country code matches: {len(country_filtered_rows)}', flush=True)
            candidate_rows = country_filtered_rows

    import time as _time

    direct_match_row = None
    direct_match_index = None
    t0 = _time.perf_counter()
    for idx, row in enumerate(candidate_rows):
        city_keys = build_match_keys(row.CityName)
        if guess_keys & city_keys:
            print(f'MATCH (direct): {row.CityName} idx={idx} elapsed_ms={((_time.perf_counter()-t0)*1000):.1f}', flush=True)
            direct_match_row = row
            direct_match_index = idx
            break
    print(f'direct pass: {(_time.perf_counter()-t0)*1000:.1f}ms checked={idx+1 if direct_match_row is not None else len(candidate_rows)}', flush=True)

    if direct_match_row is not None:
        alt_conflicts = []
        t1 = _time.perf_counter()
        for row in candidate_rows[:direct_match_index]:
            raw = row.AlternateNames or ''
            for alt in raw.split('|||'):
                if normalize_place_name(alt) == normalized_guess:
                    alt_conflicts.append(row)
                    break
        print(f'alt conflict scan: {(_time.perf_counter()-t1)*1000:.1f}ms cities_checked={direct_match_index} conflicts={len(alt_conflicts)}', flush=True)
        if alt_conflicts:
            print(f'DISAMBIGUATION (alt name conflict): {[r.CityName for r in alt_conflicts]}', flush=True)
            return {
                "type": "confirmation_required",
                "suggestions": [
                    {"city_id": int(r.CityId), "city": r.CityName, "country_code": r.CountryCode}
                    for r in alt_conflicts + [direct_match_row]
                ],
            }
        return {
            "type": "match",
            "row": direct_match_row,
        }

    print('No direct match. Trying exact phonetic...', flush=True)

    confirmation_candidates = []

    for row in candidate_rows:
        city_keys = build_match_keys(row.CityName)

        direct_alt_match = False

        if row.AlternateNames:
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
                    print(f'CONFIRMATION REQUIRED: {guess_text} -> {row.CityName}', flush=True)

                    confirmation_candidates.append({
                        "city_id": int(row.CityId),
                        "city": row.CityName,
                        "country_code": row.CountryCode,
                    })

                    continue

            print(f'MATCH (phonetic): {row.CityName}', flush=True)

            return {
                "type": "match",
                "row": row,
            }

    if confirmation_candidates:
        return {
            "type": "confirmation_required",
            "suggestions": confirmation_candidates,
        }

    print('REJECTED', flush=True)
    return {
        "type": "no_match",
    }