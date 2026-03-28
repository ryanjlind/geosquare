import math


def compute_score(rows, guessed_population: int) -> int:
    populations = sorted(
        int(row.Population)
        for row in rows
        if row.Population is not None and int(row.Population) > 0
    )

    if not populations:
        return 0

    if len(populations) == 1:
        return 100

    min_pop = populations[0]
    max_pop = populations[-1]

    if guessed_population <= min_pop or max_pop <= min_pop:
        return 100

    log_min = math.log(min_pop)
    log_max = math.log(max_pop)
    log_guess = math.log(max(guessed_population, 1))

    full_span = (log_guess - log_min) / (log_max - log_min)
    full_span = max(0.0, min(1.0, full_span))

    plausible_cutoff = 50000
    plausible = [population for population in populations if population >= plausible_cutoff]

    if len(plausible) >= 2:
        p_min = plausible[0]
        p_max = plausible[-1]

        if guessed_population <= p_min:
            plausible_span = 0.0
        elif guessed_population >= p_max:
            plausible_span = 1.0
        elif p_max == p_min:
            plausible_span = 0.0
        else:
            plausible_span = (math.log(guessed_population) - math.log(p_min)) / (math.log(p_max) - math.log(p_min))
            plausible_span = max(0.0, min(1.0, plausible_span))
    else:
        plausible_span = full_span

    blended_span = (0.55 * full_span) + (0.45 * plausible_span)

    plausible_ratio = len(plausible) / len(populations)
    floor_score = 45 + round((1.0 - plausible_ratio) * 20)

    curved = (1.0 - blended_span) ** 0.55
    score = floor_score + ((100 - floor_score) * curved)

    return max(floor_score, min(100, round(score)))
