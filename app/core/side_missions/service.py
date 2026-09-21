import os
import random
from time import perf_counter
from types import SimpleNamespace

from app.constants import GAME_ROUND_COUNT as ROUND_COUNT
from app.core.db import get_conn
from app.core.logging import get_logger
from app.core.game_mappers import map_completed_rounds, map_square
from app.core.game_queries import (
	get_base_square_id_for_round,
	get_completed_round_rows,
	get_square_by_id,
	get_square_cities,
)
from app.core.infinity_queries import (
	create_infinity_session,
	get_infinity_guesses,
	get_infinity_session,
	update_current_round,
)
from app.core.session_service import get_current_session
from app.core.side_missions.deck import SIDE_MISSION_DECK
from app.core.side_missions.framework import SideMissionContext
from app.core.side_missions.queries import (
	complete_side_mission_round,
	get_side_mission_round,
	get_side_mission_rounds,
	insert_side_mission_round,
)


_logger = get_logger('geosquare.side_missions')


def _round_ineligibility_reasons(round_data: dict) -> list[str]:
	reasons = []
	if round_data['round_status'] != 'Completed':
		reasons.append(f'status is {round_data["round_status"]}')
	if not round_data['guesses']:
		reasons.append('round was not solved')
	if int(round_data['expansion_level']) != 0:
		reasons.append(f'expansion level is {round_data["expansion_level"]}')
	return reasons


def _e2e_mission_assignments() -> dict[int, str] | None:
	if os.environ.get('DATABASE_TARGET') != 'e2e':
		return None
	if 'E2E_SIDE_MISSION_ASSIGNMENTS' not in os.environ:
		raise RuntimeError(
			'E2E_SIDE_MISSION_ASSIGNMENTS is required when starting Side Missions '
			'against the E2E database.'
		)
	raw_assignments = os.environ['E2E_SIDE_MISSION_ASSIGNMENTS'].strip()
	if not raw_assignments:
		raise ValueError('E2E_SIDE_MISSION_ASSIGNMENTS must not be empty.')
	assignments = {}
	for assignment in raw_assignments.split(','):
		parts = assignment.split(':')
		if len(parts) != 2:
			raise ValueError(
				'E2E_SIDE_MISSION_ASSIGNMENTS must use round:mission_id entries.'
			)
		round_number = int(parts[0])
		mission_id = parts[1]
		if round_number in assignments:
			raise ValueError(f'Duplicate E2E Side Mission round: {round_number}.')
		if mission_id not in SIDE_MISSION_DECK.missions:
			raise ValueError(f'Unknown E2E Side Mission: {mission_id}.')
		assignments[round_number] = mission_id
	return assignments


def _load_daily_rounds(cur, session_id: int) -> list[dict]:
	return map_completed_rounds(get_completed_round_rows(cur, session_id))


def _load_base_square(cur, game_id: int, round_number: int) -> dict:
	square_id = get_base_square_id_for_round(cur, game_id, round_number)
	if square_id is None:
		raise LookupError(f'No base square found for round {round_number}.')
	cities = get_square_cities(cur, square_id)
	return map_square(
		get_square_by_id(cur, square_id),
		cities,
		SimpleNamespace(TotalCityCount=len(cities)),
		False,
	)


def _answer_for_round(completed_round: dict, square: dict) -> dict:
	if len(completed_round['guesses']) != 1:
		raise ValueError('A side-mission round requires exactly one daily answer.')
	answer_id = int(completed_round['guesses'][0]['city_id'])
	for city in square['cities']:
		if int(city['city_id']) == answer_id:
			return city
	raise LookupError(f'Daily answer city {answer_id} is not in the base square.')


def _guesses_by_round(rows) -> dict[int, tuple[dict, ...]]:
	guesses = {round_number: [] for round_number in range(1, ROUND_COUNT + 1)}
	for row in rows:
		guesses[int(row.RoundNumber)].append({'city_id': int(row.CityId)})
	return {
		round_number: tuple(round_guesses)
		for round_number, round_guesses in guesses.items()
	}


def _context_for_round(
	cur,
	game_id: int,
	completed_round: dict,
	guesses: tuple[dict, ...],
) -> SideMissionContext:
	square = _load_base_square(cur, game_id, int(completed_round['round_number']))
	return SideMissionContext(
		answer=_answer_for_round(completed_round, square),
		cities=tuple(square['cities']),
		guesses=guesses,
	)


def _load_round_contexts(
	cur,
	game_id: int,
	completed_rounds: list[dict],
	guesses_by_round: dict[int, tuple[dict, ...]],
) -> dict[int, SideMissionContext]:
	return {
		int(completed_round['round_number']): _context_for_round(
			cur,
			game_id,
			completed_round,
			guesses_by_round[int(completed_round['round_number'])],
		)
		for completed_round in completed_rounds
		if not _round_ineligibility_reasons(completed_round)
	}


def _availability_precheck_reasons(daily_session, completed_rounds: list[dict]) -> list[str]:
	reasons = []
	if daily_session.CompletedAt is None:
		reasons.append('daily game is incomplete')
	if len(completed_rounds) != ROUND_COUNT:
		reasons.append(f'completed round count is {len(completed_rounds)}, expected {ROUND_COUNT}')
	return reasons


def _evaluate_side_mission_availability(
	daily_session,
	completed_rounds: list[dict],
	contexts_by_round: dict[int, SideMissionContext],
	started: bool,
) -> dict:
	started_at = perf_counter()
	session_id = int(daily_session.SessionId)
	game_id = int(daily_session.GameId)
	_logger.info(
		'side_mission_availability: started session_id=%s game_id=%s completed_round_count=%s',
		session_id,
		game_id,
		len(completed_rounds),
	)
	reasons = _availability_precheck_reasons(daily_session, completed_rounds)

	eligible_rounds = []
	if not reasons:
		for completed_round in completed_rounds:
			round_number = int(completed_round['round_number'])
			round_reasons = _round_ineligibility_reasons(completed_round)
			if round_reasons:
				_logger.info(
					'side_mission_availability: round=%s skipped reasons=%s',
					round_number,
					round_reasons,
				)
				continue
			context = contexts_by_round[round_number]
			evaluations = SIDE_MISSION_DECK.evaluate(context)
			eligible_ids = [
				mission_id
				for mission_id, results in evaluations.items()
				if all(results.values())
			]
			_logger.info(
				'side_mission_availability: round=%s answer_city_id=%s evaluations=%s eligible=%s',
				round_number,
				context.answer['city_id'],
				evaluations,
				eligible_ids,
			)
			if eligible_ids:
				eligible_rounds.append(round_number)
			else:
				_logger.info(
					'side_mission_availability: round=%s skipped because no mission is eligible',
					round_number,
				)
		if not eligible_rounds:
			reasons.append('no rounds have an eligible mission')

	available = started or not reasons
	_logger.info(
		'side_mission_availability: completed session_id=%s available=%s started=%s reasons=%s elapsed_ms=%.1f',
		session_id,
		available,
		started,
		reasons,
		(perf_counter() - started_at) * 1000.0,
	)
	return {
		'available': available,
		'started': started,
		'reasons': reasons,
	}


def get_side_mission_availability(
	cur,
	daily_session,
	completed_rounds: list[dict],
	user_id: int,
) -> dict:
	game_id = int(daily_session.GameId)
	infinity_session = get_infinity_session(cur, user_id, game_id)
	mission_rows = (
		get_side_mission_rounds(cur, int(infinity_session.InfinityPoolSessionId))
		if infinity_session is not None
		else ()
	)
	guesses_by_round = _guesses_by_round(())
	contexts_by_round = {}
	if mission_rows or not _availability_precheck_reasons(daily_session, completed_rounds):
		contexts_by_round = _load_round_contexts(
			cur,
			game_id,
			completed_rounds,
			guesses_by_round,
		)
	return _evaluate_side_mission_availability(
		daily_session,
		completed_rounds,
		contexts_by_round,
		bool(mission_rows),
	)


def _mission_payload(mission_row, context: SideMissionContext) -> dict:
	mission = SIDE_MISSION_DECK.missions[mission_row.MissionId]
	progress = mission.calculate_progress(context)
	return {
		'round_number': int(mission_row.RoundNumber),
		'mission_id': mission.mission_id,
		'name': mission.name,
		'prompt': mission.build_prompt(context),
		'answer': {
			'city_id': int(context.answer['city_id']),
			'city_name': context.answer['city_name'],
			'country_code': context.answer['country_code'],
			'latitude': float(context.answer['latitude']),
			'longitude': float(context.answer['longitude']),
		},
		'progress': {
			'current': progress.current,
			'target': progress.target,
			'named': list(progress.named),
			'acknowledgements': {
				target_name: acknowledgement
				for target_name in progress.named
				if (acknowledgement := mission.build_acknowledgement(target_name)) is not None
			},
		},
		'completed_at': (
			mission_row.CompletedAt.isoformat()
			if mission_row.CompletedAt is not None
			else None
		),
	}


def _build_side_mission_state(
	cur,
	daily_session,
	infinity_session,
	mission_rows,
	contexts_by_round: dict[int, SideMissionContext],
) -> dict:
	started_at = perf_counter()
	daily_session_id = int(daily_session.SessionId)
	infinity_session_id = int(infinity_session.InfinityPoolSessionId)
	_logger.info(
		'side_mission_state: started daily_session_id=%s infinity_session_id=%s',
		daily_session_id,
		infinity_session_id,
	)
	missions = []
	for mission_row in mission_rows:
		round_number = int(mission_row.RoundNumber)
		context = contexts_by_round[round_number]
		progress = SIDE_MISSION_DECK.missions[mission_row.MissionId].calculate_progress(context)
		if progress.is_complete and mission_row.CompletedAt is None:
			complete_side_mission_round(cur, int(mission_row.SideMissionRoundId))
			mission_row = get_side_mission_round(cur, infinity_session_id, round_number)
			_logger.info(
				'side_mission_state: mission completed round=%s mission_id=%s progress=%s/%s',
				round_number,
				mission_row.MissionId,
				progress.current,
				progress.target,
			)
		missions.append(_mission_payload(mission_row, context))

	_logger.info(
		'side_mission_state: completed infinity_session_id=%s mission_count=%s elapsed_ms=%.1f',
		infinity_session_id,
		len(missions),
		(perf_counter() - started_at) * 1000.0,
	)
	return {
		'started': bool(mission_rows),
		'missions': missions,
	}


def load_side_mission_state(cur, daily_session, infinity_session) -> dict:
	infinity_session_id = int(infinity_session.InfinityPoolSessionId)
	completed_rounds = _load_daily_rounds(cur, int(daily_session.SessionId))
	guesses_by_round = _guesses_by_round(get_infinity_guesses(cur, infinity_session_id))
	mission_rows = get_side_mission_rounds(cur, infinity_session_id)
	contexts_by_round = _load_round_contexts(
		cur,
		int(daily_session.GameId),
		completed_rounds,
		guesses_by_round,
	)
	return _build_side_mission_state(
		cur,
		daily_session,
		infinity_session,
		mission_rows,
		contexts_by_round,
	)


def assign_specific_side_missions(
	cur,
	infinity_session_id: int,
	completed_rounds: list[dict],
	contexts_by_round: dict[int, SideMissionContext],
	assignments: dict[int, str],
) -> None:
	completed_by_round = {
		int(round_data['round_number']): round_data
		for round_data in completed_rounds
	}
	for round_number, mission_id in assignments.items():
		if round_number not in completed_by_round:
			raise ValueError(f'E2E Side Mission round {round_number} does not exist.')
		completed_round = completed_by_round[round_number]
		round_reasons = _round_ineligibility_reasons(completed_round)
		if round_reasons:
			raise ValueError(
				f'E2E Side Mission round {round_number} is ineligible: '
				+ ', '.join(round_reasons)
			)
		context = contexts_by_round[round_number]
		eligible_ids = {
			mission.mission_id
			for mission in SIDE_MISSION_DECK.eligible_missions(context)
		}
		if mission_id not in eligible_ids:
			raise ValueError(
				f'E2E Side Mission {mission_id} is not eligible for round {round_number}; '
				f'eligible missions: {sorted(eligible_ids)}.'
			)
		mission = SIDE_MISSION_DECK.missions[mission_id]
		progress = mission.calculate_progress(context)
		insert_side_mission_round(
			cur,
			infinity_session_id,
			round_number,
			mission_id,
			progress.is_complete,
		)
		_logger.info(
			'start_side_missions: assigned fixed round=%s mission_id=%s initial_progress=%s/%s',
			round_number,
			mission_id,
			progress.current,
			progress.target,
		)


def assign_random_side_missions(
	cur,
	infinity_session_id: int,
	completed_rounds: list[dict],
	contexts_by_round: dict[int, SideMissionContext],
) -> None:
	randomizer = random.SystemRandom()
	for completed_round in completed_rounds:
		round_number = int(completed_round['round_number'])
		round_reasons = _round_ineligibility_reasons(completed_round)
		if round_reasons:
			_logger.info(
				'start_side_missions: skipped round=%s reasons=%s',
				round_number,
				round_reasons,
			)
			continue
		context = contexts_by_round[round_number]
		eligible_missions = SIDE_MISSION_DECK.eligible_missions(context)
		if not eligible_missions:
			_logger.info(
				'start_side_missions: skipped round=%s because no mission is eligible',
				round_number,
			)
			continue
		mission = randomizer.choice(eligible_missions)
		progress = mission.calculate_progress(context)
		insert_side_mission_round(
			cur,
			infinity_session_id,
			round_number,
			mission.mission_id,
			progress.is_complete,
		)
		_logger.info(
			'start_side_missions: assigned round=%s mission_id=%s initial_progress=%s/%s',
			round_number,
			mission.mission_id,
			progress.current,
			progress.target,
		)


def ensure_side_mission_assignments(cur, daily_session, infinity_session):
	infinity_session_id = int(infinity_session.InfinityPoolSessionId)
	existing = get_side_mission_rounds(cur, infinity_session_id)
	if existing:
		return existing

	completed_rounds = _load_daily_rounds(cur, int(daily_session.SessionId))
	guesses_by_round = _guesses_by_round(get_infinity_guesses(cur, infinity_session_id))
	contexts_by_round = _load_round_contexts(
		cur,
		int(daily_session.GameId),
		completed_rounds,
		guesses_by_round,
	)
	availability = _evaluate_side_mission_availability(
		daily_session,
		completed_rounds,
		contexts_by_round,
		False,
	)
	if not availability['available']:
		return ()

	assignments = _e2e_mission_assignments()
	if assignments is None:
		assign_random_side_missions(
			cur,
			infinity_session_id,
			completed_rounds,
			contexts_by_round,
		)
	else:
		assign_specific_side_missions(
			cur,
			infinity_session_id,
			completed_rounds,
			contexts_by_round,
			assignments,
		)
	assigned_missions = get_side_mission_rounds(cur, infinity_session_id)
	if assigned_missions:
		update_current_round(
			cur,
			infinity_session_id,
			int(assigned_missions[0].RoundNumber),
		)
	return assigned_missions


def start_side_missions(user_id: int, session_id: int | None) -> tuple[dict, int]:
	started_at = perf_counter()
	_logger.info('start_side_missions: started user_id=%s session_id=%s', user_id, session_id)
	try:
		with get_conn() as conn:
			cur = conn.cursor()
			daily_session = get_current_session(cur, user_id, session_id)
			if daily_session is None:
				return {'error': 'No game found for today.'}, 404
			completed_rounds = _load_daily_rounds(cur, int(daily_session.SessionId))
			game_id = int(daily_session.GameId)
			infinity_session = get_infinity_session(cur, user_id, game_id)
			assigned_missions = (
				get_side_mission_rounds(cur, int(infinity_session.InfinityPoolSessionId))
				if infinity_session is not None
				else ()
			)
			guesses_by_round = (
				_guesses_by_round(
					get_infinity_guesses(cur, int(infinity_session.InfinityPoolSessionId))
				)
				if infinity_session is not None
				else _guesses_by_round(())
			)
			contexts_by_round = {}
			if assigned_missions or not _availability_precheck_reasons(daily_session, completed_rounds):
				contexts_by_round = _load_round_contexts(
					cur,
					game_id,
					completed_rounds,
					guesses_by_round,
				)
			availability = _evaluate_side_mission_availability(
				daily_session,
				completed_rounds,
				contexts_by_round,
				bool(assigned_missions),
			)
			if not availability['available']:
				return {
					'error': 'Side missions are unavailable for this game.',
					'reasons': availability['reasons'],
				}, 403

			if infinity_session is None:
				infinity_session = create_infinity_session(cur, user_id, game_id)
			if not assigned_missions:
				infinity_session_id = int(infinity_session.InfinityPoolSessionId)
				assignments = _e2e_mission_assignments()
				if assignments is None:
					assign_random_side_missions(
						cur,
						infinity_session_id,
						completed_rounds,
						contexts_by_round,
					)
				else:
					assign_specific_side_missions(
						cur,
						infinity_session_id,
						completed_rounds,
						contexts_by_round,
						assignments,
					)
				assigned_missions = get_side_mission_rounds(cur, infinity_session_id)
				if assigned_missions:
					update_current_round(
						cur,
						infinity_session_id,
						int(assigned_missions[0].RoundNumber),
					)
			if not assigned_missions:
				raise LookupError('No Side Mission assignments were created.')
			infinity_session_id = int(infinity_session.InfinityPoolSessionId)
			state = _build_side_mission_state(
				cur,
				daily_session,
				infinity_session,
				assigned_missions,
				contexts_by_round,
			)
			conn.commit()
	except Exception:
		_logger.exception(
			'start_side_missions: failed user_id=%s session_id=%s elapsed_ms=%.1f',
			user_id,
			session_id,
			(perf_counter() - started_at) * 1000.0,
		)
		raise

	_logger.info(
		'start_side_missions: completed user_id=%s infinity_session_id=%s elapsed_ms=%.1f',
		user_id,
		infinity_session_id,
		(perf_counter() - started_at) * 1000.0,
	)
	return {
		'infinity_pool_session_id': infinity_session_id,
		'side_missions': state,
	}, 200


def get_original_answer_city_id(
	cur,
	daily_session,
	infinity_session_id: int,
	round_number: int,
) -> int | None:
	completed_rounds = _load_daily_rounds(cur, int(daily_session.SessionId))
	completed_round = next(
		item for item in completed_rounds
		if int(item['round_number']) == round_number
	)
	if not completed_round['guesses']:
		return None
	return int(completed_round['guesses'][0]['city_id'])
