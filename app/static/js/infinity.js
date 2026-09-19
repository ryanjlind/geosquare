import {
    fetchInfinityState,
    selectInfinityRoundRequest,
    startSideMissionsRequest,
    submitInfinityGuessRequest,
} from './api.js?v=5';
import { playFail, playSuccess } from './audio.js?v=4';
import { drawCities, renderRoundMap, showIncorrectGuessedCity } from './map.js?v=4';
import { escapeHtml, numberFmt } from './utils.js?v=4';


const SIDE_MISSION_ACKNOWLEDGEMENT_MS = 2500;

const infinityState = {
    active: false,
    mode: 'daily',
    poolSessionId: null,
    currentRound: 1,
    roundCount: 5,
    roundScores: {},
    totalScore: 0,
    guesses: [],
    square: null,
    sideMissions: [],
    sideMissionsAvailable: false,
};

let showDailyRound = null;
let showSummary = null;
let sideMissionAcknowledgementTimer = null;


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
        requireString(city.city_name, `${cityPath}.city_name`);
        requireString(city.country_code, `${cityPath}.country_code`);
        requireNumber(city.latitude, `${cityPath}.latitude`);
        requireNumber(city.longitude, `${cityPath}.longitude`);
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
    requireInteger(data.infinity_pool_session_id, 'state.infinity_pool_session_id');
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
    validateSideMissionState(data.side_missions, 'state.side_missions');
}


function validateSideMissionState(sideMissions, path) {
    requireObject(sideMissions, path);
    requireBoolean(sideMissions.started, `${path}.started`);
    requireArray(sideMissions.missions, `${path}.missions`);
    sideMissions.missions.forEach((mission, index) => {
        const missionPath = `${path}.missions[${index}]`;
        requireObject(mission, missionPath);
        requireInteger(mission.round_number, `${missionPath}.round_number`);
        requireString(mission.mission_id, `${missionPath}.mission_id`);
        requireString(mission.name, `${missionPath}.name`);
        requireString(mission.prompt, `${missionPath}.prompt`);
        requireObject(mission.answer, `${missionPath}.answer`);
        requireInteger(mission.answer.city_id, `${missionPath}.answer.city_id`);
        requireString(mission.answer.city_name, `${missionPath}.answer.city_name`);
        requireString(mission.answer.country_code, `${missionPath}.answer.country_code`);
        requireNumber(mission.answer.latitude, `${missionPath}.answer.latitude`);
        requireNumber(mission.answer.longitude, `${missionPath}.answer.longitude`);
        requireObject(mission.progress, `${missionPath}.progress`);
        requireInteger(mission.progress.current, `${missionPath}.progress.current`);
        requireInteger(mission.progress.target, `${missionPath}.progress.target`);
        validateStringArray(mission.progress.named, `${missionPath}.progress.named`);
        requireObject(
            mission.progress.acknowledgements,
            `${missionPath}.progress.acknowledgements`,
        );
        mission.progress.named.forEach(name => requireString(
            mission.progress.acknowledgements[name],
            `${missionPath}.progress.acknowledgements[${name}]`,
        ));
        if (mission.completed_at !== null && typeof mission.completed_at !== 'string') {
            throw new Error(`Invalid Infinity response: ${missionPath}.completed_at must be a string or null.`);
        }
    });
}


function validateRoundResponse(data) {
    requireObject(data, 'round');
    requireInteger(data.infinity_pool_session_id, 'round.infinity_pool_session_id');
    requireInteger(data.current_round, 'round.current_round');
    validateSquare(data.square, 'round.square');
}


function validateSubmitResponse(data) {
    requireObject(data, 'guess');
    requireBoolean(data.ok, 'guess.ok');
    if (data.requires_confirmation === true) {
        requireArray(data.candidates, 'guess.candidates');
        requireString(data.guess, 'guess.guess');
        return;
    }
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
    validateSideMissionState(data.side_missions, 'guess.side_missions');
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


function largestUnnamedCity() {
    const foundIds = new Set(guessesForCurrentRound().map(guess => guess.city_id));
    const unnamedCities = infinityState.square.cities.filter(
        city => !foundIds.has(city.city_id)
    );

    if (unnamedCities.length === 0) {
        return null;
    }

    return unnamedCities.reduce((largest, city) => (
        city.population > largest.population ? city : largest
    ));
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
    document.getElementById('dailyModeBtn').classList.toggle('active', infinityState.mode === 'daily');
    document.getElementById('infinityModeBtn').classList.toggle('active', infinityState.mode === 'infinity');
}


function setPoolLayout() {
    infinityState.active = true;
    infinityState.mode = 'infinity';
    document.body.classList.add('infinity-mode');
    document.getElementById('roundTable').classList.add('hidden');
    document.getElementById('infinityPanel').classList.remove('hidden');
    document.getElementById('sideMissionsInvite').classList.add('hidden');
    document.getElementById('difficultyRow').classList.add('hidden');
    document.getElementById('passBtn').style.display = 'none';
    document.getElementById('expandBtn').style.display = 'none';
    document.getElementById('previousBtn').style.display = 'inline-block';
    document.getElementById('nextBtn').style.display = 'inline-block';
    document.getElementById('shareScoreBtn').style.display = 'none';
    document.getElementById('summaryBtn').classList.remove('hidden');
    document.getElementById('postGameActions').style.display = 'grid';
    document.getElementById('guessBox').style.display = 'block';
    document.getElementById('sideMissionPanel').classList.add('hidden');
    setModeButtons();
}


function setDailyLayout() {
    infinityState.active = false;
    infinityState.mode = 'daily';
    document.body.classList.remove('infinity-mode');
    document.getElementById('roundTable').classList.remove('hidden');
    document.getElementById('infinityPanel').classList.add('hidden');
    document.getElementById('sideMissionPanel').classList.add('hidden');
    document.getElementById('guessBox').style.display = 'none';
    document.getElementById('previousBtn').style.display = 'none';
    document.getElementById('nextBtn').style.display = 'none';
    document.getElementById('shareScoreBtn').style.display = 'inline-block';
    document.getElementById('summaryBtn').classList.remove('hidden');
    document.getElementById('sideMissionsInvite').classList.toggle(
        'hidden',
        !infinityState.sideMissionsAvailable,
    );
    setModeButtons();
}


function currentSideMission() {
    return infinityState.sideMissions.find(
        mission => mission.round_number === infinityState.currentRound,
    );
}


function renderSideMission() {
    const panel = document.getElementById('sideMissionPanel');
    const mission = currentSideMission();
    if (!mission) {
        panel.classList.add('hidden');
        return;
    }
    const complete = mission.completed_at !== null;
    panel.classList.remove('hidden');
    document.getElementById('guessBox').style.display = 'block';
    document.getElementById('sideMissionName').textContent = mission.name;
    document.getElementById('sideMissionPrompt').textContent = mission.prompt;
    const targetChips = mission.progress.named.map(
        name => `<span class="side-mission-target">${escapeHtml(name)}</span>`,
    ).join('');
    document.getElementById('sideMissionProgress').innerHTML = `
        <strong class="side-mission-count">${mission.progress.current} / ${mission.progress.target}</strong>
        <span class="side-mission-targets">${targetChips}</span>
        ${complete ? '<strong class="side-mission-complete">Complete!</strong>' : ''}
    `;
}


function renderInfinityMeta() {
    const currentGuesses = guessesForCurrentRound();
    const progress = progressForCurrentRound();
    const progressItems = renderProgressItems(progress);
    const largestCity = largestUnnamedCity();
    const largestUnnamedText = largestCity === null
        ? 'All cities named'
        : `Largest unnamed city: ${numberFmt(largestCity.population)}`;
    const revealAvailable = largestCity !== null;
    const largestUnnamedMarkup = largestCity === null
        ? `<div class="desktop-meta-only infinity-largest-unnamed">${largestUnnamedText}</div>`
        : `<button id="infinityLargestUnnamed" class="desktop-meta-only infinity-largest-unnamed can-reveal" type="button" title="click to reveal, no points will be added.">${largestUnnamedText}</button>`;
    document.getElementById('meta').innerHTML = `
        <div class="infinity-round-heading">
            <span>Square ${infinityState.currentRound} of ${infinityState.roundCount}</span>
        </div>
        <div class="desktop-meta-only infinity-gameplay-copy">            
        </div>
        <div class="desktop-meta-only infinity-progress-board">
            ${progressItems}
        </div>
        ${largestUnnamedMarkup}
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
    const revealControls = [
        document.getElementById('infinityLargestUnnamed'),
        mobileLargestUnnamed,
    ].filter(Boolean);
    for (const control of revealControls) {
        control.classList.toggle('can-reveal', revealAvailable);
        control.title = !revealAvailable
            ? ''
            : 'click to reveal, no points will be added.';
        control.onclick = !revealAvailable ? null : () => submitGuess(largestCity);
        control.onkeydown = !revealAvailable ? null : event => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                submitGuess(largestCity);
            }
        };
        if (control !== document.getElementById('infinityLargestUnnamed')) {
            control.tabIndex = !revealAvailable ? -1 : 0;
            control.setAttribute('role', !revealAvailable ? 'status' : 'button');
        }
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
            <span class="infinity-chip-score">${numberFmt(guess.score)}</span>
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
    const markers = guessesForCurrentRound().map(guess => ({
            city_name: guess.city_name,
            label: guess.city_name,
            latitude: guess.latitude,
            longitude: guess.longitude,
            pixel_size: 8,
            color: guess.score === 0 ? Cesium.Color.WHITE : Cesium.Color.LIME,
            outline_color: Cesium.Color.BLACK,
            outline_width: 2,
        }));
    drawCities(markers);
}


function renderRound() {
    renderRoundMap(infinityState.square);
    renderMarkers();
    renderInfinityMeta();
    renderSideMission();
    renderChips();
    renderScores();
    const previousButton = document.getElementById('previousBtn');
    const nextButton = document.getElementById('nextBtn');
    previousButton.textContent = 'Previous Square';
    nextButton.textContent = 'Next Square';
    previousButton.style.display = infinityState.currentRound === 1 ? 'none' : 'inline-block';
    nextButton.style.display = infinityState.currentRound === infinityState.roundCount
        ? 'none'
        : 'inline-block';
    previousButton.disabled = infinityState.currentRound === 1;
    nextButton.disabled = infinityState.currentRound === infinityState.roundCount;
    document.getElementById('guessFeedback').innerHTML = '';
    document.getElementById('guessInput').value = '';
    if (!document.getElementById('guessInput').disabled) {
        document.getElementById('guessInput').focus();
    }
}


async function selectRound(roundNumber) {
    const startedAt = performance.now();
    console.info('pool_round: started', {
        mode: infinityState.mode,
        fromRound: infinityState.currentRound,
        toRound: roundNumber,
    });
    try {
        const { response, data } = await selectInfinityRoundRequest(
            roundNumber,
            infinityState.poolSessionId,
        );
        if (!response.ok) {
            throw new Error(data.error);
        }
        validateRoundResponse(data);
        infinityState.currentRound = data.current_round;
        infinityState.square = data.square;
        renderRound();
        console.info('pool_round: completed', {
            mode: infinityState.mode,
            round: infinityState.currentRound,
            elapsedMs: performance.now() - startedAt,
        });
    } catch (error) {
        console.error('pool_round: failed', {
            mode: infinityState.mode,
            fromRound: infinityState.currentRound,
            toRound: roundNumber,
            elapsedMs: performance.now() - startedAt,
            error,
        });
        throw error;
    }
}


function showPoolGuessConfirmation(data) {
    const modal = document.getElementById('guessConflictModal');
    const list = document.getElementById('guessConflictList');
    list.innerHTML = '<div class="modal-title">Did you mean:</div>';
    for (const candidate of data.candidates) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'modal-btn';
        button.textContent = [candidate.city, candidate.province, candidate.country_name]
            .filter(Boolean)
            .join(', ');
        button.onclick = () => {
            modal.classList.add('hidden');
            submitGuess(null, candidate.city_id);
        };
        list.appendChild(button);
    }
    const noneButton = document.createElement('button');
    noneButton.type = 'button';
    noneButton.className = 'modal-btn';
    noneButton.textContent = 'None of these';
    noneButton.onclick = () => {
        modal.classList.add('hidden');
        document.getElementById('guessFeedback').textContent = 'Not in this square.';
        if (data.nearby_city) {
            showIncorrectGuessedCity(data.nearby_city);
        }
        playFail();
    };
    list.appendChild(noneButton);
    modal.classList.remove('hidden');
}


async function submitGuess(revealedCity = null, confirmedCityId = null) {
    const startedAt = performance.now();
    const input = document.getElementById('guessInput');
    const button = document.getElementById('guessBtn');
    const isReveal = revealedCity !== null;
    const guess = isReveal ? '' : input.value.trim();
    if (!guess && !isReveal) {
        return;
    }

    input.disabled = true;
    button.disabled = true;
    console.info('pool_guess: started', {
        mode: infinityState.mode,
        round: infinityState.currentRound,
        confirmedCityId,
    });
    try {
        const { response, data } = await submitInfinityGuessRequest(
            guess,
            infinityState.currentRound,
            isReveal ? revealedCity.city_id : null,
            infinityState.poolSessionId,
            confirmedCityId,
        );
        if (!response.ok) {
            throw new Error(data.error);
        }
        validateSubmitResponse(data);
        if (data.requires_confirmation === true) {
            console.info('pool_guess: confirmation required', {
                mode: infinityState.mode,
                round: infinityState.currentRound,
                candidateCount: data.candidates.length,
            });
            showPoolGuessConfirmation(data);
            return;
        }
        if (!data.correct) {
            console.info('pool_guess: incorrect', {
                mode: infinityState.mode,
                round: infinityState.currentRound,
            });
            document.getElementById('guessFeedback').textContent = 'Not in this square.';
            if ('matched_city' in data) {
                showIncorrectGuessedCity(data.matched_city);
            }
            playFail();
            return;
        }
        if (data.duplicate) {
            console.info('pool_guess: duplicate', {
                mode: infinityState.mode,
                round: infinityState.currentRound,
                cities: data.duplicates,
            });
            document.getElementById('guessFeedback').textContent = `${data.duplicates.join(', ')} already in your pool.`;
            return;
        }

        const previousRoundScore = infinityState.roundScores[infinityState.currentRound] || 0;
        const previousTotalScore = infinityState.totalScore;
        const previousMission = currentSideMission();
        const previousNamedTargets = new Set(previousMission?.progress.named || []);
        infinityState.roundScores[infinityState.currentRound] = data.round_score;
        infinityState.totalScore = data.total_score;
        infinityState.sideMissions = data.side_missions.missions;
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
            color: acceptedGuess.score === 0 ? Cesium.Color.WHITE : Cesium.Color.LIME,
            outline_color: Cesium.Color.BLACK,
            outline_width: 2,
        })));
        renderInfinityMeta();
        renderChips(data.guesses.map(acceptedGuess => acceptedGuess.city_id));
        renderScores(previousRoundScore, previousTotalScore);
        renderSideMission();
        const acceptedNames = data.guesses.map(acceptedGuess => acceptedGuess.city).join(', ');
        const awardedScore = data.guesses.reduce(
            (total, acceptedGuess) => total + acceptedGuess.score,
            0,
        );
        const duplicateText = data.duplicates.length
            ? `<br>${escapeHtml(data.duplicates.join(', '))} already in your pool.`
            : '';
        const mission = currentSideMission();
        const newlyNamedTargets = mission?.progress.named.filter(
            name => !previousNamedTargets.has(name),
        ) || [];
        const scoreFeedback = isReveal
            ? `<b>${escapeHtml(acceptedNames)}</b> revealed`
            : `<b>${escapeHtml(acceptedNames)}</b> +${numberFmt(awardedScore)}${duplicateText}`;
        const acknowledgements = newlyNamedTargets.map(
            name => mission.progress.acknowledgements[name],
        );
        const acknowledgementMarkup = acknowledgements.length > 0
            ? `<div id="sideMissionAcknowledgement" class="side-mission-success">${acknowledgements.map(
                acknowledgement => `<strong>${escapeHtml(acknowledgement)}</strong>`,
            ).join('')}</div>`
            : '';
        document.getElementById('guessFeedback').innerHTML = `
            <div>${scoreFeedback}</div>
            ${acknowledgementMarkup}
        `;
        if (sideMissionAcknowledgementTimer !== null) {
            window.clearTimeout(sideMissionAcknowledgementTimer);
        }
        if (acknowledgements.length > 0) {
            sideMissionAcknowledgementTimer = window.setTimeout(() => {
                document.getElementById('sideMissionAcknowledgement')?.remove();
                sideMissionAcknowledgementTimer = null;
            }, SIDE_MISSION_ACKNOWLEDGEMENT_MS);
        }
        if (!isReveal) {
            input.value = '';
            playSuccess();
        }
        console.info('pool_guess: completed', {
            mode: infinityState.mode,
            round: infinityState.currentRound,
            acceptedCities: data.guesses.map(acceptedGuess => acceptedGuess.city),
            roundScore: data.round_score,
            totalScore: data.total_score,
            missionProgress: mission ? mission.progress : null,
            elapsedMs: performance.now() - startedAt,
        });
        if (previousMission?.completed_at === null && mission?.completed_at !== null) {
            console.info('side_mission: completed', {
                round: mission.round_number,
                missionId: mission.mission_id,
                progress: mission.progress,
            });
        }
    } catch (error) {
        console.error('pool_guess: failed', {
            mode: infinityState.mode,
            round: infinityState.currentRound,
            elapsedMs: performance.now() - startedAt,
            error,
        });
        throw error;
    } finally {
        input.disabled = false;
        button.disabled = false;
        if (isReveal) {
            renderInfinityMeta();
        }
        input.focus();
    }
}


export async function enterInfinityMode(poolSessionId = null, requestedRound = null) {
    const startedAt = performance.now();
    console.info('infinity_mode: started', { poolSessionId, requestedRound });
    const { response, data } = await fetchInfinityState(poolSessionId);
    if (!response.ok) {
        throw new Error(data.error);
    }
    validateInfinityStateResponse(data);
    document.getElementById('statsOverlay').style.display = 'none';
    setPoolLayout();
    infinityState.poolSessionId = data.infinity_pool_session_id;
    infinityState.currentRound = data.current_round;
    infinityState.roundCount = data.round_count;
    infinityState.roundScores = data.round_scores;
    infinityState.totalScore = data.total_score;
    infinityState.guesses = data.guesses;
    infinityState.square = data.square;
    infinityState.sideMissions = data.side_missions.missions;
    document.getElementById('guessInput').disabled = false;
    document.getElementById('guessBtn').disabled = false;
    if (requestedRound !== null && requestedRound !== infinityState.currentRound) {
        await selectRound(requestedRound);
    } else {
        renderRound();
    }
    console.info('infinity_mode: completed', {
        poolSessionId: infinityState.poolSessionId,
        round: infinityState.currentRound,
        guessCount: infinityState.guesses.length,
        totalScore: infinityState.totalScore,
        elapsedMs: performance.now() - startedAt,
    });
}


async function startSideMissions() {
    const startedAt = performance.now();
    console.info('side_missions: start requested', {
        currentPoolSessionId: infinityState.poolSessionId,
        currentRound: infinityState.currentRound,
    });
    try {
        const { response: startResponse, data: startData } = await startSideMissionsRequest();
        if (!startResponse.ok) {
            throw new Error(startData.error);
        }
        requireInteger(
            startData.infinity_pool_session_id,
            'side_missions_start.infinity_pool_session_id',
        );
        validateSideMissionState(startData.side_missions, 'side_missions_start.side_missions');
        console.info('side_missions: assignments loaded', {
            poolSessionId: startData.infinity_pool_session_id,
            missions: startData.side_missions.missions.map(mission => ({
                round: mission.round_number,
                missionId: mission.mission_id,
                progress: mission.progress,
                completed: mission.completed_at !== null,
            })),
        });

        await enterInfinityMode(startData.infinity_pool_session_id);
        console.info('side_missions: ready', {
            poolSessionId: infinityState.poolSessionId,
            round: infinityState.currentRound,
            elapsedMs: performance.now() - startedAt,
        });
    } catch (error) {
        console.error('side_missions: failed', {
            elapsedMs: performance.now() - startedAt,
            error,
        });
        throw error;
    }
}


export function isInfinityModeActive() {
    return infinityState.active;
}


async function handleEnterInfinityClick() {
    const startedAt = performance.now();
    try {
        await enterInfinityMode();
    } catch (error) {
        console.error('infinity_mode: failed', {
            elapsedMs: performance.now() - startedAt,
            error,
        });
    }
}


function setSideMissionAvailability(availability) {
    requireObject(availability, 'side_mission_availability');
    requireBoolean(availability.available, 'side_mission_availability.available');
    requireBoolean(availability.started, 'side_mission_availability.started');
    validateStringArray(availability.reasons, 'side_mission_availability.reasons');
    console.info('side_missions: availability evaluated', availability);
    infinityState.sideMissionsAvailable = availability.available;
    document.getElementById('sideMissionsInvite').classList.toggle(
        'hidden',
        !availability.available,
    );
}


function handleEnterSideMissionsClick() {
    startSideMissions().catch(error => {
        console.error('Side Missions mode failed:', error);
    });
}


export function unlockInfinityMode(sideMissionAvailability) {
    const infinityButton = document.getElementById('infinityModeBtn');
    document.getElementById('gameModeSwitch').classList.remove('hidden');
    infinityButton.disabled = false;
    infinityButton.removeAttribute('title');
    document.getElementById('statsInfinityInvite').classList.remove('hidden');
    setSideMissionAvailability(sideMissionAvailability);
}


export function initInfinityMode(dailyCompleted, sideMissionAvailability, callbacks) {
    const infinityButton = document.getElementById('infinityModeBtn');
    showDailyRound = callbacks.showDailyRound;
    showSummary = callbacks.showSummary;
    infinityButton.disabled = !dailyCompleted;
    if (!dailyCompleted) {
        infinityButton.title = 'Complete the Daily game to unlock Infinity Pool';
    }

    document.getElementById('dailyModeBtn').onclick = () => {
        document.getElementById('statsOverlay').style.display = 'none';
        setDailyLayout();
        showDailyRound(infinityState.currentRound);
    };
    infinityButton.onclick = handleEnterInfinityClick;
    document.getElementById('sideMissionsInviteBtn').onclick = handleEnterSideMissionsClick;
    document.getElementById('statsInfinityInviteBtn').onclick = handleEnterInfinityClick;
    document.getElementById('summaryBtn').onclick = () => showSummary();
    document.getElementById('previousBtn').onclick = () => selectRound(
        infinityState.currentRound - 1,
    );
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
        unlockInfinityMode(sideMissionAvailability);
    }
    setModeButtons();

    const params = new URLSearchParams(window.location.search);
    const poolSessionId = Number.parseInt(params.get('infinity_pool_session_id'), 10);
    const requestedRound = Number.parseInt(params.get('round'), 10);
    if (Number.isInteger(poolSessionId) && poolSessionId > 0) {
        unlockInfinityMode();
        enterInfinityMode(
            poolSessionId,
            Number.isInteger(requestedRound) ? requestedRound : null,
        ).catch(error => {
            console.error('Infinity mode failed:', error);
        });
    }
}