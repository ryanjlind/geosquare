# core/game_mappers.py

def map_completed_rounds(rows):
    completed = {}

    for r in rows:
        round_number = int(r.RoundNumber)

        if round_number not in completed:
            completed[round_number] = {
                "session_round_id": int(r.SessionRoundId),
                "round_number": round_number,
                "square_id": int(r.SquareId),
                "score": int(getattr(r, "Score", 0) or 0),
                "round_status": r.RoundStatus,
                "guesses": [],
            }

        if r.CityName is not None:
            completed[round_number]["guesses"].append({
                "city_id": int(r.CityId) if r.CityId is not None else None,
                "city_name": r.CityName,
                "latitude": float(r.Latitude),
                "longitude": float(r.Longitude),
                "population": int(r.Population) if r.Population is not None else None,
                "score": int(getattr(r, "Score", 0) or 0),
                "rank": int(r.PopRank) if r.PopRank is not None else None,
                "guessed_at": r.GuessedAt.isoformat(),
            })

    return list(completed.values())


def map_square(row, cities_rows, city_count_row, has_next_expansion):
    cities = [
        {
            "city_name": c.CityName,
            "country_code": c.CountryCode,
            "latitude": float(c.Latitude),
            "longitude": float(c.Longitude),
            "population": int(c.Population),
        }
        for c in cities_rows
    ]

    return {
        "square_id": int(row.SquareId),
        "expansion_level": int(row.ExpansionLevel),
        "has_next_expansion": has_next_expansion,
        "config_key": row.ConfigKey,
        "seed": {"lat": float(row.SeedLat), "lon": float(row.SeedLon)},
        "bounds": {
            "min_lat": float(row.MinLat),
            "min_lon": float(row.MinLon),
            "max_lat": float(row.MaxLat),
            "max_lon": float(row.MaxLon),
        },
        "total_population": int(row.TotalPopulation),
        "qualifying_city_count": int(row.QualifyingCityCount),
        "width_degrees": float(row.WidthDegrees),
        "height_degrees": float(row.HeightDegrees),
        "generated_at": row.GeneratedAt.isoformat(),
        "rules": {
            "min_total_population": int(row.MinTotalPopulation),
            "min_city_count": int(row.MinCityCount),
            "min_city_population": int(row.MinCityPopulation),
            "max_square_width_degrees": float(row.MaxSquareWidthDegrees),
            "max_square_height_degrees": float(row.MaxSquareHeightDegrees),
            "step_degrees": float(row.StepDegrees),
        },
        "cities": cities,
        "total_city_count": int(city_count_row.TotalCityCount),
        "largest_city": cities[0] if cities else None,
        "round_number": int(row.RoundNumber),
        "game_id": int(row.GameId),
    }


def map_game_state(session, completed_rounds, is_authenticated, username):
    base = {
        "session_id": int(session.SessionId),
        "user_id": int(session.UserId),
        "game_id": int(session.GameId),
        "total_score": int(session.TotalScore),
        "is_authenticated": is_authenticated,
        "username": username,
    }

    is_perfect = all(r["score"] > 0 for r in completed_rounds)

    if session.CompletedAt is not None:
        round_number = completed_rounds[-1]["round_number"] if completed_rounds else 1
        return {
            "state": "completed",
            "round_number": round_number,
            "completed_at": session.CompletedAt.isoformat(),
            "completed_rounds": completed_rounds,
            "is_perfect": is_perfect,
            **base,
        }

    if len(completed_rounds) == 0:
        return {
            "state": "not_started",
            "round_number": 1,
            "completed_at": None,
            "completed_rounds": [],
            "is_perfect": True,
            **base,
        }

    next_round = completed_rounds[-1]["round_number"] + 1

    return {
        "state": "in_progress",
        "round_number": next_round,
        "completed_at": None,
        "completed_rounds": completed_rounds,
        "is_perfect": is_perfect,
        **base,
    }


def map_player_stats(sessions, round_stats, best_guess, current_streak, longest_streak):
    scores = [int(s.TotalScore) for s in sessions]

    games_played = len(scores)
    average_score = round(sum(scores) / games_played)

    perfect_days = 0
    perfect_streak = 0
    perfect_flags = []

    for s in sessions:
        rs = round_stats.get(int(s.SessionId))
        solved = int(rs["solved_rounds"]) if rs else 0
        total = int(rs["total_rounds"]) if rs else 0

        is_perfect = total > 0 and solved == total
        perfect_flags.append(is_perfect)

        if is_perfect:
            perfect_days += 1

    for flag in reversed(perfect_flags):
        if not flag:
            break
        perfect_streak += 1

    best_index = max(range(len(sessions)), key=lambda i: int(sessions[i].TotalScore))
    best_score = int(sessions[best_index].TotalScore)
    best_score_game_date = sessions[best_index].GameDate.isoformat()

    last_score = int(sessions[-1].TotalScore)
    last_game_date = sessions[-1].GameDate.isoformat()

    graph_points = []
    for s in sessions[-20:]:
        rs = round_stats.get(s.SessionId)
        solved = int(rs["solved_rounds"]) if rs else 0
        total = int(rs["total_rounds"]) if rs else 0

        graph_points.append({
            "game_date": s.GameDate.isoformat(),
            "solved": solved,
            "points": int(s.TotalScore),
            "is_perfect": solved == total,
        })

    return {
        "games_played": games_played,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "perfect_days": perfect_days,
        "perfect_streak": perfect_streak,
        "average_score": average_score,
        "best_score": best_score,
        "best_score_game_date": best_score_game_date,
        "last_score": last_score,
        "last_game_date": last_game_date,
        "graph_points": graph_points,
        "best_guess": {
            "city_name": best_guess.CityName,
            "population": int(best_guess.Population) if best_guess and best_guess.Population is not None else None,
            "score": int(best_guess.Score) if best_guess else None,
            "game_date": best_guess.GameDate.isoformat() if best_guess else None,
            "round_number": int(best_guess.RoundNumber) if best_guess else None,
        } if best_guess else None,
    }