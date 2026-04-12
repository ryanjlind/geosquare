function numberFmt(value) {
    if (value == null || value === '') {
        return '—';
    }

    return new Intl.NumberFormat('en-US').format(value);
}

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    return { response, data };
}

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

function formatBestRound(bestRound) {
    if (!bestRound) {
        return '—';
    }

    const city = bestRound.city_name ? escapeHtml(bestRound.city_name) : '—';
    const score = numberFmt(bestRound.score);
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
        setText('statsStrongestCountry', summary.strongest_country.country_code);
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
            `${summary.most_obscure_city.city_name}, ${summary.most_obscure_city.country_code}`
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
            `${summary.most_used_city.city_name}, ${summary.most_used_city.country_code}`
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

function renderRegionPerformance(summaryRows, detailRows) {
    const tbody = document.getElementById('profileRegionTableBody');

    if (!tbody) return;

    const grouped = {};
    (detailRows || []).forEach((row) => {
        if (!grouped[row.region]) {
            grouped[row.region] = [];
        }
        grouped[row.region].push(row);
    });

    tbody.innerHTML = (summaryRows || []).map((row, idx) => {
        const regionKey = row.region;
        const regionDetails = grouped[regionKey] || [];
        const detailId = `region-detail-${idx}`;

        const detailRowsHtml = regionDetails.map((d) => `
            <tr class="region-detail-row">
                <td>${escapeHtml(d.game_date)}</td>
                <td>${numberFmt(d.round_number)}</td>
                <td>${d.guessed_city ? escapeHtml(d.guessed_city) : '—'}</td>
                <td>${d.guessed_population != null ? numberFmt(d.guessed_population) : '—'}</td>
                <td>${d.top_city_name ? escapeHtml(d.top_city_name) : '—'}</td>
                <td>${d.top_city_population != null ? numberFmt(d.top_city_population) : '—'}</td>
                <td>${numberFmt(d.score)}</td>
            </tr>
        `).join('');

        return `
            <tr class="region-summary-row" data-target="${detailId}">
                <td>${escapeHtml(row.region)}</td>
                <td>${numberFmt(row.square_count)}</td>
                <td>${numberFmt(row.completion_rate)}%</td>
                <td>${numberFmt(row.average_points)}</td>
            </tr>

            <tr id="${detailId}" class="region-detail-container hidden">
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
                        <tbody>
                            ${detailRowsHtml || '<tr><td colspan="10">No data</td></tr>'}
                        </tbody>
                    </table>
                </td>
            </tr>
        `;
    }).join('');

    wireRegionRowToggle();
}

function buildHistoryRoundsTable(completedRounds) {
    const bodyRows = completedRounds.map((round) => {
        const guess = round.guesses && round.guesses.length ? round.guesses[round.guesses.length - 1] : null;

        return `
            <tr>
                <td>${numberFmt(round.round_number)}</td>
                <td>${guess ? escapeHtml(guess.city_name || '—') : '—'}</td>
                <td>${guess && guess.population != null ? numberFmt(guess.population) : '—'}</td>
                <td>${guess && guess.rank != null ? numberFmt(guess.rank) : '—'}</td>
                <td>${numberFmt(round.score)}</td>
            </tr>
        `;
    }).join('');

    const total = completedRounds.reduce((sum, round) => sum + Number(round.score || 0), 0);

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

function renderHistory(history) {
    const container = document.getElementById('profileHistoryList');

    if (!history || history.length === 0) {
        container.innerHTML = '<div class="profile-message">No history found.</div>';
        return;
    }

    container.innerHTML = history.map((game, index) => `
        <section class="profile-history-card${index === 0 ? ' is-open' : ''}">
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
                ${buildHistoryRoundsTable(game.completed_rounds || [])}            
            </div>
        </section>
    `).join('');

    wireHistoryCards();
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

    const username = payload.user?.username || `User ${payload.user?.user_id ?? ''}`.trim();

    setText('profileUsername', username);
    setText('profileHeroName', username);    

    renderSummary(payload.summary);
    renderRegionPerformance(
        payload.region_performance || [],
        payload.region_classification_details || []
    );
    wireRegionDetailsToggle();
    renderHistory(payload.history || []);
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

function wireRegionDetailsToggle() {
    const button = document.getElementById('profileRegionDetailsToggle');
    const wrap = document.getElementById('profileRegionDetailsWrap');

    if (!button || !wrap) {
        return;
    }

    button.onclick = () => {
        const isHidden = wrap.classList.contains('hidden');

        if (isHidden) {
            wrap.classList.remove('hidden');
            button.textContent = 'Hide square classification detail';
            return;
        }

        wrap.classList.add('hidden');
        button.textContent = 'Show square classification detail';
    };
}

function wireRegionRowToggle() {
    const rows = document.querySelectorAll('.region-summary-row');

    rows.forEach((row) => {
        row.onclick = () => {
            const targetId = row.getAttribute('data-target');
            const detail = document.getElementById(targetId);

            if (!detail) return;

            detail.classList.toggle('hidden');
        };
    });
}