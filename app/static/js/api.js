const CSRF_COOKIE_NAME = 'geosquare_csrf';
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

function getCookie(name) {
    const prefix = `${encodeURIComponent(name)}=`;
    const cookie = document.cookie
        .split('; ')
        .find(value => value.startsWith(prefix));
    return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null;
}

export function fetchWithCsrf(url, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    if (!UNSAFE_METHODS.has(method)) {
        return fetch(url, options);
    }

    const headers = new Headers(options.headers);
    const csrfToken = getCookie(CSRF_COOKIE_NAME);
    if (csrfToken !== null) {
        headers.set('X-CSRF-Token', csrfToken);
    }

    return fetch(url, { ...options, headers });
}

export async function fetchJson(url, options = {}) {
    const response = await fetchWithCsrf(url, options);
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

export async function fetchInfinityState(infinityPoolSessionId = null) {
    const params = new URLSearchParams();
    if (infinityPoolSessionId !== null) {
        params.set('infinity_pool_session_id', infinityPoolSessionId);
    }
    const query = params.toString();
    return fetchJson(`/api/infinity-state${query ? `?${query}` : ''}`);
}

export async function selectInfinityRoundRequest(roundNumber, infinityPoolSessionId = null) {
    const payload = { round_number: roundNumber };
    if (infinityPoolSessionId !== null) {
        payload.infinity_pool_session_id = infinityPoolSessionId;
    }
    return fetchJson('/api/infinity-round', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
}

export async function submitInfinityGuessRequest(
    guess,
    roundNumber,
    revealCityId = null,
    infinityPoolSessionId = null,
    confirmedCityId = null,
) {
    const payload = {
        guess,
        round_number: roundNumber,
    };
    if (revealCityId !== null) {
        payload.reveal_city_id = revealCityId;
    }
    if (infinityPoolSessionId !== null) {
        payload.infinity_pool_session_id = infinityPoolSessionId;
    }
    if (confirmedCityId !== null) {
        payload.confirmed_city_id = confirmedCityId;
    }

    return fetchJson('/api/infinity-guess', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
}

export async function startSideMissionsRequest() {
    return fetchJson('/api/side-missions/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
    });
}
