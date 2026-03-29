import { gameState } from './state.js';
import { fetchGameState, fetchRound, submitGuessRequest, submitPassRequest } from './api.js';
import { getSfxCtx, warmUpSfx, playSuccess, playFail } from './audio.js';
import { initCesium, renderRoundMap, drawCities, showGuessedCity, showIncorrectGuessedCity } from './map.js';
import {
    setMetaError,
    renderSidebar,
    restoreSavedState,
    setGuessBoxVisible,
    setGuessControlsEnabled,
    hideNextButton,
    showNextButton,
    setGuessFeedback,
    clearGuessInput,
    getGuessValue,
    focusGuessInput,
    addRoundRow,
} from './ui.js';
import { wireStatsOverlay, showEndGameSummary } from './stats.js';
import { escapeHtml, numberFmt, ordinal } from './utils.js';

function renderRound(data) {
    renderSidebar(data);
    renderRoundMap(data);
}

function wireGuessing() {
    const input = document.getElementById('guessInput');
    const btn = document.getElementById('guessBtn');
    const passBtn = document.getElementById('passBtn');

    btn.onpointerdown = warmUpSfx;
    input.onpointerdown = warmUpSfx;
    passBtn.onpointerdown = warmUpSfx;

    btn.onclick = submitGuess;
    input.onkeydown = handleGuessKeyDown;
}

function wireRoundButtons() {
    document.getElementById('nextBtn').onclick = handleNextRound;
    document.getElementById('passBtn').onclick = handlePass;
}

function handleGuessKeyDown(e) {
    if (e.key === 'Enter') {
        submitGuess();
    }
}

export async function handleNextRound() {
    hideNextButton();

    gameState.currentRound += 1;

    if (gameState.currentRound > 5) {
        hideNextButton();
        setGuessControlsEnabled(false);
        await showEndGameSummary();
        return;
    }

    const data = await fetchRound(gameState.currentRound);
    renderRound(data);
    gameState.roundLocked = false;
}

export async function handlePass() {
    gameState.roundLocked = true;
    getSfxCtx();

    const { response, data } = await submitPassRequest(gameState.currentRound);

    if (!response.ok) {
        setGuessFeedback(escapeHtml(data.error || 'Pass failed.'));
        gameState.roundLocked = false;
        return;
    }

    const largestCity = data.largest_city;

    setGuessFeedback(`No guess submitted.<br>
        Largest city: <b>${escapeHtml(largestCity.city_name)}</b><br>
        Population: ${numberFmt(largestCity.population)}<br>
        Points awarded: <b>0</b>`);

    addRoundRow({
        city: '—',
        population: 0,
        rank: '—',
        score: 0
    }, gameState.currentRound);

    drawCities([largestCity]);
    playFail();

    if (gameState.currentRound === 5) {
        await showEndGameSummary();
    } else {
        showNextButton(gameState.currentRound);
    }

    clearGuessInput();
    setGuessBoxVisible(false);
}

export async function submitGuess() {
    getSfxCtx();

    const guess = getGuessValue();
    const { data } = await submitGuessRequest(guess, gameState.currentRound);

    if (data.correct) {
        gameState.roundLocked = true;

        setGuessFeedback(`<b>${escapeHtml(data.city.toUpperCase())}</b> is the ${data.rank === 1 ? 'largest' : `${ordinal(data.rank)} largest`} city in the square.<br><br>
        With a population of ${numberFmt(data.population)}, you are awarded <b>${numberFmt(data.score)}</b> points.<br>`);

        showGuessedCity(data);
        addRoundRow(data, gameState.currentRound);
        playSuccess();
        clearGuessInput();
        setGuessBoxVisible(false);

        if (gameState.currentRound === 5) {
            await showEndGameSummary();
        } else {
            showNextButton(gameState.currentRound);
        }

        return;
    }

    setGuessFeedback('<br>Not in the square or population < 15,000');

    if (data.matched_city) {
        showIncorrectGuessedCity(data.matched_city);
    }

    playFail();
    focusGuessInput();
}

export async function initGame() {
    await initCesium();
    wireStatsOverlay();

    const { response: stateResponse, data: state } = await fetchGameState();

    if (!stateResponse.ok) {
        setMetaError(state.error);
        return;
    }

    const data = await fetchRound(state.round_number || 1);

    gameState.currentRound = data.round_number;
    console.log('[DEBUG] init:before-load', { currentRound: gameState.currentRound });
    gameState.roundLocked = false;

    renderRound(data);
    const { currentRoundCompleted } = restoreSavedState(state);
    wireGuessing();
    wireRoundButtons();

    if (currentRoundCompleted) {
        gameState.roundLocked = true;
    }

    if (state.completed_at) {
        setGuessControlsEnabled(false);
        hideNextButton();
        setGuessBoxVisible(false);
        gameState.roundLocked = true;
        await showEndGameSummary();
    }
}