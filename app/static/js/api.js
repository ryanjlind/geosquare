const CSRF_COOKIE_NAME = 'geosquare_csrf';
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);


export class ApiResponseError extends Error {
    constructor(response, message) {
        super(message);
        this.name = 'ApiResponseError';
        this.httpStatus = response.status;
        this.clientErrorReported = response.status >= 500;
    }
}

function getCookie(name) {
    const prefix = `${encodeURIComponent(name)}=`;
    const cookie = document.cookie
        .split('; ')
        .find(value => value.startsWith(prefix));
    return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null;
}

export async function fetchWithCsrf(url, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    let requestOptions = options;
    if (UNSAFE_METHODS.has(method)) {
        const headers = new Headers(options.headers);
        const csrfToken = getCookie(CSRF_COOKIE_NAME);
        if (csrfToken !== null) {
            headers.set('X-CSRF-Token', csrfToken);
        }
        requestOptions = { ...options, headers };
    }

    let response;
    try {
        response = await fetch(url, requestOptions);
    } catch (error) {
        await window.GeoSquareBrowserErrors.postRateLimitedClientError('api_network_error', {
            message: `${method} ${String(url)} failed: ${String(error)}`,
            method,
            request_url: String(url),
            error_name: error instanceof Error ? error.name : null,
            stack: error instanceof Error ? error.stack : null,
        });
        if (error instanceof Error) {
            error.clientErrorReported = true;
        }
        throw error;
    }

    if (response.status >= 500) {
        await window.GeoSquareBrowserErrors.postRateLimitedClientError('api_server_error', {
            message: `${method} ${String(url)} returned ${response.status}`,
            method,
            request_url: String(url),
            status: response.status,
            status_text: response.statusText,
        });
    }

    return response;
}

export async function fetchJson(url, options = {}) {
    const response = await fetchWithCsrf(url, options);
    const data = await response.json();
    return { response, data };
}

export async function setChallengeModeRequest(enabled) {
    return fetchJson('/api/challenge-mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
    });
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
        throw new ApiResponseError(
            response,
            data.error || 'Failed to fetch all daily squares.',
        );
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
