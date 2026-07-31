from functools import lru_cache
import logging

from rapidfuzz import fuzz

from app.helpers.text import build_match_keys, normalize_place_name


AUTO_ACCEPT_SCORE = 95.0
FUZZY_LINE_SCORE = 80.0
PHONETIC_TOKEN_SCORE = 92.0
UNMATCHED_LEADING_TOKEN_PENALTY = 30.0
UNMATCHED_INTERIOR_TOKEN_PENALTY = 20.0
UNMATCHED_TRAILING_TOKEN_PENALTY = 5.0
UNMATCHED_INPUT_TOKEN_PENALTY = 30.0
NEARBY_FIRST_RING_PENALTY = 12.0
NEARBY_RING_PENALTY_DECAY = 4.0
NEARBY_NOTORIETY_SCALE = 10.0
NAME_CONNECTOR_WORDS = {
    'a', 'aan', 'af', 'ai', 'al', 'ale', 'alla', 'alle', 'am', 'an',
    'and', 'ar', 'as', 'at', 'auf', 'au', 'aux', 'av', 'az', 'bajo',
    'bei', 'bij', 'by', 'chez', 'con', 'contra', 'cu', 'd', 'da', 'dal',
    'dalla', 'das', 'de', 'dei', 'del', 'della', 'delle', 'dem', 'den',
    'der', 'des', 'di', 'die', 'din', 'do', 'dos', 'du', 'e', 'el',
    'em', 'en', 'entre', 'es', 'eta', 'et', 'for', 'from', 'het', 'i',
    'im', 'in', 'kod', 'kraj', 'l', 'la', 'langa', 'las', 'le', 'les',
    'lo', 'los', 'lui', 'na', 'nam', 'nan', 'nas', 'nad', 'near', 'nel',
    'nella', 'no', 'nos', 'ob', 'of', 'og', 'on', 'onder', 'op', 'pa',
    'pe', 'pod', 'pri', 'prie', 'przy', 'se', 'si', 'sob', 'sobre',
    'sotto', 'sous', 'sul', 'sulla', 'sur', 'ta', 'te', 'ten', 'ter',
    'the', 'til', 'till', 'to', 'tot', 'u', 'unter', 'upon', 'v', 'van',
    've', 'ved', 'vom', 'von', 'w', 'wa', 'with', 'y', 'ya', 'yn', 'yr',
    'z', 'za', 'ze', 'zu', 'zum', 'zur',
}

_logger = logging.getLogger('geosquare.matching')
_logger.setLevel(logging.INFO)


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


def _token_similarity(guess_token: str, candidate_token: str) -> float:
    spelling_score = fuzz.ratio(guess_token, candidate_token)
    guess_phonetic = phonetic_key(guess_token)
    candidate_phonetic = phonetic_key(candidate_token)

    if guess_phonetic and guess_phonetic == candidate_phonetic:
        return max(spelling_score, PHONETIC_TOKEN_SCORE)

    return spelling_score


def _substantive_tokens(tokens: list[str]) -> list[str]:
    if len(tokens) == 1:
        return tokens
    return [token for token in tokens if token not in NAME_CONNECTOR_WORDS]


def _score_name_pair(guess_name: str, candidate_name: str) -> float:
    guess_tokens = normalize_place_name(guess_name).split()
    candidate_tokens = normalize_place_name(candidate_name).split()

    if not guess_tokens or not candidate_tokens:
        return 0.0

    guess_substantive_tokens = _substantive_tokens(guess_tokens)
    candidate_substantive_tokens = _substantive_tokens(candidate_tokens)

    if (
        _token_similarity(
            guess_substantive_tokens[0],
            candidate_substantive_tokens[0],
        ) < FUZZY_LINE_SCORE
    ):
        return 0.0

    guess_token_count = len(guess_substantive_tokens)

    @lru_cache(maxsize=None)
    def align(
        guess_index: int,
        candidate_index: int,
        match_started: bool,
        pending_candidate_tokens: int,
    ) -> float:
        if guess_index == len(guess_tokens):
            trailing_count = pending_candidate_tokens + len(candidate_tokens) - candidate_index
            return -(trailing_count * UNMATCHED_TRAILING_TOKEN_PENALTY)

        if candidate_index == len(candidate_tokens):
            remaining_input_count = len(guess_tokens) - guess_index
            return (
                -(pending_candidate_tokens * UNMATCHED_TRAILING_TOKEN_PENALTY)
                -(remaining_input_count * UNMATCHED_INPUT_TOKEN_PENALTY)
            )

        if guess_tokens[guess_index] in NAME_CONNECTOR_WORDS:
            similarity = 0.0
        else:
            similarity = _token_similarity(
                guess_tokens[guess_index],
                candidate_tokens[candidate_index],
            ) / guess_token_count

        pending_penalty = (
            pending_candidate_tokens * UNMATCHED_INTERIOR_TOKEN_PENALTY
            if match_started
            else pending_candidate_tokens * UNMATCHED_LEADING_TOKEN_PENALTY
        )

        match_score = (
            similarity
            - pending_penalty
            + align(guess_index + 1, candidate_index + 1, True, 0)
        )
        skip_input_score = (
            -UNMATCHED_INPUT_TOKEN_PENALTY
            + align(guess_index + 1, candidate_index, match_started, pending_candidate_tokens)
        )
        skip_candidate_score = align(
            guess_index,
            candidate_index + 1,
            match_started,
            pending_candidate_tokens + 1,
        )

        return max(match_score, skip_input_score, skip_candidate_score)

    return max(0.0, min(100.0, align(0, 0, False, 0)))


def _candidate_name_options(row) -> list[tuple[str, str, str]]:
    options = [
        (key, 'canonical', row.CityName)
        for key in build_match_keys(row.CityName)
    ]

    if row.AlternateNames:
        for alternate_name in row.AlternateNames.split('|||'):
            options.extend(
                (key, 'alternate', alternate_name)
                for key in build_match_keys(alternate_name)
            )

    return options


def _score_candidate(guess_keys: set[str], row) -> tuple[float, str, str, str, str]:
    scored_options = [
        (
            _score_name_pair(guess_key, candidate_key),
            guess_key,
            candidate_key,
            source_type,
            source_name,
        )
        for guess_key in guess_keys
        for candidate_key, source_type, source_name in _candidate_name_options(row)
    ]

    return max(
        scored_options,
        key=lambda option: (
            option[0],
            option[3] == 'canonical',
            option[2],
        ),
    )


def _suggestion(row) -> dict:
    return {
        "city_id": int(row.CityId),
        "city": row.CityName,
        "country_code": row.CountryCode,
    }


def _nearby_intent_penalty(nearby_exact_match, current_expansion_level: int) -> float:
    rings_away = int(nearby_exact_match.ExpansionLevel) - current_expansion_level
    distance_penalty = max(
        0.0,
        NEARBY_FIRST_RING_PENALTY - ((rings_away - 1) * NEARBY_RING_PENALTY_DECAY),
    )
    notoriety_score = float(nearby_exact_match.NotorietyScore)
    return distance_penalty * (notoriety_score / NEARBY_NOTORIETY_SCALE)


def find_matching_city(
    rows,
    guess_text: str,
    *,
    nearby_exact_match,
    current_expansion_level: int,
):
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

    summary_parts = []

    if nearby_exact_match is not None:
        nearby_penalty = _nearby_intent_penalty(
            nearby_exact_match,
            current_expansion_level,
        )
        rings_away = int(nearby_exact_match.ExpansionLevel) - current_expansion_level
        summary_parts.append(
            f'Nearby exact match {nearby_exact_match.CityName} is {rings_away} '
            f'ring{"s" if rings_away != 1 else ""} away with notoriety '
            f'{float(nearby_exact_match.NotorietyScore):.2f}, applying a '
            f'{nearby_penalty:.1f} penalty to fuzzy candidates.'
        )

    candidate_rows = rows
    if precision_filter:
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

        if province_filtered_rows:
            candidate_rows = province_filtered_rows
            summary_parts.append(
                f'Province filter {precision_filter} reduced the field to '
                f'{len(candidate_rows)} candidates.'
            )
        else:
            country_filtered_rows = [
                r for r in rows
                if (r.CountryCode or '').upper() == precision_filter
            ]
            candidate_rows = country_filtered_rows
            summary_parts.append(
                f'Country filter {precision_filter} reduced the field to '
                f'{len(candidate_rows)} candidates.'
            )

    scored_candidates = []

    for row in candidate_rows:
        raw_score = _score_candidate(guess_keys, row)[0]
        if raw_score == 100.0 or nearby_exact_match is None:
            score = raw_score
        else:
            score = max(0.0, raw_score - nearby_penalty)
        scored_candidates.append((score, row))

    surviving_candidates = [
        (score, row)
        for score, row in scored_candidates
        if score >= FUZZY_LINE_SCORE
    ]
    discarded_count = len(scored_candidates) - len(surviving_candidates)

    if not surviving_candidates:
        summary_parts.append(
            f'All {discarded_count} candidates scored below {FUZZY_LINE_SCORE:.0f}, '
            'so the guess was rejected.'
        )
        _logger.info('City match for %r: %s', guess_text, ' '.join(summary_parts))
        result = {"type": "no_match"}
        if nearby_exact_match is not None:
            result["nearby_exact_match"] = nearby_exact_match
        return result

    if (
        len(surviving_candidates) == 1
        and surviving_candidates[0][0] >= AUTO_ACCEPT_SCORE
    ):
        score, row = surviving_candidates[0]
        summary_parts.append(
            f'{row.CityName}, {row.CountryCode} scored {score:.1f} and was '
            f'automatically accepted. The other {discarded_count} candidates '
            f'scored below {FUZZY_LINE_SCORE:.0f}.'
        )
        _logger.info('City match for %r: %s', guess_text, ' '.join(summary_parts))
        return {
            "type": "match",
            "row": row,
        }

    surviving_candidates.sort(
        key=lambda candidate: (
            normalize_place_name(candidate[1].CityName),
            (candidate[1].CountryCode or '').upper(),
            int(candidate[1].CityId),
        )
    )

    viable_candidates = ', '.join(
        f'{row.CityName}, {row.CountryCode} ({score:.1f})'
        for score, row in surviving_candidates
    )
    summary_parts.append(
        f'Viable candidate{"s" if len(surviving_candidates) != 1 else ""}: '
        f'{viable_candidates}. The other {discarded_count} candidates scored below '
        f'{FUZZY_LINE_SCORE:.0f}, so confirmation is required.'
    )
    _logger.info('City match for %r: %s', guess_text, ' '.join(summary_parts))

    result = {
        "type": "confirmation_required",
        "suggestions": [
            _suggestion(row)
            for _score, row in surviving_candidates
        ],
    }
    if nearby_exact_match is not None:
        result["nearby_exact_match"] = nearby_exact_match
    return result