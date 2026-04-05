import { numberFmt, escapeHtml, parseFormattedInt } from './utils.js';

export function setMetaError(message) {
    document.getElementById('meta').innerHTML = `<div class="value">${escapeHtml(message)}</div>`;
}

export function renderSidebar(data) {
    const meta = document.getElementById('meta');

    meta.innerHTML = `
        <div class="desktop-meta-only">
            <div class="label">Round</div>
            <div class="value">${data.round_number} / 5</div>

            <div class="label">Population in square</div>
            <div class="value">${numberFmt(data.total_population)}</div>

            <div class="label">Cities in square</div>
            <div class="value" data-mobile-cities-value>${numberFmt(data.total_city_count)}</div>

            <div class="label">Largest city population</div>
            <div class="value">${numberFmt(data.largest_city.population)}</div>
        </div>

        <div class="label">Gameplay</div>
        <div class="value">
            Try to name a city in each square. It is perfectly acceptable to "Pass" a round if you don't know any!<br><br>    
            Squares have a minimum total population of ${numberFmt(data.rules.min_total_population)}.<br><br>
            At least ${numberFmt(data.rules.min_city_count)} cities have a population ≥ ${numberFmt(data.rules.min_city_population)}.<br><br>            
            The smaller the city you can name, the more points you will receive. <br><br>
            Includes most (not all) cities ≥ 15,000 population.
        </div>
    `;

    setGuessBoxVisible(true);
    clearGuessInput();
    clearGuessFeedback();
}

export function clearRoundTable() {
    document.querySelector('#roundTable tbody').innerHTML = '';
    document.getElementById('totalPoints').textContent = '0';
}

export function clearGuessFeedback() {
    document.getElementById('guessFeedback').innerHTML = '';
}

export function setGuessFeedback(html) {
    document.getElementById('guessFeedback').innerHTML = html;
}

export function clearGuessInput() {
    document.getElementById('guessInput').value = '';
}

export function focusGuessInput() {
    document.getElementById('guessInput').focus();
}

export function getGuessValue() {
    return document.getElementById('guessInput').value.trim();
}

export function setGuessBoxVisible(isVisible) {
    document.getElementById('guessBox').style.display = isVisible ? 'block' : 'none';
}

export function setGuessControlsEnabled(isEnabled) {
    document.getElementById('guessInput').disabled = !isEnabled;
    document.getElementById('guessBtn').disabled = !isEnabled;
}

export function hideNextButton() {
    document.getElementById('nextBtn').style.display = 'none';
}

export function showNextButton(currentRound) {
    const btn = document.getElementById('nextBtn');
    btn.textContent = currentRound === 5 ? 'Show Summary' : 'Next Round';
    btn.style.display = 'inline-block';
}

export function addRoundRow(result, roundNumber) {
    const tbody = document.querySelector('#roundTable tbody');
    const totalEl = document.getElementById('totalPoints');
    const tr = document.createElement('tr');

    tr.dataset.roundNumber = String(roundNumber);

    tr.innerHTML = `
        <td>${roundNumber}</td>
        <td><span class="round-city">${escapeHtml(result.city)}</span></td>
        <td>${numberFmt(result.population)}</td>
        <td>${result.rank}</td>
        <td>${numberFmt(result.score)}</td>
    `;

    tbody.appendChild(tr);

    const currentTotal = parseFormattedInt(totalEl.textContent);
    totalEl.textContent = numberFmt(currentTotal + result.score);
}

export function wireRoundTable(onRoundSelect) {
    const tbody = document.querySelector('#roundTable tbody');

    tbody.onclick = (e) => {
        const row = e.target.closest('tr[data-round-number]');
        if (!row) {
            return;
        }

        onRoundSelect(Number(row.dataset.roundNumber));
    };
}

export function setSelectedRoundRow(roundNumber) {
    const rows = document.querySelectorAll('#roundTable tbody tr');

    rows.forEach((row) => {
        row.classList.toggle('selected', Number(row.dataset.roundNumber) === roundNumber);
    });
}

export function restoreSavedState(state) {
    clearRoundTable();
    clearGuessFeedback();

    for (const round of (state.completed_rounds || [])) {
        const guess = round.guesses && round.guesses.length ? round.guesses[0] : null;

        addRoundRow({
            city: guess ? guess.city_name : '—',
            population: guess ? (guess.population ?? 0) : 0,
            rank: guess ? (guess.rank ?? '—') : '—',
            score: round.score ?? 0
        }, round.round_number);
    }

    if (state.completed_at) {
        setGuessBoxVisible(false);
        showNextButton(5);
        return;
    }

    setGuessBoxVisible(true);
}
export function showAuthConflictModal(message) {
    const modal = document.getElementById('authConflictModal');
    const body = document.getElementById('authConflictMessage');

    if (body) {
        body.textContent = message;
    }

    if (modal) {
        modal.classList.remove('hidden');
    }
}

export function hideAuthConflictModal() {
    const modal = document.getElementById('authConflictModal');

    if (modal) {
        modal.classList.add('hidden');
    }
}

export function wireAuthConflictModal({ onDiscard, onOverwrite, onAbort }) {
    const discardBtn = document.getElementById('conflictDiscardBtn');
    const overwriteBtn = document.getElementById('conflictOverwriteBtn');
    const abortBtn = document.getElementById('conflictAbortBtn');

    if (discardBtn) discardBtn.onclick = onDiscard;
    if (overwriteBtn) overwriteBtn.onclick = onOverwrite;
    if (abortBtn) abortBtn.onclick = onAbort;
}