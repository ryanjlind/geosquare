from math import asin, cos, radians, sin, sqrt

from app.core.country_names import get_country_name, get_sovereign_country_code
from app.core.side_missions.copy import MISSION_COPY
from app.core.side_missions.framework import (
	MissionProgress,
	SideMissionContext,
	SideMissionDeck,
	SideMissionDefinition,
)


NAME_CHAIN_MINIMUM_STEP_POPULATION = 150_000


class AnswerIsCapital:
	def __call__(self, context: SideMissionContext) -> bool:
		return bool(context.answer['is_capital'])


class SquareHasMultipleCapitals:
	def __call__(self, context: SideMissionContext) -> bool:
		return sum(bool(city['is_capital']) for city in context.cities) > 1


class SquareHasMultipleCountries:
	def __call__(self, context: SideMissionContext) -> bool:
		return len({
			get_sovereign_country_code(city['country_code'])
			for city in context.cities
		}) > 1


class AnswerHasExtremeValue:
	def __init__(self, field: str, extreme: str):
		self.field = field
		self.extreme = extreme

	def __call__(self, context: SideMissionContext) -> bool:
		values = [city[self.field] for city in context.cities]
		extreme_value = {
			'minimum': min,
			'maximum': max,
		}[self.extreme](values)
		return context.answer[self.field] == extreme_value


class SquareHasAtLeastCities:
	def __init__(self, count: int):
		self.count = count

	def __call__(self, context: SideMissionContext) -> bool:
		return len(context.cities) >= self.count


def _normalized_name_letters(city_name: str) -> str:
	return ''.join(character for character in city_name.casefold() if character.isalpha())


def _is_multi_word(city_name: str) -> bool:
	return len(city_name.split()) >= 2


def _distance_km(first: dict, second: dict) -> float:
	first_latitude = radians(float(first['latitude']))
	second_latitude = radians(float(second['latitude']))
	latitude_delta = second_latitude - first_latitude
	longitude_delta = radians(float(second['longitude']) - float(first['longitude']))
	haversine = (
		sin(latitude_delta / 2) ** 2
		+ cos(first_latitude) * cos(second_latitude) * sin(longitude_delta / 2) ** 2
	)
	return 6371.0 * 2 * asin(sqrt(haversine))


class AnswerStartsThreeCityNameChain:
	def __call__(self, context: SideMissionContext) -> bool:
		answer_letters = _normalized_name_letters(context.answer['city_name'])
		if not answer_letters:
			raise ValueError('Daily answer city name contains no letters.')
		available = tuple(
			city for city in context.cities
			if int(city['city_id']) != int(context.answer['city_id'])
		)
		return self._has_chain(available, answer_letters[-1], 3)

	def _has_chain(self, cities: tuple[dict, ...], required_letter: str, remaining: int) -> bool:
		if remaining == 0:
			return True
		matching_cities = tuple(
			city for city in cities
			if (letters := _normalized_name_letters(city['city_name']))
			and letters[0] == required_letter
		)
		if sum(int(city['population']) for city in matching_cities) < NAME_CHAIN_MINIMUM_STEP_POPULATION:
			return False
		for city in matching_cities:
			letters = _normalized_name_letters(city['city_name'])
			next_cities = tuple(candidate for candidate in cities if candidate is not city)
			if self._has_chain(next_cities, letters[-1], remaining - 1):
					return True
		return False


class AnswerHasTwoWordName:
	def __call__(self, context: SideMissionContext) -> bool:
		return len(context.answer['city_name'].split()) == 2


class SquareHasOtherMultiWordCity:
	def __call__(self, context: SideMissionContext) -> bool:
		return any(
			int(city['city_id']) != int(context.answer['city_id'])
			and _is_multi_word(city['city_name'])
			for city in context.cities
		)


class AnswerHasNoCityWithin100Km:
	def __call__(self, context: SideMissionContext) -> bool:
		return all(
			_distance_km(context.answer, city) >= 100
			for city in context.cities
			if int(city['city_id']) != int(context.answer['city_id'])
		)


class CapitalSweepPrompt:
	def __call__(self, context: SideMissionContext) -> str:
		other_capitals = sum(bool(city['is_capital']) for city in context.cities) - 1
		noun = 'capital' if other_capitals == 1 else 'capitals'
		return MISSION_COPY['capital_sweep']['prompt'].format(
			city_name=context.answer['city_name'],
			other_capitals=other_capitals,
			capital_noun=noun,
		)


class CapitalSweepProgress:
	def __call__(self, context: SideMissionContext) -> MissionProgress:
		cities_by_id = {
			int(city['city_id']): city
			for city in context.cities
		}
		target_ids = {
			int(city['city_id'])
			for city in context.cities
			if city['is_capital']
		}
		found_ids = context.found_city_ids & target_ids
		return MissionProgress(
			current=len(found_ids),
			target=len(target_ids),
			named=tuple(sorted(cities_by_id[city_id]['city_name'] for city_id in found_ids)),
		)


class CountryCoveragePrompt:
	def __call__(self, context: SideMissionContext) -> str:
		other_countries = len({
			get_sovereign_country_code(city['country_code'])
			for city in context.cities
		}) - 1
		noun = 'country' if other_countries == 1 else 'countries'
		country_name = get_country_name(
			get_sovereign_country_code(context.answer['country_code'])
		).upper()
		return MISSION_COPY['country_coverage']['prompt'].format(
			country_name=country_name,
			other_countries=other_countries,
			country_noun=noun,
		)


class CountryCoverageProgress:
	def __call__(self, context: SideMissionContext) -> MissionProgress:
		cities_by_id = {
			int(city['city_id']): city
			for city in context.cities
		}
		target_countries = {
			get_sovereign_country_code(city['country_code'])
			for city in context.cities
		}
		found_countries = {
			get_sovereign_country_code(cities_by_id[city_id]['country_code'])
			for city_id in context.found_city_ids
			if city_id in cities_by_id
		}
		return MissionProgress(
			current=len(found_countries),
			target=len(target_countries),
			named=tuple(sorted(get_country_name(code) for code in found_countries)),
		)


class OppositeExtremePrompt:
	def __init__(self, mission_id: str):
		self.mission_id = mission_id

	def __call__(self, context: SideMissionContext) -> str:
		return MISSION_COPY[self.mission_id]['prompt'].format(
			city_name=context.answer['city_name'],
		)


class ExtremeCityProgress:
	def __init__(self, field: str, extreme: str):
		self.field = field
		self.extreme = extreme

	def __call__(self, context: SideMissionContext) -> MissionProgress:
		values = [city[self.field] for city in context.cities]
		target_value = {
			'minimum': min,
			'maximum': max,
		}[self.extreme](values)
		target_ids = {
			int(city['city_id'])
			for city in context.cities
			if city[self.field] == target_value
		}
		found_ids = context.found_city_ids & target_ids
		cities_by_id = {
			int(city['city_id']): city
			for city in context.cities
		}
		return MissionProgress(
			current=len(found_ids),
			target=len(target_ids),
			named=tuple(sorted(cities_by_id[city_id]['city_name'] for city_id in found_ids)),
		)


class SmallestToLargestPrompt:
	def __call__(self, context: SideMissionContext) -> str:
		return MISSION_COPY['smallest_to_largest']['prompt'].format(
			city_name=context.answer['city_name'],
		)


class ThreeLargestCitiesProgress:
	def __call__(self, context: SideMissionContext) -> MissionProgress:
		target_cities = sorted(
			context.cities,
			key=lambda city: (-int(city['population']), int(city['city_id'])),
		)[:3]
		target_ids = {int(city['city_id']) for city in target_cities}
		found_ids = context.found_city_ids & target_ids
		cities_by_id = {
			int(city['city_id']): city
			for city in target_cities
		}
		return MissionProgress(
			current=len(found_ids),
			target=len(target_ids),
			named=tuple(sorted(cities_by_id[city_id]['city_name'] for city_id in found_ids)),
		)


class NameChainPrompt:
	def __call__(self, context: SideMissionContext) -> str:
		letters = _normalized_name_letters(context.answer['city_name'])
		return MISSION_COPY['name_chain']['prompt'].format(
			city_name=context.answer['city_name'],
			required_letter=letters[-1].upper(),
		)


class ThreeCityNameChainProgress:
	def __call__(self, context: SideMissionContext) -> MissionProgress:
		cities_by_id = {
			int(city['city_id']): city
			for city in context.cities
		}
		answer_letters = _normalized_name_letters(context.answer['city_name'])
		required_letter = answer_letters[-1]
		named = []
		for guess in context.guesses:
			city = cities_by_id[int(guess['city_id'])]
			letters = _normalized_name_letters(city['city_name'])
			if len(named) < 3 and letters and letters[0] == required_letter:
				named.append(city['city_name'])
				required_letter = letters[-1]
		return MissionProgress(current=len(named), target=3, named=tuple(named))


class MultiWordCitiesPrompt:
	def __call__(self, context: SideMissionContext) -> str:
		return MISSION_COPY['multi_word_sweep']['prompt'].format(
			city_name=context.answer['city_name'],
		)


class OtherMultiWordCitiesProgress:
	def __call__(self, context: SideMissionContext) -> MissionProgress:
		target_cities = {
			int(city['city_id']): city
			for city in context.cities
			if int(city['city_id']) != int(context.answer['city_id'])
			and _is_multi_word(city['city_name'])
		}
		found_ids = context.found_city_ids & target_cities.keys()
		return MissionProgress(
			current=len(found_ids),
			target=len(target_cities),
			named=tuple(sorted(target_cities[city_id]['city_name'] for city_id in found_ids)),
		)


class IsolatedCityPrompt:
	def __call__(self, context: SideMissionContext) -> str:
		return MISSION_COPY['isolated_neighbors']['prompt'].format(
			city_name=context.answer['city_name'],
		)


class ThreeNearestNeighborsProgress:
	def __call__(self, context: SideMissionContext) -> MissionProgress:
		target_cities = sorted(
			(
				city for city in context.cities
				if int(city['city_id']) != int(context.answer['city_id'])
			),
			key=lambda city: (
				_distance_km(context.answer, city),
				int(city['city_id']),
			),
		)[:3]
		targets_by_id = {int(city['city_id']): city for city in target_cities}
		found_ids = context.found_city_ids & targets_by_id.keys()
		return MissionProgress(
			current=len(found_ids),
			target=len(targets_by_id),
			named=tuple(sorted(targets_by_id[city_id]['city_name'] for city_id in found_ids)),
		)


class DiscoveredAcknowledgement:
	def __call__(self, target_name: str) -> str:
		return f'{target_name.upper()} DISCOVERED'


ELIGIBILITY_SCENARIOS = {
	'answer_is_capital': AnswerIsCapital(),
	'square_has_multiple_capitals': SquareHasMultipleCapitals(),
	'square_has_multiple_countries': SquareHasMultipleCountries(),
	'answer_is_northernmost': AnswerHasExtremeValue('latitude', 'maximum'),
	'answer_is_southernmost': AnswerHasExtremeValue('latitude', 'minimum'),
	'answer_is_easternmost': AnswerHasExtremeValue('longitude', 'maximum'),
	'answer_is_westernmost': AnswerHasExtremeValue('longitude', 'minimum'),
	'answer_is_smallest': AnswerHasExtremeValue('population', 'minimum'),
	'square_has_four_cities': SquareHasAtLeastCities(4),
	'answer_starts_three_city_name_chain': AnswerStartsThreeCityNameChain(),
	'answer_has_two_word_name': AnswerHasTwoWordName(),
	'square_has_other_multi_word_city': SquareHasOtherMultiWordCity(),
	'answer_has_no_city_within_100_km': AnswerHasNoCityWithin100Km(),
}


MISSIONS = {
	'capital_sweep': SideMissionDefinition(
		mission_id='capital_sweep',
		name=MISSION_COPY['capital_sweep']['name'],
		build_prompt=CapitalSweepPrompt(),
		calculate_progress=CapitalSweepProgress(),
		build_acknowledgement=DiscoveredAcknowledgement(),
	),
	'country_coverage': SideMissionDefinition(
		mission_id='country_coverage',
		name=MISSION_COPY['country_coverage']['name'],
		build_prompt=CountryCoveragePrompt(),
		calculate_progress=CountryCoverageProgress(),
		build_acknowledgement=DiscoveredAcknowledgement(),
	),
	'north_to_south': SideMissionDefinition(
		mission_id='north_to_south',
		name=MISSION_COPY['north_to_south']['name'],
		build_prompt=OppositeExtremePrompt('north_to_south'),
		calculate_progress=ExtremeCityProgress('latitude', 'minimum'),
		build_acknowledgement=DiscoveredAcknowledgement(),
	),
	'south_to_north': SideMissionDefinition(
		mission_id='south_to_north',
		name=MISSION_COPY['south_to_north']['name'],
		build_prompt=OppositeExtremePrompt('south_to_north'),
		calculate_progress=ExtremeCityProgress('latitude', 'maximum'),
		build_acknowledgement=DiscoveredAcknowledgement(),
	),
	'east_to_west': SideMissionDefinition(
		mission_id='east_to_west',
		name=MISSION_COPY['east_to_west']['name'],
		build_prompt=OppositeExtremePrompt('east_to_west'),
		calculate_progress=ExtremeCityProgress('longitude', 'minimum'),
		build_acknowledgement=DiscoveredAcknowledgement(),
	),
	'west_to_east': SideMissionDefinition(
		mission_id='west_to_east',
		name=MISSION_COPY['west_to_east']['name'],
		build_prompt=OppositeExtremePrompt('west_to_east'),
		calculate_progress=ExtremeCityProgress('longitude', 'maximum'),
		build_acknowledgement=DiscoveredAcknowledgement(),
	),
	'smallest_to_largest': SideMissionDefinition(
		mission_id='smallest_to_largest',
		name=MISSION_COPY['smallest_to_largest']['name'],
		build_prompt=SmallestToLargestPrompt(),
		calculate_progress=ThreeLargestCitiesProgress(),
		build_acknowledgement=DiscoveredAcknowledgement(),
	),
	'name_chain': SideMissionDefinition(
		mission_id='name_chain',
		name=MISSION_COPY['name_chain']['name'],
		build_prompt=NameChainPrompt(),
		calculate_progress=ThreeCityNameChainProgress(),
		build_acknowledgement=DiscoveredAcknowledgement(),
	),
	'multi_word_sweep': SideMissionDefinition(
		mission_id='multi_word_sweep',
		name=MISSION_COPY['multi_word_sweep']['name'],
		build_prompt=MultiWordCitiesPrompt(),
		calculate_progress=OtherMultiWordCitiesProgress(),
		build_acknowledgement=DiscoveredAcknowledgement(),
	),
	'isolated_neighbors': SideMissionDefinition(
		mission_id='isolated_neighbors',
		name=MISSION_COPY['isolated_neighbors']['name'],
		build_prompt=IsolatedCityPrompt(),
		calculate_progress=ThreeNearestNeighborsProgress(),
		build_acknowledgement=DiscoveredAcknowledgement(),
	),
}


MISSION_ELIGIBILITY = {
	'capital_sweep': (
		'answer_is_capital',
		'square_has_multiple_capitals',
	),
	'country_coverage': (
		'square_has_multiple_countries',
	),
	'north_to_south': (
		'answer_is_northernmost',
	),
	'south_to_north': (
		'answer_is_southernmost',
	),
	'east_to_west': (
		'answer_is_easternmost',
	),
	'west_to_east': (
		'answer_is_westernmost',
	),
	'smallest_to_largest': (
		'answer_is_smallest',
		'square_has_four_cities',
	),
	'name_chain': (
		'answer_starts_three_city_name_chain',
	),
	'multi_word_sweep': (
		'answer_has_two_word_name',
		'square_has_other_multi_word_city',
	),
	'isolated_neighbors': (
		'answer_has_no_city_within_100_km',
		'square_has_four_cities',
	),
}


SIDE_MISSION_DECK = SideMissionDeck(
	eligibility_scenarios=ELIGIBILITY_SCENARIOS,
	missions=MISSIONS,
	mission_eligibility=MISSION_ELIGIBILITY,
)
