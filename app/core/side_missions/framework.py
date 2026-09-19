from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Mapping


@dataclass(frozen=True)
class SideMissionContext:
	answer: dict
	cities: tuple[dict, ...]
	guesses: tuple[dict, ...]

	@property
	def found_city_ids(self) -> set[int]:
		return {
			int(city['city_id'])
			for city in (self.answer, *self.guesses)
		}


@dataclass(frozen=True)
class MissionProgress:
	current: int
	target: int
	named: tuple[str, ...]

	@property
	def is_complete(self) -> bool:
		return self.current >= self.target


EligibilityCheck = Callable[[SideMissionContext], bool]
PromptBuilder = Callable[[SideMissionContext], str]
ProgressCalculator = Callable[[SideMissionContext], MissionProgress]
AcknowledgementBuilder = Callable[[str], str]


@dataclass(frozen=True)
class SideMissionDefinition:
	mission_id: str
	name: str
	build_prompt: PromptBuilder
	calculate_progress: ProgressCalculator
	build_acknowledgement: AcknowledgementBuilder


@dataclass(frozen=True)
class SideMissionDeck:
	eligibility_scenarios: Mapping[str, EligibilityCheck]
	missions: Mapping[str, SideMissionDefinition]
	mission_eligibility: Mapping[str, tuple[str, ...]]

	def evaluate(self, context: SideMissionContext) -> dict[str, dict[str, bool]]:
		return {
			mission_id: {
				scenario_id: self.eligibility_scenarios[scenario_id](context)
				for scenario_id in scenario_ids
			}
			for mission_id, scenario_ids in self.mission_eligibility.items()
		}

	def eligible_missions(self, context: SideMissionContext) -> tuple[SideMissionDefinition, ...]:
		evaluations = self.evaluate(context)
		return tuple(
			self.missions[mission_id]
			for mission_id, results in evaluations.items()
			if all(results.values())
		)

	def select_mission(
		self,
		context: SideMissionContext,
		randomizer: random.SystemRandom,
	) -> SideMissionDefinition:
		eligible = self.eligible_missions(context)
		if not eligible:
			raise LookupError('No side mission is eligible for this round.')
		return randomizer.choice(eligible)
