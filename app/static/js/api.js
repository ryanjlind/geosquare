export async function fetchJson(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    return { response, data };
}

export async function fetchGameState() {
    const { response, data } = await fetchJson('/api/game-state');
    return { response, data };
}

export async function fetchRound(roundNumber) {
    const { data } = await fetchJson(`/api/daily-square?round=${roundNumber}`);
    return data;
}

export async function fetchAllDailySquares() {
    const { response, data } = await fetchJson('/api/all-daily-squares');

    if (!response.ok) {
        throw new Error(data.error || 'Failed to fetch all daily squares.');
    }

    return data.rounds;
}

export async function submitGuessRequest(guess, roundNumber, confirmedCityId = null) {
    const { response, data } = await fetchJson('/api/guess', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            guess,
            round_number: roundNumber,
            confirmed_city_id: confirmedCityId,
        }),
    });

    return { response, data };
}

export async function submitPassRequest(roundNumber) {
    const { response, data } = await fetchJson('/api/pass', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ round_number: roundNumber }),
    });

    return { response, data };
}

export async function fetchPlayerStats() {
    const { data } = await fetchJson('/api/player-stats');
    return data;
}

export async function expandSquareRequest(roundNumber) {
    const { response, data } = await fetchJson('/api/expand', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ round_number: roundNumber }),
    });

    return { response, data };
}

export async function setDifficultyRequest(roundNumber, level) {
    const { response, data } = await fetchJson('/api/difficulty', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ round_number: roundNumber, level }),
    });

    return { response, data };
}

export async function fetchInfinityState() {
    return fetchJson('/api/infinity-state');
}

export async function selectInfinityRoundRequest(roundNumber) {
    return fetchJson('/api/infinity-round', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ round_number: roundNumber }),
    });
}

export async function submitInfinityGuessRequest(guess, roundNumber, revealCityId = null) {
    const payload = {
        guess,
        round_number: roundNumber,
    };
    if (revealCityId !== null) {
        payload.reveal_city_id = revealCityId;
    }

    return fetchJson('/api/infinity-guess', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
}