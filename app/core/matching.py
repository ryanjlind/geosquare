import difflib

from app.helpers.text import build_match_keys, normalize_place_name


def find_matching_city(rows, guess_text: str):
    guess_keys = build_match_keys(guess_text)
    normalized_guess = normalize_place_name(guess_text)

    if 'city' not in normalized_guess.split():
        guess_keys.add(f'{normalized_guess} city')
        guess_keys.add(f'{normalized_guess}city')

    guess_compact = normalized_guess.replace(' ', '')

    print(f'\n=== GUESS: {guess_text}')
    print(f'Normalized: {normalized_guess}')
    print(f'Keys: {guess_keys}')

    for row in rows:
        print(f'CITY: {row.CityName} -> {build_match_keys(row.CityName)}')
        city_keys = build_match_keys(row.CityName)
        if guess_keys & city_keys:
            print(f'MATCH (direct): {row.CityName}')
            return row

    print('No direct match. Trying fuzzy...')

    best_row = None
    best_score = 0.0

    for row in rows:
        city_keys = build_match_keys(row.CityName)

        for key in city_keys:
            score = difflib.SequenceMatcher(
                None,
                guess_compact,
                key.replace(' ', ''),
            ).ratio()

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
