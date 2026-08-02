from dataclasses import dataclass

import pytest

from app.core.matching import find_matching_city


@dataclass
class CityRow:
    CityId: int
    CityName: str
    CountryCode: str = 'US'
    AlternateNames: str = ''
    ProvinceCodes: str = ''


@dataclass
class NearbyCity:
    CityId: int
    CityName: str
    CountryCode: str
    Latitude: float
    Longitude: float
    Population: int
    NotorietyScore: float
    ExpansionLevel: int


def test_single_exact_match_is_auto_accepted():
    result = find_matching_city(
        [CityRow(1, 'Austin')],
        'Austin',
        nearby_exact_match=None,
        current_expansion_level=0,
    )

    assert result['type'] == 'match'
    assert result['row'].CityName == 'Austin'


def test_missing_diacritics_is_treated_as_exact():
    result = find_matching_city(
        [CityRow(1, 'San José')],
        'San Jose',
        nearby_exact_match=None,
        current_expansion_level=0,
    )

    assert result['type'] == 'match'
    assert result['row'].CityName == 'San José'


def test_multiple_survivors_require_confirmation_even_when_both_auto_accept():
    result = find_matching_city(
        [CityRow(1, 'Kailua'), CityRow(2, 'Kailua-Kona')],
        'Kailua',
        nearby_exact_match=None,
        current_expansion_level=0,
    )

    assert result == {
        'type': 'confirmation_required',
        'suggestions': [
            {'city_id': 1, 'city': 'Kailua', 'country_code': 'US'},
            {'city_id': 2, 'city': 'Kailua-Kona', 'country_code': 'US'},
        ],
    }


def test_single_phonetic_spelling_requires_confirmation():
    result = find_matching_city(
        [CityRow(1, 'Sebu')],
        'Cebu',
        nearby_exact_match=None,
        current_expansion_level=0,
    )

    assert result == {
        'type': 'confirmation_required',
        'suggestions': [
            {'city_id': 1, 'city': 'Sebu', 'country_code': 'US'},
        ],
    }


@pytest.mark.parametrize(
    ('guess', 'candidate'),
    [
        ('Cebu', 'Lake Sebu'),
        ('York', 'New York'),
    ],
)
def test_unmatched_leading_word_is_not_a_plausible_match(guess, candidate):
    result = find_matching_city(
        [CityRow(1, candidate)],
        guess,
        nearby_exact_match=None,
        current_expansion_level=0,
    )

    assert result == {'type': 'no_match'}


def test_trailing_name_expansion_can_be_auto_accepted():
    result = find_matching_city(
        [CityRow(1, 'Kailua-Kona')],
        'Kailua',
        nearby_exact_match=None,
        current_expansion_level=0,
    )

    assert result['type'] == 'match'
    assert result['row'].CityName == 'Kailua-Kona'


def test_weaker_trailing_name_expansion_requires_confirmation():
    result = find_matching_city(
        [CityRow(1, 'Rostov-on-Don', 'RU')],
        'Rostov',
        nearby_exact_match=None,
        current_expansion_level=0,
    )

    assert result == {
        'type': 'confirmation_required',
        'suggestions': [
            {'city_id': 1, 'city': 'Rostov-on-Don', 'country_code': 'RU'},
        ],
    }


def test_discarded_candidate_is_not_shown_with_a_viable_candidate():
    result = find_matching_city(
        [CityRow(1, 'Lake Sebu', 'PH'), CityRow(2, 'Sebu', 'PH')],
        'Cebu',
        nearby_exact_match=None,
        current_expansion_level=0,
    )

    assert result == {
        'type': 'confirmation_required',
        'suggestions': [
            {'city_id': 2, 'city': 'Sebu', 'country_code': 'PH'},
        ],
    }


def test_confirmation_suggestions_are_alphabetical():
    result = find_matching_city(
        [CityRow(1, 'Rostov-on-Don', 'RU'), CityRow(2, 'Rostov', 'US')],
        'Rostov',
        nearby_exact_match=None,
        current_expansion_level=0,
    )

    assert [suggestion['city'] for suggestion in result['suggestions']] == [
        'Rostov',
        'Rostov-on-Don',
    ]


def test_alternate_name_uses_its_best_score():
    result = find_matching_city(
        [CityRow(1, 'Rostov-on-Don', 'RU', AlternateNames='Rostov')],
        'Rostov',
        nearby_exact_match=None,
        current_expansion_level=0,
    )

    assert result['type'] == 'match'
    assert result['row'].CityName == 'Rostov-on-Don'


def test_connector_does_not_consume_substantive_alternate_name_token():
    result = find_matching_city(
        [CityRow(1, 'Haikou', 'CN', AlternateNames='Hoi Hao')],
        'Hoi An',
        nearby_exact_match=None,
        current_expansion_level=0,
    )

    assert result == {'type': 'no_match'}


def test_fuzzy_alternate_name_receives_additional_penalty():
    result = find_matching_city(
        [
            CityRow(
                1,
                'Chak One Hundred Twenty Nine Left',
                'PK',
                AlternateNames='Kamīr',
            )
        ],
        'Kashmir',
        nearby_exact_match=None,
        current_expansion_level=0,
    )

    assert result == {'type': 'no_match'}


def test_cardinal_direction_name_requires_exact_full_name():
    result = find_matching_city(
        [CityRow(1, 'West Odessa', 'US')],
        'West',
        nearby_exact_match=None,
        current_expansion_level=0,
    )

    assert result == {'type': 'no_match'}


def test_single_word_cardinal_direction_name_still_matches_exactly():
    result = find_matching_city(
        [CityRow(1, 'West', 'US')],
        'West',
        nearby_exact_match=None,
        current_expansion_level=0,
    )

    assert result['type'] == 'match'
    assert result['row'].CityName == 'West'


@pytest.mark.parametrize(
    ('guess', 'candidate'),
    [
        ('New', 'New York'),
        ('Old', 'Old Harbour'),
        ('Upper', 'Upper Hutt'),
        ('Lower', 'Lower Hutt'),
        ('Greater', 'Greater Sudbury'),
        ('Central', 'Central City'),
        ('Nuevo', 'Nuevo Laredo'),
        ('Nova', 'Nova Friburgo'),
    ],
)
def test_generic_descriptor_requires_exact_full_name(guess, candidate):
    result = find_matching_city(
        [CityRow(1, candidate)],
        guess,
        nearby_exact_match=None,
        current_expansion_level=0,
    )

    assert result == {'type': 'no_match'}


@pytest.mark.parametrize('city', ['New York', 'Upper Hutt', 'Nova Friburgo'])
def test_full_name_with_generic_descriptor_still_matches_exactly(city):
    result = find_matching_city(
        [CityRow(1, city)],
        city,
        nearby_exact_match=None,
        current_expansion_level=0,
    )

    assert result['type'] == 'match'
    assert result['row'].CityName == city


def test_country_qualifier_filters_candidates_before_scoring():
    result = find_matching_city(
        [CityRow(1, 'Springfield', 'US'), CityRow(2, 'Springfield', 'CA')],
        'Springfield, CA',
        nearby_exact_match=None,
        current_expansion_level=0,
    )

    assert result['type'] == 'match'
    assert result['row'].CountryCode == 'CA'


def test_prominent_exact_match_in_next_expansion_eliminates_borderline_fuzzy_matches():
    nearby_omsk = NearbyCity(
        CityId=10,
        CityName='Omsk',
        CountryCode='RU',
        Latitude=54.99,
        Longitude=73.37,
        Population=1_100_000,
        NotorietyScore=95.0,
        ExpansionLevel=1,
    )

    result = find_matching_city(
        [
            CityRow(1, 'Tomsk', 'RU'),
            CityRow(2, 'Seversk', 'RU', AlternateNames='Tomsk-7'),
        ],
        'Omsk',
        nearby_exact_match=nearby_omsk,
        current_expansion_level=0,
    )

    assert result == {
        'type': 'no_match',
        'nearby_exact_match': nearby_omsk,
    }


def test_weak_exact_match_multiple_expansions_away_preserves_fuzzy_confirmation():
    distant_cebu = NearbyCity(
        CityId=10,
        CityName='Cebu',
        CountryCode='PH',
        Latitude=10.31,
        Longitude=123.89,
        Population=20_000,
        NotorietyScore=10.0,
        ExpansionLevel=3,
    )

    result = find_matching_city(
        [CityRow(1, 'Sebu', 'PH')],
        'Cebu',
        nearby_exact_match=distant_cebu,
        current_expansion_level=0,
    )

    assert result == {
        'type': 'confirmation_required',
        'suggestions': [
            {'city_id': 1, 'city': 'Sebu', 'country_code': 'PH'},
        ],
        'nearby_exact_match': distant_cebu,
    }


def test_nearby_exact_match_does_not_penalize_exact_in_square_match():
    nearby_omsk = NearbyCity(
        CityId=10,
        CityName='Omsk',
        CountryCode='RU',
        Latitude=54.99,
        Longitude=73.37,
        Population=1_100_000,
        NotorietyScore=95.0,
        ExpansionLevel=1,
    )

    result = find_matching_city(
        [CityRow(1, 'Omsk', 'RU')],
        'Omsk',
        nearby_exact_match=nearby_omsk,
        current_expansion_level=0,
    )

    assert result['type'] == 'match'
    assert result['row'].CityName == 'Omsk'