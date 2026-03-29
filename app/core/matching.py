import difflib

from app.helpers.text import build_match_keys, normalize_place_name


def phonetic_key(text: str) -> str:
    text = normalize_place_name(text).replace(' ', '')
    if not text:
        return ''

    first = text[0]
    tail = text[1:]

    tail = (
        tail.replace('ph', 'f')
            .replace('ck', 'k')
            .replace('qu', 'k')
            .replace('x', 'ks')
            .replace('z', 's')
    )

    chars = [first]
    i = 0
    while i < len(tail):
        c = tail[i]

        if c in 'aeiouyhw':
            i += 1
            continue

        if c == 'c':
            nxt = tail[i + 1] if i + 1 < len(tail) else ''
            chars.append('s' if nxt in 'iey' else 'k')
            i += 1
            continue

        if c == 'g':
            nxt = tail[i + 1] if i + 1 < len(tail) else ''
            chars.append('j' if nxt in 'iey' else 'g')
            i += 1
            continue

        if c == 'q':
            chars.append('k')
            i += 1
            continue

        chars.append(c)
        i += 1

    result = []
    prev = None
    for c in chars:
        if c != prev:
            result.append(c)
        prev = c

    return ''.join(result)


def find_matching_city(rows, guess_text: str):
    guess_keys = build_match_keys(guess_text)
    normalized_guess = normalize_place_name(guess_text)

    if 'city' not in normalized_guess.split():
        guess_keys.add(f'{normalized_guess} city')
        guess_keys.add(f'{normalized_guess}city')

    guess_compact = normalized_guess.replace(' ', '')
    guess_phonetic = phonetic_key(guess_text)

    print(f'\n=== GUESS: {guess_text}')
    print(f'Normalized: {normalized_guess}')
    print(f'Keys: {guess_keys}')
    print(f'Phonetic: {guess_phonetic}')

    for row in rows:
        city_keys = build_match_keys(row.CityName)
        print(f'CITY: {row.CityName} -> {city_keys}')
        if guess_keys & city_keys:
            print(f'MATCH (direct): {row.CityName}')
            return row

    print('No direct match. Trying fuzzy...')

    best_row = None
    best_score = 0.0

    for row in rows:
        city_keys = build_match_keys(row.CityName)

        for key in city_keys:
            city_compact = key.replace(' ', '')
            city_phonetic = phonetic_key(key)

            exact_phonetic = guess_phonetic and guess_phonetic == city_phonetic

            fuzzy_score = difflib.SequenceMatcher(
                None,
                guess_compact,
                city_compact,
            ).ratio()

            if exact_phonetic:
                compact_len_gap = abs(len(guess_compact) - len(city_compact))
                compact_prefix = 0
                for a, b in zip(guess_compact, city_compact):
                    if a != b:
                        break
                    compact_prefix += 1

                if fuzzy_score >= 0.86 and compact_len_gap <= 1 and compact_prefix >= 3:
                    score = 1.0
                else:
                    score = fuzzy_score
            else:
                score = fuzzy_score

            if score > best_score:
                best_score = score
                best_row = row

    if best_row:
        print(f'Best fuzzy match: {best_row.CityName} ({best_score:.3f})')

    if best_score >= 0.88:
        print('ACCEPTED (fuzzy)')
        return best_row

    print('REJECTED')
    return None