import { numberFmt, abbreviateNumber, abbreviatePopulationForDisplay, escapeHtml } from '@geosquare/utils.js';
import { fetchJson } from '@geosquare/api.js';

let historyOffset = 0;
let historyHasMore = false;
let regionPerformanceSummary = [];

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) {
        el.textContent = value;
    }
}

function showElement(id) {
    document.getElementById(id).classList.remove('hidden');
}

function hideElement(id) {
    document.getElementById(id).classList.add('hidden');
}

function formatDate(dateString) {
    if (!dateString) {
        return '—';
    }

    const date = new Date(`${dateString}T00:00:00`);
    return date.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    });
}

function formatDateTime(dateString) {
    if (!dateString) {
        return '—';
    }

    const date = new Date(dateString);
    return date.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
    });
}

function formatScoreWithPenalty(score, expansionLevel) {
    const penalty = expansionLevel ? ` <span class="stats-expansion-penalty">[-${expansionLevel * 20}%]</span>` : '';
    return `${numberFmt(score)}${penalty}`;
}

function formatBestRound(bestRound) {
    if (!bestRound) {
        return '—';
    }

    const city = bestRound.city_name ? escapeHtml(bestRound.city_name) : '—';
    const score = formatScoreWithPenalty(bestRound.score, bestRound.expansion_level);
    return `Round ${bestRound.round_number} · ${city} · ${score} pts`;
}

function renderSummary(summary) {
    setText('statsGamesPlayed', numberFmt(summary.games_played));
    setText('statsPerfectGamesPlayed', numberFmt(summary.perfect_games_played));
    setText('statsBestScore', numberFmt(summary.best_score));
    setText('statsBestScoreDate', summary.best_score_date ? formatDate(summary.best_score_date) : '—');
    setText('statsAveragePoints', numberFmt(summary.average_points));    
    setText('statsTotalPoints', numberFmt(summary.total_points));
    setText('statsTotalSquaresSolved', numberFmt(summary.total_squares_solved));
    setText('statsAverageSquaresSolved', numberFmt(summary.average_squares_solved));
    setText('statsGameStreak', numberFmt(summary.current_game_streak));
    setText('statsPerfectStreak', numberFmt(summary.current_perfect_streak));

    if (summary.strongest_country) {
        setText('statsStrongestCountry', summary.strongest_country.country_name);
        setText(
            'statsStrongestCountryMeta',
            `${numberFmt(summary.strongest_country.average_score)} avg pts · ${numberFmt(summary.strongest_country.guess_count)} guesses`
        );
    } else {
        setText('statsStrongestCountry', '—');
        setText('statsStrongestCountryMeta', '—');
    }

    if (summary.most_obscure_city) {
        setText(
            'statsMostObscureCity',
            `${summary.most_obscure_city.city_name}, ${summary.most_obscure_city.country_name}`
        );
        setText(
            'statsMostObscureCityMeta',
            `Population ${numberFmt(summary.most_obscure_city.population)} · Notoriety ${numberFmt(summary.most_obscure_city.notoriety_score)}`
        );
    } else {
        setText('statsMostObscureCity', '—');
        setText('statsMostObscureCityMeta', '—');
    }

    if (summary.most_used_city) {
        setText(
            'statsMostUsedCity',
            `${summary.most_used_city.city_name}, ${summary.most_used_city.country_name}`
        );
        setText(
            'statsMostUsedCityMeta',
            `${numberFmt(summary.most_used_city.times_used)} uses · Population ${numberFmt(summary.most_used_city.population)}`
        );
    } else {
        setText('statsMostUsedCity', '—');
        setText('statsMostUsedCityMeta', '—');
    }
    
}

function renderRegionSummary(summaryRows) {
    const summaryBody = document.getElementById('profileRegionSummaryTableBody');
    summaryBody.innerHTML = summaryRows.map((row) => `
        <tr class="region-summary-row" data-region="${escapeHtml(row.region)}" role="button" tabindex="0" aria-expanded="false">
            <td>${escapeHtml(row.region)}</td>
            <td>${numberFmt(row.square_count)}</td>
            <td>${numberFmt(row.completion_rate)}%</td>
            <td>${numberFmt(row.average_points)}</td>
        </tr>
    `).join('');
    wireRegionRowToggle();
}

function buildHistoryRoundsTable(completedRounds) {
    const bodyRows = completedRounds.map((round) => {
        const guess = round.guesses && round.guesses.length ? round.guesses[round.guesses.length - 1] : null;

        return `
            <tr>
                <td>${numberFmt(round.round_number)}</td>
                <td>${guess ? escapeHtml(guess.city_name || '—') : '—'}</td>
                <td class="pop-cell">${guess && guess.population != null ? numberFmt(guess.population) : '—'}</td>
                <td>${guess && guess.rank != null ? numberFmt(guess.rank) : '—'}</td>
                <td>${formatScoreWithPenalty(round.score, round.expansion_level)}</td>
            </tr>
        `;
    }).join('');

    let total = 0;
    completedRounds.forEach((round) => {
        if (typeof round.score !== 'number' || !Number.isFinite(round.score)) {
            throw new Error('History round score must be a finite number.');
        }
        total += round.score;
    });

    return `
        <div class="stats-card">
            <table class="stats-rounds-table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>City</th>
                        <th>Pop.</th>
                        <th>Rank</th>
                        <th>Pts</th>
                    </tr>
                </thead>
                <tbody>${bodyRows}</tbody>
                <tfoot>
                    <tr>
                        <td colspan="4"><b>Total</b></td>
                        <td>${numberFmt(total)}</td>
                    </tr>
                </tfoot>
            </table>
        </div>
    `;
}

function renderHistory(history, append = false) {
    const container = document.getElementById('profileHistoryList');

    if (!history || history.length === 0) {
        if (!append) {
            container.innerHTML = '<div class="profile-message">No history found.</div>';
        }
        return;
    }

    const markup = history.map((game, index) => `
        <section class="profile-history-card${!append && index === 0 ? ' is-open' : ''}">
            <button class="profile-history-summary" type="button">
                <div class="profile-history-col">
                    <div class="profile-history-topline">${formatDate(game.game_date)}</div>
                    <div class="profile-history-subline">${game.completed_at ? formatDateTime(game.completed_at) : '—'}</div>
                </div>

                <div class="profile-history-col">
                    <div class="label">Solved</div>
                    <div class="profile-history-topline">${numberFmt(game.solved_count)} / 5</div>
                </div>

                <div class="profile-history-col">
                    <div class="label">Points</div>
                    <div class="profile-history-topline">${numberFmt(game.total_score)}</div>
                </div>

                <div class="profile-history-col">
                    <div class="label">Best Round</div>
                    <div class="profile-history-subline">${formatBestRound(game.best_round)}</div>
                </div>

                <div class="profile-history-col">
                    <span class="profile-pill${game.is_perfect ? ' perfect' : ''}">${game.is_perfect ? 'Perfect' : 'Completed'}</span>
                </div>

                <div class="profile-history-toggle">+</div>
            </button>

            <div class="profile-history-details">                            
                ${buildHistoryRoundsTable(game.completed_rounds)}            
            </div>
        </section>
    `).join('');

    if (append) {
        container.insertAdjacentHTML('beforeend', markup);
    } else {
        container.innerHTML = markup;
    }

    wireHistoryCards();
    adjustProfilePopulationDisplay();
}

function updateHistoryPagination(pagination, returnedCount) {
    historyOffset = Number(pagination?.offset) + returnedCount;
    historyHasMore = Boolean(pagination?.has_more);
    document.getElementById('profileHistoryLoadMore').classList.toggle('hidden', !historyHasMore);
}

async function loadMoreHistory() {
    const button = document.getElementById('profileHistoryLoadMore');
    button.disabled = true;

    try {
        const { response, data } = await fetchJson(`/api/profile/history?offset=${historyOffset}`);
        const history = data.history;
        renderHistory(history, true);
        updateHistoryPagination(data.history_pagination, history.length);
    } finally {
        button.disabled = false;
    }
}

function adjustProfilePopulationDisplay() {
    const popCells = document.querySelectorAll('.profile-history-details .pop-cell');
    
    popCells.forEach((cell) => {
        const text = cell.textContent.trim();
        const value = parseInt(text.replace(/,/g, ''), 10);
        const formatted = numberFmt(value);
        const width = abbreviatePopulationForDisplay(value, '.stats-rounds-table td:nth-child(3)');
        
        if (width !== formatted) {
            cell.textContent = width;
        }
    });
}

function wireHistoryCards() {
    const cards = document.querySelectorAll('.profile-history-card');

    cards.forEach((card) => {
        const button = card.querySelector('.profile-history-summary');
        button.onclick = () => {
            card.classList.toggle('is-open');
        };
    });
}

function renderNoProfile() {
    hideElement('profileContent');    
    hideElement('profileLoadingState');    
    wireAuthButtons(null);
}

function renderProfile(payload) {
    hideElement('profileLoadingState');    
    showElement('profileContent');

    const username = payload.user?.username;

    setText('profileUsername', username);
    setText('profileHeroName', username);    

    renderSummary(payload.summary);
    regionPerformanceSummary = payload.region_performance;
    renderRegionSummary(regionPerformanceSummary);
    const history = payload.history;
    renderHistory(history);
    updateHistoryPagination(payload.history_pagination, history.length);
    document.getElementById('profileHistoryLoadMore').onclick = loadMoreHistory;
    wireAuthButtons(payload.user);
}

async function loadProfile() {
    const { response, data } = await fetchJson('/api/profile');

    if (!response.ok || !data.profile_found) {
        renderNoProfile();
        return;
    }

    renderProfile(data);
}

loadProfile().catch(() => {
    renderNoProfile();
});

function wireAuthButtons(user) {
    const loginBtn = document.getElementById('loginBtn');
    const logoutBtn = document.getElementById('logoutBtn');

    if (!user?.is_authenticated) {
        loginBtn.classList.remove('hidden');
        logoutBtn.classList.add('hidden');
    } else {
        loginBtn.classList.add('hidden');
        logoutBtn.classList.remove('hidden');
    }

    loginBtn.onclick = () => {
        window.location.href = '/login';
    };

    logoutBtn.onclick = () => {
        window.location.href = '/logout';
    };
}

function wireRegionRowToggle() {
    const rows = document.querySelectorAll('.region-summary-row');

    rows.forEach((row) => {
        const toggle = async () => {
            const expanded = row.getAttribute('aria-expanded') === 'true';
            const existingDetail = row.nextElementSibling;
            if (expanded) {
                existingDetail.remove();
                row.setAttribute('aria-expanded', 'false');
                return;
            }

            const region = row.dataset.region;
            const detailRow = document.createElement('tr');
            detailRow.className = 'region-detail-container';
            detailRow.innerHTML = '<td colspan="4">Loading classification detail...</td>';
            row.insertAdjacentElement('afterend', detailRow);
            row.setAttribute('aria-expanded', 'true');

            const { response, data } = await fetchJson(
                `/api/profile/region-details?region=${encodeURIComponent(region)}`
            );
            if (!response.ok) {
                throw new Error(`Unable to load classification detail for ${region}.`);
            }

            detailRow.innerHTML = renderRegionDetailTable(data.region_classification_details);
        };
        row.onclick = toggle;
        row.onkeydown = (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                toggle();
            }
        };
    });
}

function renderRegionDetailTable(detailRows) {
    const rows = detailRows.map((row) => `
        <tr class="region-detail-row">
            <td>${escapeHtml(row.game_date)}</td>
            <td>${numberFmt(row.round_number)}</td>
            <td>${row.guessed_city ? escapeHtml(row.guessed_city) : '—'}</td>
            <td>${row.guessed_population != null ? numberFmt(row.guessed_population) : '—'}</td>
            <td>${row.top_city_name ? escapeHtml(row.top_city_name) : '—'}</td>
            <td>${row.top_city_population != null ? numberFmt(row.top_city_population) : '—'}</td>
            <td>${formatScoreWithPenalty(row.score, row.expansion_level)}</td>
        </tr>
    `).join('');
    return `
        <td colspan="4">
            <table class="stats-rounds-table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Round</th>
                        <th>Your Guess</th>
                        <th>Pop.</th>
                        <th>Largest City</th>
                        <th>Pop.</th>
                        <th>Pts</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </td>
    `;
}