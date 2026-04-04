import { gameState } from './state.js';
import { postClientLog, escapeHtml, numberFmt, ordinal } from './utils.js';
import { fetchGameState, fetchRound, submitGuessRequest, submitPassRequest } from './api.js';
import { getSfxCtx, playSuccess, playFail, playComplete, playPerfect } from './audio.js';
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
    showAuthConflictModal,
    hideAuthConflictModal,
    wireAuthConflictModal,
} from './ui.js';
import { wireStatsOverlay, showEndGameSummary } from './stats.js';
import { initFeedback } from './feedback.js';
import { initAuth, resolveAuthConflict } from './auth.js';

let latestGameState = null;

function renderRound(data) {
    renderSidebar(data);
    renderRoundMap(data);
}

function wireGuessing() {
    const input = document.getElementById('guessInput');
    const btn = document.getElementById('guessBtn');
    const passBtn = document.getElementById('passBtn');

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

    if (gameState.currentRound >= 5) {
        gameState.currentRound = 5;
        setGuessControlsEnabled(false);
        await showEndGameSummary();
        return;
    }

    gameState.currentRound += 1;

    const data = await fetchRound(gameState.currentRound);
    renderRound(data);
    gameState.roundLocked = false;
    document.getElementById('passBtn').disabled = false;
    hideNextButton();
}

export async function handlePass() {
    document.getElementById('passBtn').disabled = true;
    gameState.roundLocked = true;
    getSfxCtx();
    
    gameState.isPerfect = false 

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

    showNextButton(gameState.currentRound);    

    clearGuessInput();
    setGuessBoxVisible(false);
}

export async function submitGuess() {    
    
    const guessBtn = document.getElementById('guessBtn');
    const guessInput = document.getElementById('guessInput');

    if (guessBtn.disabled) {        
        return;
    }

    guessBtn.disabled = true;
    guessInput.disabled = true;
    const guess = getGuessValue();
    try {        
        const { data } = await submitGuessRequest(guess, gameState.currentRound);

        if (data.correct) {
            setGuessFeedback(`<b>${escapeHtml(data.city.toUpperCase())}</b> is the ${data.rank === 1 ? 'largest' : `${ordinal(data.rank)} largest`} city in the square.<br><br>
            With a population of ${numberFmt(data.population)}, you are awarded <b>${numberFmt(data.score)}</b> points.<br>`);

            showGuessedCity(data);
            addRoundRow(data, gameState.currentRound);
            clearGuessInput();
            setGuessBoxVisible(false);

            if (gameState.currentRound === 5) {
                if (gameState.isPerfect) playPerfect();
                else playComplete();
            } else {
                playSuccess();
            }

            showNextButton(gameState.currentRound);
            return;
        }

        setGuessFeedback('<br>Not in the square or population < 15,000');

        if (data.matched_city) {
            showIncorrectGuessedCity(data.matched_city);
        }

        playFail();
    } catch (err) {
        await postClientLog('submit_guess_error', {
            round: gameState.currentRound,
            message: err?.message || String(err),
            stack: err?.stack || null
        });
        throw err;
    } finally {
        guessBtn.disabled = false;
        guessInput.disabled = false;
        focusGuessInput();
    }
}

export async function initGame() {
    await initCesium();
    wireStatsOverlay();

    const { response: stateResponse, data: state } = await fetchGameState();

    if (!stateResponse.ok) {
        setMetaError(state.error);
        return;
    }

    latestGameState = state;

    const data = await fetchRound(state.round_number || 1);

    gameState.currentRound = data.round_number;
    gameState.isPerfect = state.is_perfect;
    console.log('[DEBUG] init:before-load', { gameState: gameState });
    gameState.roundLocked = false;
    renderRound(data);
    restoreSavedState(state);
    wireGuessing();
    wireRoundButtons();
    initFeedback();
    initAuth(state, {
        onAuthSuccess: async () => {
            window.location.reload();
        },
        onAuthConflict: (message) => {
            showAuthConflictModal(message);
        },
        onAuthError: (message) => {
            console.log(message || 'Login failed.');
        },
    });

    wireAuthConflictModal({
        onDiscard: () => resolveAuthConflict('discard_this_device_conflicts').then(hideAuthConflictModal),
        onOverwrite: () => resolveAuthConflict('overwrite_profile').then(hideAuthConflictModal),
        onAbort: () => resolveAuthConflict('abort').then(hideAuthConflictModal),
    });

    if (state.completed_at) {
        setGuessControlsEnabled(false);
        setGuessBoxVisible(false);
        showNextButton(5);
        await showEndGameSummary();
    }
}