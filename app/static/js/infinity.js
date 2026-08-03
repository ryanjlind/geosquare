import {
    fetchInfinityState,
    selectInfinityRoundRequest,
    submitInfinityGuessRequest,
} from './api.js';
import { playFail, playSuccess } from './audio.js';
import { drawCities, renderRoundMap, showIncorrectGuessedCity } from './map.js';
import { escapeHtml, numberFmt } from './utils.js';


const infinityState = {
    active: false,
    currentRound: 1,
    roundCount: 5,
    roundScores: {},
    totalScore: 0,
    guesses: [],
    square: null,
};


function requireObject(value, path) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
        throw new Error(`Invalid Infinity response: ${path} must be an object.`);
    }
}


function requireArray(value, path) {
    if (!Array.isArray(value)) {
        throw new Error(`Invalid Infinity response: ${path} must be an array.`);
    }
}


function requireBoolean(value, path) {
    if (typeof value !== 'boolean') {
        throw new Error(`Invalid Infinity response: ${path} must be a boolean.`);
    }
}


function requireString(value, path) {
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error(`Invalid Infinity response: ${path} must be a non-empty string.`);
    }
}


function requireNumber(value, path) {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
        throw new Error(`Invalid Infinity response: ${path} must be a finite number.`);
    }
}


function requireInteger(value, path) {
    if (!Number.isInteger(value)) {
        throw new Error(`Invalid Infinity response: ${path} must be an integer.`);
    }
}


function validateSquare(square, path) {
    requireObject(square, path);
    requireInteger(square.square_id, `${path}.square_id`);
    requireObject(square.bounds, `${path}.bounds`);
    requireNumber(square.bounds.min_lat, `${path}.bounds.min_lat`);
    requireNumber(square.bounds.min_lon, `${path}.bounds.min_lon`);
    requireNumber(square.bounds.max_lat, `${path}.bounds.max_lat`);
    requireNumber(square.bounds.max_lon, `${path}.bounds.max_lon`);
    requireArray(square.cities, `${path}.cities`);
    square.cities.forEach((city, index) => {
        const cityPath = `${path}.cities[${index}]`;
        requireObject(city, cityPath);
        requireInteger(city.city_id, `${cityPath}.city_id`);
        requireInteger(city.population, `${cityPath}.population`);
        requireBoolean(city.is_capital, `${cityPath}.is_capital`);
    });
}


function validateRestoredGuess(guess, path) {
    requireObject(guess, path);
    requireInteger(guess.round_number, `${path}.round_number`);
    requireInteger(guess.city_id, `${path}.city_id`);
    requireString(guess.city_name, `${path}.city_name`);
    requireInteger(guess.population, `${path}.population`);
    requireInteger(guess.score, `${path}.score`);
    requireNumber(guess.latitude, `${path}.latitude`);
    requireNumber(guess.longitude, `${path}.longitude`);
}


function validateAcceptedGuess(guess, path) {
    requireObject(guess, path);
    requireString(guess.city, `${path}.city`);
    requireInteger(guess.city_id, `${path}.city_id`);
    requireString(guess.country_code, `${path}.country_code`);
    requireNumber(guess.latitude, `${path}.latitude`);
    requireNumber(guess.longitude, `${path}.longitude`);
    requireInteger(guess.population, `${path}.population`);
    requireInteger(guess.rank, `${path}.rank`);
    requireInteger(guess.score, `${path}.score`);
}


function validateStringArray(values, path) {
    requireArray(values, path);
    values.forEach((value, index) => requireString(value, `${path}[${index}]`));
}


function validateInfinityStateResponse(data) {
    requireObject(data, 'state');
    requireBoolean(data.unlocked, 'state.unlocked');
    requireInteger(data.current_round, 'state.current_round');
    requireInteger(data.round_count, 'state.round_count');
    requireObject(data.round_scores, 'state.round_scores');
    for (let roundNumber = 1; roundNumber <= data.round_count; roundNumber += 1) {
        requireInteger(data.round_scores[roundNumber], `state.round_scores[${roundNumber}]`);
    }
    requireInteger(data.total_score, 'state.total_score');
    requireArray(data.guesses, 'state.guesses');
    data.guesses.forEach(
        (guess, index) => validateRestoredGuess(guess, `state.guesses[${index}]`),
    );
    validateSquare(data.square, 'state.square');
}


function validateRoundResponse(data) {
    requireObject(data, 'round');
    requireInteger(data.current_round, 'round.current_round');
    validateSquare(data.square, 'round.square');
}


function validateSubmitResponse(data) {
    requireObject(data, 'guess');
    requireBoolean(data.ok, 'guess.ok');
    requireBoolean(data.correct, 'guess.correct');
    if (!data.correct) {
        requireInteger(data.score, 'guess.score');
        if ('matched_city' in data) {
            requireObject(data.matched_city, 'guess.matched_city');
            requireString(data.matched_city.city_name, 'guess.matched_city.city_name');
            requireNumber(data.matched_city.latitude, 'guess.matched_city.latitude');
            requireNumber(data.matched_city.longitude, 'guess.matched_city.longitude');
        }
        return;
    }

    requireBoolean(data.duplicate, 'guess.duplicate');
    validateStringArray(data.duplicates, 'guess.duplicates');
    if (data.duplicate) {
        if (data.duplicates.length === 0) {
            throw new Error('Invalid Infinity response: guess.duplicates must not be empty for a duplicate response.');
        }
        return;
    }

    requireArray(data.guesses, 'guess.guesses');
    if (data.guesses.length === 0) {
        throw new Error('Invalid Infinity response: guess.guesses must not be empty for a successful response.');
    }
    data.guesses.forEach(
        (guess, index) => validateAcceptedGuess(guess, `guess.guesses[${index}]`),
    );
    requireInteger(data.round_score, 'guess.round_score');
    requireInteger(data.total_score, 'guess.total_score');
}


function guessesForCurrentRound() {
    return infinityState.guesses.filter(
        guess => guess.round_number === infinityState.currentRound
    );
}


function progressForCurrentRound() {
    const cities = infinityState.square.cities;
    const foundIds = new Set(guessesForCurrentRound().map(guess => guess.city_id));
    const categories = [
        ['Cities', city => true],
        ['1M+', city => city.population >= 1_000_000],
        ['500K+', city => city.population >= 500_000],
        ['Capitals', city => city.is_capital],
    ];

    return categories.map(([label, matches]) => {
        const matchingCities = cities.filter(matches);
        return {
            label,
            found: matchingCities.filter(city => foundIds.has(city.city_id)).length,
            total: matchingCities.length,
        };
    });
}


function largestUnnamedPopulation() {
    const foundIds = new Set(guessesForCurrentRound().map(guess => guess.city_id));
    const unnamedCities = infinityState.square.cities.filter(
        city => !foundIds.has(city.city_id)
    );

    if (unnamedCities.length === 0) {
        return null;
    }

    return Math.max(...unnamedCities.map(city => city.population));
}


function renderProgressItems(progress) {
    return progress.map(item => `
        <div class="infinity-progress-item">
            <span>${item.label}</span>
            <strong>${item.found} / ${item.total}</strong>
        </div>
    `).join('');
}


function setModeButtons() {
    document.getElementById('dailyModeBtn').classList.toggle('active', !infinityState.active);
    document.getElementById('infinityModeBtn').classList.toggle('active', infinityState.active);
}


function setInfinityLayout() {
    infinityState.active = true;
    document.body.classList.add('infinity-mode');
    document.getElementById('roundTable').classList.add('hidden');
    document.getElementById('infinityPanel').classList.remove('hidden');
    document.getElementById('infinityInvite').classList.add('hidden');
    document.getElementById('difficultyRow').classList.add('hidden');
    document.getElementById('passBtn').style.display = 'none';
    document.getElementById('expandBtn').style.display = 'none';
    document.getElementById('previousBtn').style.display = 'inline-block';
    document.getElementById('nextBtn').style.display = 'inline-block';
    document.getElementById('shareScoreBtn').style.display = 'none';
    document.getElementById('postGameActions').style.display = 'grid';
    document.getElementById('guessBox').style.display = 'block';
    setModeButtons();
}


function renderInfinityMeta() {
    const currentGuesses = guessesForCurrentRound();
    const progress = progressForCurrentRound();
    const progressItems = renderProgressItems(progress);
    const largestPopulation = largestUnnamedPopulation();
    const largestUnnamedText = largestPopulation === null
        ? 'All cities named'
        : `Largest unnamed city: ${numberFmt(largestPopulation)}`;
    document.getElementById('meta').innerHTML = `
        <div class="infinity-round-heading">
            <span>Square ${infinityState.currentRound} of ${infinityState.roundCount}</span>
        </div>
        <div class="desktop-meta-only infinity-gameplay-copy">
            Name as many cities as you can. You can move back and forth between squares to add as many cities as you want. See how high you can reach!
        </div>
        <div class="desktop-meta-only infinity-progress-board">
            ${progressItems}
        </div>
        <div class="desktop-meta-only infinity-largest-unnamed">${largestUnnamedText}</div>
        <span class="hidden" data-mobile-cities-value>${currentGuesses.length}</span>
    `;
    const mobileProgress = document.getElementById('mobileInfinityProgress');
    if (mobileProgress) {
        mobileProgress.innerHTML = progressItems;
    }
    const mobileLargestUnnamed = document.getElementById('mobileInfinityLargestUnnamed');
    if (mobileLargestUnnamed) {
        mobileLargestUnnamed.textContent = largestUnnamedText;
    }
    const mobileRound = document.getElementById('mobileRoundStat');
    const mobileCities = document.getElementById('mobileCitiesStat');
    if (mobileRound) {
        mobileRound.textContent = String(infinityState.currentRound);
    }
    if (mobileCities) {
        mobileCities.textContent = String(currentGuesses.length);
    }
}


function renderChips(newCityIds = []) {
    const chipList = document.getElementById('infinityChips');
    const guesses = [...guessesForCurrentRound()].reverse();
    const newCityIdSet = new Set(newCityIds);
    if (guesses.length === 0) {
        chipList.innerHTML = '<div class="infinity-empty">No cities found yet.</div>';
        return;
    }

    chipList.innerHTML = guesses.map(guess => `
        <div class="infinity-chip${newCityIdSet.has(guess.city_id) ? ' newly-scored' : ''}">
            <span class="infinity-chip-city">${escapeHtml(guess.city_name)}</span>
            <span class="infinity-chip-score">+${numberFmt(guess.score)}</span>
        </div>
    `).join('');
}


function animateNumber(element, from, to) {
    const duration = 650;
    const startedAt = performance.now();

    function frame(now) {
        const progress = Math.min((now - startedAt) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        element.textContent = numberFmt(Math.round(from + ((to - from) * eased)));
        if (progress < 1) {
            window.requestAnimationFrame(frame);
        }
    }

    window.requestAnimationFrame(frame);
}


function renderScores(previousRoundScore = null, previousTotalScore = null) {
    const roundScore = infinityState.roundScores[infinityState.currentRound];
    const roundElement = document.getElementById('infinityRoundScore');
    const totalElement = document.getElementById('infinityTotalScore');

    if (previousRoundScore === null) {
        roundElement.textContent = numberFmt(roundScore);
    } else {
        animateNumber(roundElement, previousRoundScore, roundScore);
    }

    if (previousTotalScore === null) {
        totalElement.textContent = numberFmt(infinityState.totalScore);
    } else {
        animateNumber(totalElement, previousTotalScore, infinityState.totalScore);
    }

    document.getElementById('totalPoints').textContent = numberFmt(infinityState.totalScore);
    const mobilePoints = document.getElementById('mobilePointsStat');
    if (mobilePoints) {
        mobilePoints.textContent = numberFmt(infinityState.totalScore);
    }
}


function renderMarkers() {
    drawCities(
        guessesForCurrentRound().map(guess => ({
            city_name: guess.city_name,
            label: guess.city_name,
            latitude: guess.latitude,
            longitude: guess.longitude,
            pixel_size: 8,
            color: Cesium.Color.LIME,
            outline_color: Cesium.Color.BLACK,
            outline_width: 2,
        }))
    );
}


function renderRound() {
    renderRoundMap(infinityState.square);
    renderMarkers();
    renderInfinityMeta();
    renderChips();
    renderScores();
    document.getElementById('previousBtn').disabled = infinityState.currentRound === 1;
    document.getElementById('nextBtn').disabled = infinityState.currentRound === infinityState.roundCount;
    document.getElementById('nextBtn').textContent = 'Next Square';
    document.getElementById('guessFeedback').innerHTML = '';
    document.getElementById('guessInput').value = '';
    document.getElementById('guessInput').focus();
}


async function selectRound(roundNumber) {
    const { response, data } = await selectInfinityRoundRequest(roundNumber);
    if (!response.ok) {
        throw new Error(data.error);
    }
    validateRoundResponse(data);
    infinityState.currentRound = data.current_round;
    infinityState.square = data.square;
    renderRound();
}


async function submitGuess() {
    const input = document.getElementById('guessInput');
    const button = document.getElementById('guessBtn');
    const guess = input.value.trim();
    if (!guess) {
        return;
    }

    input.disabled = true;
    button.disabled = true;
    try {
        const { response, data } = await submitInfinityGuessRequest(
            guess,
            infinityState.currentRound,
        );
        if (!response.ok) {
            throw new Error(data.error);
        }
        validateSubmitResponse(data);
        if (!data.correct) {
            document.getElementById('guessFeedback').textContent = 'Not in this square.';
            if ('matched_city' in data) {
                showIncorrectGuessedCity(data.matched_city);
            }
            playFail();
            return;
        }
        if (data.duplicate) {
            document.getElementById('guessFeedback').textContent = `${data.duplicates.join(', ')} already in your pool.`;
            return;
        }

        const previousRoundScore = infinityState.roundScores[infinityState.currentRound] || 0;
        const previousTotalScore = infinityState.totalScore;
        infinityState.roundScores[infinityState.currentRound] = data.round_score;
        infinityState.totalScore = data.total_score;
        infinityState.guesses.push(...data.guesses.map(acceptedGuess => ({
            round_number: infinityState.currentRound,
            square_id: infinityState.square.square_id,
            city_id: acceptedGuess.city_id,
            city_name: acceptedGuess.city,
            population: acceptedGuess.population,
            score: acceptedGuess.score,
            latitude: acceptedGuess.latitude,
            longitude: acceptedGuess.longitude,
            rank: acceptedGuess.rank,
        })));
        drawCities(data.guesses.map(acceptedGuess => ({
            city_name: acceptedGuess.city,
            label: acceptedGuess.city,
            latitude: acceptedGuess.latitude,
            longitude: acceptedGuess.longitude,
            pixel_size: 8,
            color: Cesium.Color.LIME,
            outline_color: Cesium.Color.BLACK,
            outline_width: 2,
        })));
        renderInfinityMeta();
        renderChips(data.guesses.map(acceptedGuess => acceptedGuess.city_id));
        renderScores(previousRoundScore, previousTotalScore);
        const acceptedNames = data.guesses.map(acceptedGuess => acceptedGuess.city).join(', ');
        const awardedScore = data.guesses.reduce(
            (total, acceptedGuess) => total + acceptedGuess.score,
            0,
        );
        const duplicateText = data.duplicates.length
            ? `<br>${escapeHtml(data.duplicates.join(', '))} already in your pool.`
            : '';
        document.getElementById('guessFeedback').innerHTML = `<b>${escapeHtml(acceptedNames)}</b> +${numberFmt(awardedScore)}${duplicateText}`;
        input.value = '';
        playSuccess();
    } finally {
        input.disabled = false;
        button.disabled = false;
        input.focus();
    }
}


export async function enterInfinityMode() {
    const { response, data } = await fetchInfinityState();
    if (!response.ok) {
        throw new Error(data.error);
    }
    validateInfinityStateResponse(data);
    document.getElementById('statsOverlay').style.display = 'none';
    setInfinityLayout();
    infinityState.currentRound = data.current_round;
    infinityState.roundCount = data.round_count;
    infinityState.roundScores = data.round_scores;
    infinityState.totalScore = data.total_score;
    infinityState.guesses = data.guesses;
    infinityState.square = data.square;
    document.getElementById('guessInput').disabled = false;
    document.getElementById('guessBtn').disabled = false;
    renderRound();
}


export function isInfinityModeActive() {
    return infinityState.active;
}


async function handleEnterInfinityClick() {
    try {
        await enterInfinityMode();
    } catch (error) {
        console.error('Infinity mode failed:', error);
    }
}


export function unlockInfinityMode() {
    const infinityButton = document.getElementById('infinityModeBtn');
    document.getElementById('gameModeSwitch').classList.remove('hidden');
    infinityButton.disabled = false;
    infinityButton.removeAttribute('title');
    document.getElementById('infinityInvite').classList.remove('hidden');
    document.getElementById('statsInfinityInvite').classList.remove('hidden');
}


export function initInfinityMode(dailyCompleted) {
    const infinityButton = document.getElementById('infinityModeBtn');
    infinityButton.disabled = !dailyCompleted;
    if (!dailyCompleted) {
        infinityButton.title = 'Complete the Daily game to unlock Infinity Pool';
    }

    document.getElementById('dailyModeBtn').onclick = () => window.location.reload();
    infinityButton.onclick = handleEnterInfinityClick;
    document.getElementById('infinityInviteBtn').onclick = handleEnterInfinityClick;
    document.getElementById('statsInfinityInviteBtn').onclick = handleEnterInfinityClick;
    document.getElementById('previousBtn').onclick = () => selectRound(infinityState.currentRound - 1);
    document.getElementById('nextBtn').addEventListener('click', event => {
        if (!infinityState.active) {
            return;
        }
        event.stopImmediatePropagation();
        selectRound(infinityState.currentRound + 1);
    }, true);
    document.getElementById('guessBtn').addEventListener('click', event => {
        if (!infinityState.active) {
            return;
        }
        event.stopImmediatePropagation();
        submitGuess();
    }, true);
    document.getElementById('guessInput').addEventListener('keydown', event => {
        if (!infinityState.active || event.key !== 'Enter') {
            return;
        }
        event.preventDefault();
        event.stopImmediatePropagation();
        submitGuess();
    }, true);

    if (dailyCompleted) {
        unlockInfinityMode();
    }
    setModeButtons();
}