import { fetchPlayerStats } from './api.js';
import { escapeHtml, numberFmt, parseFormattedInt } from './utils.js';

export async function syncStatsUsernameUi() {
    const row = document.getElementById('statsUserRow');
    const view = document.getElementById('statsUserView');
    const edit = document.getElementById('statsUserEdit');
    const text = document.getElementById('statsUsernameText');
    const input = document.getElementById('statsUsernameInput');
    const message = document.getElementById('statsUsernameMessage');

    if (!row || !view || !edit || !text || !input || !message) {
        return;
    }

    message.textContent = '';
    edit.classList.add('hidden');
    view.classList.remove('hidden');

    if (!latestGameState || !latestGameState.is_authenticated) {
        row.classList.add('hidden');
        return;
    }

    row.classList.remove('hidden');
    text.textContent = latestGameState.username || '';
    input.value = latestGameState.username || '';
}

export function wireStatsOverlay() {
    const overlay = document.getElementById('statsOverlay');
    const closeBtn = document.getElementById('statsCloseBtn');
    const backdrop = overlay.querySelector('.stats-backdrop');
    const editBtn = document.getElementById('statsUsernameEditBtn');
    const saveBtn = document.getElementById('statsUsernameSaveBtn');
    const cancelBtn = document.getElementById('statsUsernameCancelBtn');
    const input = document.getElementById('statsUsernameInput');

    closeBtn.onclick = hideStatsOverlay;
    backdrop.onclick = hideStatsOverlay;

    if (editBtn) {
        editBtn.onclick = () => {
            const row = document.getElementById('statsUserRow');
            const view = document.getElementById('statsUserView');
            const edit = document.getElementById('statsUserEdit');
            const text = document.getElementById('statsUsernameText');
            const message = document.getElementById('statsUsernameMessage');

            if (row.classList.contains('hidden')) {
                return;
            }

            input.value = text.textContent.trim();
            message.textContent = '';
            view.classList.add('hidden');
            edit.classList.remove('hidden');
            input.focus();
            input.select();
        };
    }

    if (cancelBtn) {
        cancelBtn.onclick = () => {
            const view = document.getElementById('statsUserView');
            const edit = document.getElementById('statsUserEdit');
            const message = document.getElementById('statsUsernameMessage');

            message.textContent = '';
            edit.classList.add('hidden');
            view.classList.remove('hidden');
        };
    }

    if (saveBtn) {
        saveBtn.onclick = async () => {
            const view = document.getElementById('statsUserView');
            const edit = document.getElementById('statsUserEdit');
            const text = document.getElementById('statsUsernameText');
            const message = document.getElementById('statsUsernameMessage');
            const username = input.value.trim();

            message.textContent = '';

            if (!username) {
                message.textContent = 'Username is required';
                return;
            }

            if (!/^[a-zA-Z0-9]{3,15}$/.test(username)) {
                message.textContent = 'Username must be 3-15 letters or numbers';
                return;
            }

            const { response: checkResponse, data: checkData } = await fetchJson(`/api/username-check?username=${encodeURIComponent(username)}`);
            if (!checkResponse.ok) {
                message.textContent = 'Unable to validate username';
                return;
            }

            const currentUsername = text.textContent.trim();
            if (username !== currentUsername && !checkData.available) {
                message.textContent = 'Username taken';
                return;
            }

            const { response: saveResponse, data: saveData } = await fetchJson('/api/set-username', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username })
            });

            if (!saveResponse.ok) {
                message.textContent = saveData?.error || 'Unable to save username';
                return;
            }

            if (latestGameState) {
                latestGameState.username = username;
            }

            text.textContent = username;
            message.textContent = 'Saved';
            edit.classList.add('hidden');
            view.classList.remove('hidden');
        };
    }

    if (input) {
        input.onkeydown = async (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                await saveBtn.onclick();
            }

            if (e.key === 'Escape') {
                e.preventDefault();
                cancelBtn.onclick();
            }
        };
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && overlay.style.display !== 'none') {
            hideStatsOverlay();
        }
    });
}

export function hideStatsOverlay() {
    document.getElementById('statsOverlay').style.display = 'none';
}

export function showStatsOverlay() {
    document.getElementById('statsOverlay').style.display = 'block';
}

export function renderStatsChart(stats) {
    const svg = document.getElementById('statsChart');
    const chartPoints = stats.graph_points || [];

    const width = 640;
    const height = 220;
    const leftPad = 40;
    const rightPad = 40;
    const topPad = 28;
    const bottomPad = 30;
    const innerWidth = width - leftPad - rightPad;
    const innerHeight = height - topPad - bottomPad;

    if (chartPoints.length === 0) {
        svg.innerHTML = `
            <text x="${width / 2}" y="${height / 2}" text-anchor="middle" fill="#9dacbf" font-size="16">
                No games yet
            </text>
        `;
        return;
    }

    const maxSolved = 5;
    const maxPoints = Math.max(...chartPoints.map(p => Number(p.points) || 0), 1);

    const xFor = (index) => {
        if (chartPoints.length === 1) {
            return leftPad + innerWidth / 2;
        }
        return leftPad + (index / (chartPoints.length - 1)) * innerWidth;
    };

    const ySolved = (value) => topPad + ((maxSolved - value) / maxSolved) * innerHeight;
    const yPoints = (value) => topPad + ((maxPoints - value) / maxPoints) * innerHeight;

    const solvedLine = chartPoints
        .map((p, i) => `${xFor(i)},${ySolved(Number(p.solved) || 0)}`)
        .join(' ');

    const pointsLine = chartPoints
        .map((p, i) => `${xFor(i)},${yPoints(Number(p.points) || 0)}`)
        .join(' ');

    const solvedDots = chartPoints
        .map((p, i) => `<circle cx="${xFor(i)}" cy="${ySolved(Number(p.solved) || 0)}" r="4.5" fill="#8fd3ff"></circle>`)
        .join('');

    const pointsDots = chartPoints
        .map((p, i) => `<circle cx="${xFor(i)}" cy="${yPoints(Number(p.points) || 0)}" r="3.5" fill="#ffd166"></circle>`)
        .join('');

    const perfectMarkers = chartPoints
        .map((p, i) => {
            if (!p.is_perfect) {
                return '';
            }

            return `<circle cx="${xFor(i)}" cy="${ySolved(Number(p.solved) || 0)}" r="7" fill="none" stroke="#4cff88" stroke-width="2"></circle>`;
        })
        .join('');

    const labels = chartPoints
        .map((p, i) => `
            <text x="${xFor(i)}" y="${height - 8}" text-anchor="middle" fill="#9dacbf" font-size="10">
                ${p.game_date.slice(5)}
            </text>
        `)
        .join('');

    const grid = [0, 1, 2, 3, 4, 5]
        .map(v => `<line x1="${leftPad}" y1="${ySolved(v)}" x2="${width - rightPad}" y2="${ySolved(v)}" stroke="rgba(157,172,191,0.12)" stroke-width="1"></line>`)
        .join('');

    svg.innerHTML = `
        ${grid}

        <polyline fill="none" stroke="#8fd3ff" stroke-width="3" points="${solvedLine}"></polyline>
        <polyline fill="none" stroke="#ffd166" stroke-width="2" stroke-dasharray="6 4" points="${pointsLine}"></polyline>

        ${solvedDots}
        ${pointsDots}
        ${perfectMarkers}
        ${labels}

        <g transform="translate(${width / 2 - 98}, ${height + 1})">
            <line x1="0" y1="8" x2="24" y2="8" stroke="#8fd3ff" stroke-width="3"></line>
            <text x="30" y="12" fill="#9dacbf" font-size="11">Solved</text>

            <line x1="110" y1="8" x2="134" y2="8" stroke="#ffd166" stroke-width="2" stroke-dasharray="6 4"></line>
            <text x="140" y="12" fill="#9dacbf" font-size="11">Points</text>
        </g>

        <text x="${leftPad - 10}" y="${ySolved(5) + 4}" text-anchor="end" fill="#9dacbf" font-size="10">5</text>
        <text x="${leftPad - 10}" y="${ySolved(0) + 4}" text-anchor="end" fill="#9dacbf" font-size="10">0</text>

        <text x="${width - rightPad + 10}" y="${yPoints(maxPoints) + 4}" fill="#9dacbf" font-size="10">${numberFmt(maxPoints)}</text>
        <text x="${width - rightPad + 10}" y="${yPoints(0) + 4}" fill="#9dacbf" font-size="10">0</text>
    `;
}

export function renderStatsOverlay(stats, todaySummary) {
    const solved = todaySummary.solved;
    const totalRounds = todaySummary.totalRounds;
    const isPerfect = solved === totalRounds && totalRounds > 0;

    document.getElementById('statsTitle').textContent = isPerfect ? 'Perfect Game!' : 'Game Complete!';
    document.getElementById('statsTodayCard').classList.toggle('perfect-day', isPerfect);

    document.getElementById('statsGameDate').textContent = todaySummary.gameDate || '—';
    document.getElementById('statsTodaySolved').textContent = `${solved} / ${totalRounds}`;
    document.getElementById('statsTodayPoints').textContent = numberFmt(todaySummary.total || 0);
    document.getElementById('statsTodayBestRound').textContent = todaySummary.bestRound
        ? `${todaySummary.bestRound.city} · R${todaySummary.bestRound.round} · ${numberFmt(todaySummary.bestRound.points)}`
        : '—';

    document.getElementById('statsGamesPlayed').textContent = numberFmt(stats.games_played || 0);
    document.getElementById('statsGameStreak').textContent = numberFmt(stats.current_streak || 0);
    document.getElementById('statsAveragePoints').textContent = numberFmt(stats.average_score || 0);
    document.getElementById('statsPerfectDays').textContent = `${numberFmt(stats.perfect_days || 0)} / ${numberFmt(stats.games_played || 0)}`;
    document.getElementById('statsPerfectStreak').textContent = numberFmt(stats.perfect_streak || 0);
    document.getElementById('statsBestPoints').textContent = numberFmt(stats.best_score || 0);
    document.getElementById('statsBestPointsDate').textContent = stats.best_score_game_date || '—';

    renderStatsChart(stats);
}

export async function showEndGameSummary() {
    const totalText = document.getElementById('totalPoints').textContent;
    const total = parseFormattedInt(totalText);
    const rows = Array.from(document.querySelectorAll('#roundTable tbody tr'));

    let bestRound = null;
    let bestPoints = -1;
    let solved = 0;

    for (const row of rows) {
        const cells = row.querySelectorAll('td');
        const round = parseInt(cells[0].textContent.trim(), 10) || 0;
        const city = cells[1].textContent.trim();
        const points = parseFormattedInt(cells[4].textContent);

        if (points > 0) {
            solved += 1;
        }

        if (points > bestPoints) {
            bestPoints = points;
            bestRound = { round, city, points };
        }
    }

    const totalRounds = rows.length;
    const isPerfect = totalRounds > 0 && solved === totalRounds;

    const feedback = document.getElementById('guessFeedback');
    feedback.innerHTML = isPerfect
        ? `<div><b>Perfect Game!</b></div><div style="margin-top:8px;">You completed all ${totalRounds} squares and scored <b>${escapeHtml(totalText)}</b> points.</div>`
        : `<div><b>Game Complete</b></div><div style="margin-top:8px;">You completed <b>${solved} / ${totalRounds}</b> squares and scored <b>${escapeHtml(totalText)}</b> points.</div>`;

    const stats = await fetchPlayerStats();
    const lastGraphPoint = stats.graph_points && stats.graph_points.length
        ? stats.graph_points[stats.graph_points.length - 1]
        : null;

    renderStatsOverlay(stats, {
        total,
        solved,
        totalRounds,
        gameDate: lastGraphPoint ? lastGraphPoint.game_date : '—',
        bestRound: bestRound && bestRound.points > 0 ? bestRound : null
    });

    await syncStatsUsernameUi();
    showStatsOverlay();
}