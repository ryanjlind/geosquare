import { gameState } from './state.js';
import { postClientLog, escapeHtml, numberFmt, ordinal } from './utils.js';
import { fetchGameState, fetchRound, fetchAllDailySquares, submitGuessRequest, submitPassRequest, setDifficultyRequest } from './api.js';
import { getSfxCtx, playSuccess, playFail, playComplete, playPerfect } from './audio.js';
import {
    initCesium,
    renderRoundMap,
    renderAllSquares,
    renderEndGameRound,
    drawCities,
    showGuessedCity,
    showIncorrectGuessedCity,
    handleExpand,
    updateExpandButton,
    renderDifficultyLayer,
    clearDifficultyLayer,
} from './map.js';
import {
    setMetaError,
    renderSidebar,
    setDifficultyVisible,
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
    wireRoundTable,
    wireShareScoreButton,
    setShareButtonReady,
    setSelectedRoundRow,
    showAuthConflictModal,
    hideAuthConflictModal,
    wireAuthConflictModal,
    adjustPopulationDisplay
} from './ui.js';
import { wireStatsOverlay, showEndGameSummary, shareCurrentGameScore, hydrateShareFromState, recordShareRound, isShareReady, renderEndGameFeedbackFromState } from './stats.js';
import { initFeedback } from './feedback.js';
import { initAuth, resolveAuthConflict } from './auth.js';
import { expandSquareRequest } from './api.js';
import { drawSquare } from './map.js';

let endGameRounds = [];

const DIFFICULTY_KEY = 'geosquare_difficulty';
const DIFFICULTY_SLIDER_ENABLED = Boolean(window.GEOSQUARE_FLAGS?.difficultySliderEnabled);
let currentRoundData = null;
let currentRoundDbLevel = 1;

function getStoredDifficulty() {
    return parseInt(localStorage.getItem(DIFFICULTY_KEY) || '5', 10);
}

function setStoredDifficulty(level) {
    localStorage.setItem(DIFFICULTY_KEY, String(level));
}

// UI value 5 = rightmost = hardest = backend level 1
function uiToBackendLevel(uiValue) {
    return 6 - uiValue;
}

function updateSliderFill(slider) {
    const pct = ((slider.value - slider.min) / (slider.max - slider.min)) * 100;
    slider.style.background = [
        `linear-gradient(to right, rgba(255,255,255,0.7) 0 ${pct}%, rgba(255,255,255,0.15) ${pct}% 100%)`,
        'repeating-linear-gradient(to right, transparent 0 calc(20% - 1px), rgba(255,255,255,0.28) calc(20% - 1px) 20%)'
    ].join(', ');
}

function wireDifficultySlider(roundData) {
    if (!DIFFICULTY_SLIDER_ENABLED) {
        clearDifficultyLayer();
        return;
    }

    const row = document.getElementById('difficultyRow');
    const slider = document.getElementById('difficultySlider');
    const helpBtn = document.getElementById('difficultyHelpBtn');
    const tooltipBox = document.getElementById('difficultyTooltipBox');
    if (!slider || !row || row.classList.contains('hidden')) return;

    const storedUi = getStoredDifficulty();
    slider.value = String(storedUi);
    updateSliderFill(slider);
    const backendLevel = uiToBackendLevel(storedUi);

    if (backendLevel > 1) {
        setDifficultyRequest(roundData.round_number, backendLevel).catch(() => {});
        currentRoundDbLevel = backendLevel;
        renderDifficultyLayer(roundData, backendLevel);
    } else {
        currentRoundDbLevel = 1;
        clearDifficultyLayer();
    }

    slider.oninput = async (e) => {
        const uiValue = parseInt(e.target.value, 10);
        setStoredDifficulty(uiValue);
        updateSliderFill(slider);
        const newBackendLevel = uiToBackendLevel(uiValue);
        renderDifficultyLayer(roundData, newBackendLevel);

        if (newBackendLevel > currentRoundDbLevel) {
            currentRoundDbLevel = newBackendLevel;
            await setDifficultyRequest(roundData.round_number, newBackendLevel).catch(() => {});
        }
    };

    if (helpBtn && tooltipBox) {
        helpBtn.onclick = (e) => {
            e.stopPropagation();
            tooltipBox.classList.toggle('visible');
        };
        document.addEventListener('click', () => tooltipBox.classList.remove('visible'), { once: false });
    }
}

function renderRound(data) {
    currentRoundData = data;
    currentRoundDbLevel = 1;
    setDifficultyVisible(DIFFICULTY_SLIDER_ENABLED && !gameState.gameCompleted);
    renderSidebar(data);
    renderRoundMap(data);
    updateExpandButton(data);
    wireDifficultySlider(data);

    const guessInput = document.getElementById('guessInput');

    if (guessInput) {
        guessInput.focus();
        guessInput.select();
    }
}

async function loadEndGameRounds() {
    endGameRounds = await fetchAllDailySquares();
    await renderAllSquares(endGameRounds);
}

function handleEndGameRoundSelect(roundNumber) {
    if (!endGameRounds.length) {
        return;
    }

    setSelectedRoundRow(roundNumber);
    renderEndGameRound(endGameRounds, roundNumber);
}

async function enterEndGameGlobe() {
    setGuessControlsEnabled(false);
    setGuessBoxVisible(false);
    setShareButtonReady(isShareReady());
    showNextButton(5);
    await loadEndGameRounds();
    setSelectedRoundRow(5);
}

function wireGuessing() {
    const input = document.getElementById('guessInput');
    const btn = document.getElementById('guessBtn');

    btn.onclick = submitGuess;
    input.onkeydown = handleGuessKeyDown;
}

function wireRoundButtons() {
    document.getElementById('nextBtn').onclick = handleNextRound;
    document.getElementById('passBtn').onclick = handlePass;
    wireShareScoreButton(shareCurrentGameScore);
}

function wireExpandButton() {
    const btn = document.getElementById('expandBtn');
    btn.onclick = handleExpand;
}

function handleGuessKeyDown(e) {
    if (e.key === 'Enter') {
        submitGuess();
    }
}

export async function handleNextRound() {
    const nextBtn = document.getElementById('nextBtn');

    if (nextBtn.disabled) {
        return;
    }

    nextBtn.disabled = true;

    try {
        if (gameState.currentRound >= 5) {
            gameState.currentRound = 5;            
            await showEndGameSummary();
            return;
        }

        gameState.currentRound += 1;

        const data = await fetchRound(gameState.currentRound);
        renderRound(data);
        gameState.roundLocked = false;
        document.getElementById('passBtn').disabled = false;
        hideNextButton();
    } finally {
        nextBtn.disabled = false;
    }
}

export async function handlePass() {
    document.getElementById('passBtn').disabled = true;
    gameState.roundLocked = true;
    getSfxCtx();

    gameState.isPerfect = false;

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
    recordShareRound({
        city: '—',
        rank: '—',
        score: 0
    }, gameState.currentRound);
    adjustPopulationDisplay();

    drawCities([largestCity]);
    playFail();

    clearGuessInput();
    setGuessBoxVisible(false);

    if (gameState.currentRound === 5) {
        await enterEndGameGlobe();
        return;
    }

    showNextButton(gameState.currentRound);
}

export async function submitGuess(confirmedCityId = null) {
    const guessBtn = document.getElementById('guessBtn');
    const guessInput = document.getElementById('guessInput');    

    guessBtn.disabled = true;
    guessInput.disabled = true;

    const guess = getGuessValue();

    try {
        const { data } = await submitGuessRequest(
            guess,
            gameState.currentRound,
            confirmedCityId,
        );

        if (data.requires_confirmation) {
            window.pendingGuessConfirmation = {
                guess,
                round: gameState.currentRound,
                candidates: data.candidates,
                nearbyCity: data.nearby_city || null
            };

            if (typeof showGuessConfirmationModal === "function") {
                showGuessConfirmationModal(data.candidates, data.nearby_city || null);
            }

            return;
        }

        if (data.correct) {
            const expansionLevel = data.expansion_level || 0;

            let expansionText = "";

            if (expansionLevel > 0) {
                const penalty = expansionLevel * 20;
                expansionText = ` and a -${penalty}% expansion penalty`;
            }

            setGuessFeedback(
                `<b>${escapeHtml(data.city.toUpperCase())}</b> is the ${data.rank === 1 ? 'largest' : `${ordinal(data.rank)} largest`} city in the square.<br><br>
                With a population of ${numberFmt(data.population)}${expansionText}, you are awarded <b>${numberFmt(data.score)}</b> points.<br>`
            );

            showGuessedCity(data);
            addRoundRow(data, gameState.currentRound);
            recordShareRound(data, gameState.currentRound);
            adjustPopulationDisplay();
            clearGuessInput();
            setGuessBoxVisible(false);

            if (gameState.currentRound === 5) {
                if (gameState.isPerfect) playPerfect();
                else playComplete();

                await enterEndGameGlobe();
                return;
            }

            playSuccess();
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

    Object.assign(gameState, state);

    if (!stateResponse.ok) {
        setMetaError(state.error);
        return;
    }

    const data = await fetchRound(state.round_number || 1);

    gameState.currentRound = data.round_number;
    gameState.isPerfect = state.is_perfect;
    gameState.roundLocked = false;
    gameState.gameCompleted = Boolean(state.completed_at);
    hydrateShareFromState(state);

    if (state.completed_at) {
        setDifficultyVisible(false);
    }

    renderRound(data);
    restoreSavedState(state);
    adjustPopulationDisplay();
    wireGuessing();
    wireRoundButtons();
    wireExpandButton();
    document.addEventListener('squareExpanded', (e) => {
        updateExpandButton(e.detail);
    });
    wireRoundTable(handleEndGameRoundSelect);
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
        renderEndGameFeedbackFromState(state);
        await enterEndGameGlobe();
    }
}

export function showGuessConfirmationModal(candidates, nearbyCity) {
    const modal = document.getElementById('guessConflictModal');
    const list = document.getElementById('guessConflictList');

    list.innerHTML = '';

    const title = document.createElement('div');
    title.className = 'modal-title';
    title.textContent = 'Did you mean:';
    list.appendChild(title);

    candidates.forEach(c => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'modal-btn';
        btn.textContent = `${c.city} (${c.country_code})`;

        btn.onclick = async () => {
            modal.classList.add('hidden');

            const pending = window.pendingGuessConfirmation;
            if (!pending) return;

            const guessBtn = document.getElementById('guessBtn');
            const guessInput = document.getElementById('guessInput');

            guessBtn.disabled = true;
            guessInput.disabled = true;

            try {
                guessInput.value = `${c.city}, ${c.country_code}`;
                await submitGuess(c.city_id);
                window.pendingGuessConfirmation = null;
            } finally {
                guessBtn.disabled = false;
                guessInput.disabled = false;
                focusGuessInput();
            }
        };

        list.appendChild(btn);
    });

    const noneBtn = document.createElement('button');
    noneBtn.type = 'button';
    noneBtn.className = 'modal-btn';
    noneBtn.textContent = 'None of these';

    noneBtn.onclick = () => {
        modal.classList.add('hidden');
        window.pendingGuessConfirmation = null;
        setGuessFeedback('<br>Not in the square or population < 15,000');

        if (nearbyCity) {
            showIncorrectGuessedCity(nearbyCity);
        }

        playFail();
        focusGuessInput();
    };

    list.appendChild(noneBtn);

    modal.classList.remove('hidden');
}