from functools import lru_cache
import logging

from rapidfuzz import fuzz

from app.core.country_names import get_country_name
from app.helpers.text import normalize_place_name


AUTO_ACCEPT_SCORE = 95.0
FUZZY_LINE_SCORE = 88.5
PHONETIC_TOKEN_SCORE = 92.0
FUZZY_ALTERNATE_NAME_PENALTY = 7.5
UNMATCHED_LEADING_TOKEN_PENALTY = 30.0
UNMATCHED_INTERIOR_TOKEN_PENALTY = 20.0
UNMATCHED_TRAILING_TOKEN_PENALTY = 5.0
ADDITIONAL_UNMATCHED_TRAILING_TOKEN_PENALTY = 15.0
UNMATCHED_INPUT_TOKEN_PENALTY = 30.0
NEARBY_FIRST_RING_PENALTY = 15.0
NEARBY_RING_PENALTY_DECAY = 5.0
NEARBY_NOTORIETY_SCALE = 10.0
NAME_DESCRIPTOR_WEIGHT = 0.5
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
    'sotto', 'sous', 'sulla', 'sur', 'ta', 'te', 'ten', 'ter', 'the',
    'til', 'till', 'to', 'tot', 'u', 'unter', 'upon', 'v', 'van',
    've', 'ved', 'vom', 'von', 'w', 'wa', 'with', 'y', 'ya', 'yn', 'yr',
    'z', 'za', 'ze', 'zu', 'zum', 'zur',
}
NAME_DESCRIPTOR_WORDS = {
    'alt', 'alta', 'alte', 'alto', 'ancient', 'bas', 'basse', 'bay', 'beach',
    'beneden', 'big', 'boven', 'central', 'centrale', 'centre', 'centro',
    'centrum', 'city', 'dolna', 'dolni', 'donja', 'donje', 'donji', 'east',
    'eastern', 'eski', 'este', 'falls', 'fort', 'gammel', 'gamla', 'gorni',
    'gornja', 'gornje', 'gornji', 'grand', 'grande', 'great', 'greater',
    'groot', 'grote', 'harbor', 'harbour', 'haut', 'haute', 'heights', 'high',
    'horni', 'inferior', 'inner', 'island', 'isle', 'klein', 'kleine', 'lake',
    'lesser', 'little', 'low', 'lower', 'major', 'mala', 'male', 'mali',
    'middle', 'minor', 'modern', 'mount', 'mountain', 'neu', 'neuf',
    'neuve', 'new', 'nieuw', 'nieuwe', 'nord', 'norr', 'norra', 'norte',
    'north', 'northern', 'nou', 'noua', 'nouveau', 'nouvel', 'nouvelle',
    'nova', 'nove', 'novi', 'novo', 'novy', 'nueva', 'nuevo', 'nuova',
    'nuovo', 'ny', 'nye', 'old', 'oude', 'outer', 'ouest', 'oost', 'ost',
    'oeste', 'port', 'river', 'san', 'sant', 'santa', 'sante', 'santi',
    'santo', 'sao', 'saint', 'sainte', 'sankt', 'sankta', 'sint', 'small',
    'south', 'southern', 'springs', 'st', 'stara', 'stare', 'stari', 'stary',
    'ste', 'sud', 'sul', 'superior', 'sur', 'upper', 'valley', 'veche',
    'vechi', 'vest', 'west', 'western', 'wielka', 'wielki', 'yeni',
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
    guess_phonetic = phonetic_key(guess_token)
    candidate_phonetic = phonetic_key(candidate_token)
    same_written_opening = guess_token[0] == candidate_token[0]
    same_phonetic_opening = (
        bool(guess_phonetic)
        and bool(candidate_phonetic)
        and guess_phonetic[0] == candidate_phonetic[0]
    )

    if not same_written_opening and not same_phonetic_opening:
        return 0.0

    spelling_score = fuzz.ratio(guess_token, candidate_token)

    if guess_phonetic and guess_phonetic == candidate_phonetic:
        return max(spelling_score, PHONETIC_TOKEN_SCORE)

    return spelling_score


def _substantive_tokens(tokens: list[str]) -> list[str]:
    return [
        token for token in tokens
        if token not in NAME_CONNECTOR_WORDS
        and token not in NAME_DESCRIPTOR_WORDS
    ]


def _token_weight(token: str) -> float:
    if token in NAME_CONNECTOR_WORDS:
        return 0.0
    if token in NAME_DESCRIPTOR_WORDS:
        return NAME_DESCRIPTOR_WEIGHT
    return 1.0


def _trailing_token_penalty(tokens: list[str]) -> float:
    substantive_count = sum(token not in NAME_CONNECTOR_WORDS for token in tokens)
    if substantive_count == 0:
        return 0.0
    return (
        UNMATCHED_TRAILING_TOKEN_PENALTY
        + ((substantive_count - 1) * ADDITIONAL_UNMATCHED_TRAILING_TOKEN_PENALTY)
    )


def _score_name_pair(guess_name: str, candidate_name: str) -> float:
    guess_tokens = normalize_place_name(guess_name).split()
    candidate_tokens = normalize_place_name(candidate_name).split()

    if not guess_tokens or not candidate_tokens:
        return 0.0

    guess_substantive_tokens = _substantive_tokens(guess_tokens)
    candidate_substantive_tokens = _substantive_tokens(candidate_tokens)

    if not guess_substantive_tokens or not candidate_substantive_tokens:
        return 100.0 if guess_tokens == candidate_tokens else 0.0

    if (
        _token_similarity(
            guess_substantive_tokens[0],
            candidate_substantive_tokens[0],
        ) < FUZZY_LINE_SCORE
    ):
        return 0.0

    guess_token_weight = sum(_token_weight(token) for token in guess_tokens)

    @lru_cache(maxsize=None)
    def align(
        guess_index: int,
        candidate_index: int,
        match_started: bool,
        pending_candidate_tokens: int,
    ) -> float:
        if guess_index == len(guess_tokens):
            trailing_tokens = candidate_tokens[
                candidate_index - pending_candidate_tokens:
            ]
            return -_trailing_token_penalty(trailing_tokens)

        if candidate_index == len(candidate_tokens):
            pending_tokens = candidate_tokens[
                candidate_index - pending_candidate_tokens:
            ]
            remaining_input_count = len(guess_tokens) - guess_index
            return (
                -_trailing_token_penalty(pending_tokens)
                -(remaining_input_count * UNMATCHED_INPUT_TOKEN_PENALTY)
            )

        similarity = (
            _token_similarity(
                guess_tokens[guess_index],
                candidate_tokens[candidate_index],
            )
            * _token_weight(guess_tokens[guess_index])
            / guess_token_weight
        )

        pending_penalty = (
            pending_candidate_tokens * UNMATCHED_INTERIOR_TOKEN_PENALTY
            if match_started
            else pending_candidate_tokens * UNMATCHED_LEADING_TOKEN_PENALTY
        )

        connector_consumes_substantive = (
            _token_weight(guess_tokens[guess_index]) == 0.0
            and candidate_tokens[candidate_index] in candidate_substantive_tokens
        )
        match_score = (
            float('-inf')
            if connector_consumes_substantive
            else (
                similarity
                - pending_penalty
                + align(guess_index + 1, candidate_index + 1, True, 0)
            )
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
        (normalize_place_name(row.CityName), 'canonical', row.CityName)
    ]

    if row.AlternateNames:
        for alternate_name in row.AlternateNames.split('|||'):
            options.append(
                (normalize_place_name(alternate_name), 'alternate', alternate_name)
            )

    return options


def _score_candidate(guess_name: str, row) -> tuple[float, str, str, str, str]:
    scored_options = [
        (
            score if source_type == 'canonical' or score == 100.0
            else max(0.0, score - FUZZY_ALTERNATE_NAME_PENALTY),
            guess_name,
            candidate_name,
            source_type,
            source_name,
        )
        for candidate_name, source_type, source_name in _candidate_name_options(row)
        for score in [_score_name_pair(guess_name, candidate_name)]
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
    province = next(
        (
            value.strip()
            for value in (row.ProvinceCodes or '').split(',')
            if value.strip()
        ),
        '',
    )
    if len(province) > 10:
        province = ''

    return {
        "city_id": int(row.CityId),
        "city": row.CityName,
        "country_code": row.CountryCode,
        "country_name": get_country_name(row.CountryCode),
        "province": province or None,
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

    normalized_guess = normalize_place_name(guess_text)

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
        candidate_score = _score_candidate(normalized_guess, row)
        raw_score = candidate_score[0]
        source_type = candidate_score[3]
        if raw_score == 100.0 or nearby_exact_match is None:
            score = raw_score
        else:
            score = max(0.0, raw_score - nearby_penalty)
        scored_candidates.append((score, row, source_type))

    surviving_candidates = [
        (score, row, source_type)
        for score, row, source_type in scored_candidates
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

    canonical_exact_matches = [
        candidate
        for candidate in surviving_candidates
        if candidate[0] == 100.0 and candidate[2] == 'canonical'
    ]
    if len(canonical_exact_matches) == 1:
        score, row, _source_type = canonical_exact_matches[0]
        summary_parts.append(
            f'{row.CityName}, {row.CountryCode} scored {score:.1f} as a canonical '
            'exact match and was automatically accepted.'
        )
        _logger.info('City match for %r: %s', guess_text, ' '.join(summary_parts))
        return {
            "type": "match",
            "row": row,
        }

    if (
        len(surviving_candidates) == 1
        and surviving_candidates[0][0] >= AUTO_ACCEPT_SCORE
        and surviving_candidates[0][2] == 'canonical'
    ):
        score, row, _source_type = surviving_candidates[0]
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
        for score, row, _source_type in surviving_candidates
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
            for _score, row, _source_type in surviving_candidates
        ],
    }
    if nearby_exact_match is not None:
        result["nearby_exact_match"] = nearby_exact_match
    return result