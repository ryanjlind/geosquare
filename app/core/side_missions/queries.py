def get_side_mission_rounds(cur, infinity_session_id: int):
	cur.execute(
		"""
		SELECT
			SideMissionRoundId,
			InfinityPoolSessionId,
			RoundNumber,
			MissionId,
			CreatedAt,
			CompletedAt
		FROM dbo.SideMissionRounds
		WHERE InfinityPoolSessionId = ?
		ORDER BY RoundNumber
		""",
		(infinity_session_id,),
	)
	return cur.fetchall()


def get_side_mission_round(cur, infinity_session_id: int, round_number: int):
	cur.execute(
		"""
		SELECT
			SideMissionRoundId,
			InfinityPoolSessionId,
			RoundNumber,
			MissionId,
			CreatedAt,
			CompletedAt
		FROM dbo.SideMissionRounds
		WHERE InfinityPoolSessionId = ?
		  AND RoundNumber = ?
		""",
		(infinity_session_id, round_number),
	)
	return cur.fetchone()


def insert_side_mission_round(
	cur,
	infinity_session_id: int,
	round_number: int,
	mission_id: str,
	is_complete: bool,
) -> None:
	cur.execute(
		"""
		INSERT INTO dbo.SideMissionRounds (
			InfinityPoolSessionId,
			RoundNumber,
			MissionId,
			CreatedAt,
			CompletedAt
		)
		VALUES (
			?, ?, ?, SYSUTCDATETIME(),
			CASE WHEN ? = 1 THEN SYSUTCDATETIME() ELSE NULL END
		)
		""",
		(infinity_session_id, round_number, mission_id, int(is_complete)),
	)


def complete_side_mission_round(cur, side_mission_round_id: int) -> None:
	cur.execute(
		"""
		UPDATE dbo.SideMissionRounds
		SET CompletedAt = SYSUTCDATETIME()
		WHERE SideMissionRoundId = ?
		  AND CompletedAt IS NULL
		""",
		(side_mission_round_id,),
	)