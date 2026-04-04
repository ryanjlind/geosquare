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

export async function submitGuessRequest(guess, roundNumber) {
    const { response, data } = await fetchJson('/api/guess', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guess, round_number: roundNumber }),
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