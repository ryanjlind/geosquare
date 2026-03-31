import { gameState } from './state.js';
import { postClientLog } from './utils.js';
import { fetchGameState, fetchRound, submitGuessRequest, submitPassRequest } from './api.js';
import { getSfxCtx, warmUpSfx, playSuccess, playFail, playComplete, playPerfect } from './audio.js';
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
import { initFeedback } from './feedback.js';

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

    gameState.currentRound += 1;

    if (gameState.currentRound > 5) {        
        setGuessControlsEnabled(false);
        await showEndGameSummary();
        return;
    }

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
        alert('submit_guess_skipped_disabled');
        return;
    }

    guessBtn.disabled = true;
    guessInput.disabled = true;

    try {
        alert('submit_guess_start');
        await postClientLog('submit_guess_start', {
            round: gameState.currentRound
        });

        const guess = getGuessValue();
        alert('submit_guess_before_warmup');
        await postClientLog('submit_guess_before_warmup', {
            round: gameState.currentRound,
            guess: guess
        });

        await warmUpSfx();

        alert('submit_guess_after_warmup');
        await postClientLog('submit_guess_after_warmup', {
            round: gameState.currentRound,
            guess: guess
        });
        alert('submit_guess_before_request');
        await postClientLog('submit_guess_before_request', {
            round: gameState.currentRound,
            guess: guess
        });

        const { data } = await submitGuessRequest(guess, gameState.currentRound);

        await postClientLog('submit_guess_after_request', {
            round: gameState.currentRound,
            guess: guess,
            correct: !!data.correct,
            has_matched_city: !!data.matched_city
        });

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
        await postClientLog('submit_guess_finally', {
            round: gameState.currentRound
        });

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
    if (state.completed_at) {
        setGuessControlsEnabled(false);
        hideNextButton();
        setGuessBoxVisible(false);        
        await showEndGameSummary();
    }
}