from app.core.matching import find_matching_city


def resolve_city_guess(
    ranked_cities,
    *,
    guess_text: str,
    confirmed_city_id: int | None,
    nearby_exact_match,
    expansion_level: int,
) -> dict:
    if confirmed_city_id is not None:
        for city in ranked_cities:
            if int(city.CityId) == int(confirmed_city_id):
                return {'type': 'match', 'row': city}
        return {'type': 'invalid_confirmation'}

    return find_matching_city(
        ranked_cities,
        guess_text,
        nearby_exact_match=nearby_exact_match,
        current_expansion_level=expansion_level,
    )