import { fetchGameState, fetchPlayerStats, fetchJson } from './api.js?v=4';
import { gameState } from './state.js?v=4';
import { escapeHtml, numberFmt, ordinal, parseFormattedInt } from './utils.js?v=4';

const SHARE_FORMAT_DETAILED = 'detailed';
const SHARE_FORMAT_DISCORD = 'discord';
const SHARE_FORMAT_COMPACT = 'compact';

let shareStatusTimerId = null;
let activeShareFormat = SHARE_FORMAT_DETAILED;
let shareSource = {
    gameDate: '',
    rounds: new Map(),
    total: 0,
};

function toShareRound(result, roundNumber) {
    const score = Number(result.score ?? result.points ?? 0) || 0;
    const expansionLevel = Number(result.expansion_level ?? 0) || 0;
    const expansionPenalty = expansionLevel > 0 ? `-${expansionLevel * 20}%` : '';

    return {
        round: Number(roundNumber) || 0,
        city: result.city ?? result.city_name ?? '—',
        population: result.population,
        rank: result.rank ?? '—',
        points: score,
        expansionPenalty,
    };
}

function recomputeShareTotal() {
    shareSource.total = Array.from(shareSource.rounds.values())
        .reduce((sum, round) => sum + (round.points || 0), 0);
}

function getShareRoundsSorted() {
    return Array.from(shareSource.rounds.values())
        .sort((a, b) => a.round - b.round);
}

function getRoundMarker(round) {
    if (round.points <= 0) return '⬛';
    return round.expansionPenalty ? '🟨' : '🟩';
}

function getShareUrl() {
    const gameUrl = new URL(window.location.pathname, window.location.origin);
    gameUrl.searchParams.set('ref', 'share');
    return gameUrl.toString();
}

function formatShareRank(rank) {
    const numericRank = Number(rank);
    return Number.isInteger(numericRank) ? ordinal(numericRank) : String(rank);
}

export function hydrateShareFromState(state) {
    shareSource = {
        gameDate: state?.game_date || '',
        rounds: new Map(),
        total: 0,
    };

    for (const round of (state?.completed_rounds || [])) {
        const guess = round.guesses && round.guesses.length ? round.guesses[0] : null;

        shareSource.rounds.set(
            Number(round.round_number) || 0,
            {
                round: round.round_number ?? 0,
                city: guess ? guess.city_name : '—',
                population: guess ? guess.population : null,
                rank: guess ? (guess.rank ?? '—') : '—',
                points: round.score ?? 0,
                expansionPenalty: (round.expansion_level ?? 0) > 0 ? `-${(round.expansion_level ?? 0) * 20}%` : '',
            }
        );
    }

    recomputeShareTotal();
}

export function recordShareRound(result, roundNumber) {
    const shareRound = toShareRound(result, roundNumber);
    shareSource.rounds.set(shareRound.round, shareRound);
    recomputeShareTotal();
}

export function isShareReady() {
    return shareSource.rounds.size > 0;
}

function buildShareSummaryText({ gameDate, total, solved, totalRounds, rounds, isPerfect }) {
    const roundLines = (rounds || []).map((round) => {
        const city = round.city && round.city !== '—' ? round.city : 'Pass';
        const penalty = round.expansionPenalty ? ` ${round.expansionPenalty}` : '';
        return `${getRoundMarker(round)} R${round.round}  ${city} · ${numberFmt(round.population)} · ${formatShareRank(round.rank)} · ${numberFmt(round.points)} pts${penalty}`;
    });

    return [
        `GeoSquare ${gameDate || ''}`.trim(),
        `${numberFmt(total || 0)} points | ${solved}/${totalRounds} solved`,
        ...roundLines,
        getShareUrl(),
    ].join('\n');
}

function buildDiscordShareText({ gameDate, total, solved, totalRounds, rounds, isPerfect }) {
    const roundLines = rounds.map((round) => {
        const city = round.city && round.city !== '—' ? round.city : 'Pass';
        const penalty = round.expansionPenalty ? ` ${round.expansionPenalty}` : '';
        const spoiler = `${city} · ${numberFmt(round.population)} · ${formatShareRank(round.rank)}`;
        return `${getRoundMarker(round)} R${round.round}  ||${spoiler}|| · ${numberFmt(round.points)} pts${penalty}`;
    });

    return [
        `GeoSquare ${gameDate || ''}`.trim(),
        `${numberFmt(total || 0)} points | ${solved}/${totalRounds} solved`,
        ...roundLines,
        getShareUrl(),
    ].join('\n');
}

function buildCompactShareText({ gameDate, total, solved, totalRounds, rounds }) {
    const resultGrid = rounds.map(getRoundMarker).join(' ');

    return [
        `GeoSquare ${gameDate || ''}`.trim(),
        `${numberFmt(total || 0)} points | ${solved}/${totalRounds} solved`,
        resultGrid,
        'Can you beat me?',
        getShareUrl(),
    ].join('\n');
}

function getShareText(format) {
    const rounds = getShareRoundsSorted();
    const totalRounds = rounds.length;
    const solved = rounds.filter((round) => round.points > 0).length;
    const total = shareSource.total || 0;
    const isPerfect = totalRounds > 0 && solved === totalRounds;
    const shareData = {
        gameDate: shareSource.gameDate || '',
        total,
        solved,
        totalRounds,
        rounds,
        isPerfect,
    };

    if (format === SHARE_FORMAT_DISCORD) return buildDiscordShareText(shareData);
    if (format === SHARE_FORMAT_COMPACT) return buildCompactShareText(shareData);
    return buildShareSummaryText(shareData);
}

async function copyTextToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return true;
    }

    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'absolute';
    textarea.style.left = '-9999px';

    document.body.appendChild(textarea);
    textarea.select();

    const copied = document.execCommand('copy');
    document.body.removeChild(textarea);
    return copied;
}

export function buildRoundsFromState(state) {
    return (state.completed_rounds || []).map((round) => {
        const guess = round.guesses && round.guesses.length ? round.guesses[0] : null;
        const expansionLevel = round.expansion_level ?? 0;
        const expansionPenalty = expansionLevel > 0 ? `-${expansionLevel * 20}%` : '';

        return {
            round: round.round_number ?? 0,
            city: guess ? guess.city_name : '—',
            population: guess ? (guess.population ?? 0) : 0,
            rank: guess ? (guess.rank ?? '—') : '—',
            points: round.score ?? 0,
            expansionPenalty,
        };
    });
}

export function syncStatsUsernameUi(state) {
    const row = document.getElementById('statsUserRow');
    const view = document.getElementById('statsUserView');
    const edit = document.getElementById('statsUserEdit');
    const text = document.getElementById('statsUsernameText');
    const input = document.getElementById('statsUsernameInput');
    const message = document.getElementById('statsUsernameMessage');

    message.textContent = '';

    if (!state || !state.is_authenticated) {
        row.classList.add('hidden');
        return;
    }

    row.classList.remove('hidden');

    text.textContent = state.username || '';
    input.value = state.username || '';
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

        input.oninput = async () => {
            const message = document.getElementById('statsUsernameMessage');
            const username = input.value.trim();

            message.textContent = '';

            if (!username) {
                return;
            }

            if (!/^[a-zA-Z0-9]{3,15}$/.test(username)) {
                message.textContent = 'Username must be 3-15 letters or numbers';
                return;
            }

            const { response, data } = await fetchJson(`/api/username-check?username=${encodeURIComponent(username)}`);

            if (!response.ok) {
                message.textContent = 'Unable to validate username';
                return;
            }

            if (!data.available) {
                message.textContent = 'Username taken';
                return;
            }

            message.textContent = 'Available';
        };
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && overlay.style.display !== 'none') {
            hideStatsOverlay();
        }
    });

    wireShareModal();
}

export function hideStatsOverlay() {
    document.getElementById('statsOverlay').style.display = 'none';
}

function hideShareModal() {
    document.getElementById('shareScoreModal').classList.add('hidden');
}

function appendPreviewElement(parent, className, text) {
    const element = document.createElement('div');
    element.className = className;
    element.textContent = text;
    parent.appendChild(element);
    return element;
}

function renderSharePreview() {
    const preview = document.getElementById('shareTextPreview');
    const rounds = getShareRoundsSorted();
    const solved = rounds.filter((round) => round.points > 0).length;
    const header = document.createElement('div');
    const summary = document.createElement('div');

    preview.replaceChildren();
    header.className = 'share-card-header';
    appendPreviewElement(header, 'share-card-brand', 'GeoSquare');
    appendPreviewElement(header, 'share-card-date', shareSource.gameDate || '');
    preview.appendChild(header);

    summary.className = 'share-card-summary';
    appendPreviewElement(summary, 'share-card-score', numberFmt(shareSource.total || 0));
    appendPreviewElement(summary, 'share-card-solved', `${solved}/${rounds.length} solved`);
    preview.appendChild(summary);

    if (activeShareFormat === SHARE_FORMAT_COMPACT) {
        const resultGrid = rounds.map(getRoundMarker).join(' ');
        appendPreviewElement(preview, 'share-card-hidden-grid', resultGrid);
        appendPreviewElement(preview, 'share-card-challenge', 'Can you beat me?');
        appendPreviewElement(preview, 'share-card-url', getShareUrl());
        return;
    }

    const roundList = appendPreviewElement(preview, 'share-card-rounds', '');
    rounds.forEach((round) => {
        const row = appendPreviewElement(roundList, 'share-card-round', '');
        appendPreviewElement(row, 'share-card-marker', getRoundMarker(round));
        const city = round.city && round.city !== '—' ? round.city : 'Pass';
        const penalty = round.expansionPenalty ? ` ${round.expansionPenalty}` : '';

        appendPreviewElement(row, 'share-card-round-number', `R${round.round}`);
        if (activeShareFormat === SHARE_FORMAT_DISCORD) {
            const spoiler = document.createElement('button');
            spoiler.type = 'button';
            spoiler.className = 'share-card-spoiler';
            spoiler.textContent = `${city} · ${numberFmt(round.population)} · ${formatShareRank(round.rank)}`;
            spoiler.setAttribute('aria-label', 'Reveal spoiler');
            spoiler.onclick = () => {
                const isRevealed = spoiler.classList.toggle('revealed');
                spoiler.setAttribute('aria-label', isRevealed ? 'Hide spoiler' : 'Reveal spoiler');
            };
            row.appendChild(spoiler);
        } else {
            appendPreviewElement(
                row,
                'share-card-city',
                `${city} · ${numberFmt(round.population)} · ${formatShareRank(round.rank)}`,
            );
        }
        appendPreviewElement(row, 'share-card-round-meta', `· ${numberFmt(round.points)} pts${penalty}`);
    });
    appendPreviewElement(preview, 'share-card-url', getShareUrl());
}

function selectShareFormat(format) {
    activeShareFormat = format;
    const icon = document.getElementById('shareFormatIcon');
    const button = document.getElementById('shareFormatBtn');

    if (format === SHARE_FORMAT_DISCORD) {
        icon.className = 'fa-brands fa-discord';
        button.setAttribute('aria-label', 'Discord spoilers');
    } else if (format === SHARE_FORMAT_COMPACT) {
        icon.className = 'fa-regular fa-eye-slash';
        button.setAttribute('aria-label', 'Details hidden');
    } else {
        icon.className = 'fa-regular fa-eye';
        button.setAttribute('aria-label', 'Details visible');
    }

    renderSharePreview();
    document.getElementById('shareModalStatus').textContent = '';
}

function cycleShareFormat() {
    if (activeShareFormat === SHARE_FORMAT_DETAILED) {
        selectShareFormat(SHARE_FORMAT_DISCORD);
    } else if (activeShareFormat === SHARE_FORMAT_DISCORD) {
        selectShareFormat(SHARE_FORMAT_COMPACT);
    } else {
        selectShareFormat(SHARE_FORMAT_DETAILED);
    }
}

async function copySelectedShareText() {
    const shareStatus = document.getElementById('shareScoreStatus');
    const modalStatus = document.getElementById('shareModalStatus');

    try {
        await copyTextToClipboard(getShareText(activeShareFormat));
        hideShareModal();

        if (shareStatus) {
            shareStatus.textContent = 'Copied';
        }
    } catch (_error) {
        modalStatus.textContent = 'Copy failed';
        return;
    }

    if (shareStatusTimerId) {
        window.clearTimeout(shareStatusTimerId);
    }

    if (shareStatus) {
        shareStatusTimerId = window.setTimeout(() => {
            shareStatus.textContent = '';
        }, 1800);
    }
}

function wireShareModal() {
    const modal = document.getElementById('shareScoreModal');

    document.getElementById('shareModalCloseBtn').onclick = hideShareModal;
    document.getElementById('shareFormatBtn').onclick = cycleShareFormat;
    document.getElementById('shareCopyBtn').onclick = copySelectedShareText;
    modal.onclick = (event) => {
        if (event.target === modal) hideShareModal();
    };

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && !modal.classList.contains('hidden')) hideShareModal();
    });
}

export function shareCurrentGameScore() {
    const shareStatus = document.getElementById('shareScoreStatus');

    if (!getShareRoundsSorted().length) {
        if (shareStatus) shareStatus.textContent = 'Not ready';
        return;
    }

    selectShareFormat(SHARE_FORMAT_DETAILED);
    document.getElementById('shareScoreModal').classList.remove('hidden');
    document.getElementById('shareFormatBtn').focus();
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

function buildTodayRoundsFromCompletedRounds(completedRounds) {
        return (completedRounds || []).map((round) => {
            const guess = round.guesses && round.guesses.length ? round.guesses[0] : null;

            return {
                round: round.round_number ?? 0,
                city: guess ? guess.city_name : '—',
                population: guess ? (guess.population ?? 0) : 0,
                rank: guess ? (guess.rank ?? '—') : '—',
                points: round.score ?? 0
            };
        });
    }

function renderTodayRoundsTable(rounds, total) {
    const tbody = document.querySelector('#statsTodayRoundsTable tbody');
    const totalEl = document.getElementById('statsTodayRoundsTotal');

    tbody.innerHTML = rounds.map((round) => `
        <tr>
            <td>${round.round}</td>
            <td><span class="round-city">${escapeHtml(round.city)}</span></td>
            <td>${numberFmt(round.population)}</td>
            <td>${round.rank}</td>
            <td>${numberFmt(round.points)}${round.expansionPenalty ? ` <span class="stats-expansion-penalty">[${escapeHtml(round.expansionPenalty)}]</span>` : ''}</td>
        </tr>
    `).join('');

    totalEl.textContent = numberFmt(total || 0);
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
    document.getElementById('statsTodayBestRound').innerHTML = todaySummary.bestRound
        ? `${escapeHtml(todaySummary.bestRound.city)} · R${todaySummary.bestRound.round} · ${numberFmt(todaySummary.bestRound.points)}${todaySummary.bestRound.expansionPenalty ? ` <span class="stats-expansion-penalty">[${escapeHtml(todaySummary.bestRound.expansionPenalty)}]</span>` : ''}`
        : '—';

    renderTodayRoundsTable(todaySummary.rounds || [], todaySummary.total || 0);

    document.getElementById('statsGamesPlayed').textContent = numberFmt(stats.games_played || 0);
    document.getElementById('statsGameStreak').textContent = numberFmt(stats.current_streak || 0);
    document.getElementById('statsAveragePoints').textContent = numberFmt(stats.average_score || 0);
    document.getElementById('statsPerfectDays').textContent = `${numberFmt(stats.perfect_days || 0)} / ${numberFmt(stats.games_played || 0)}`;
    document.getElementById('statsPerfectStreak').textContent = numberFmt(stats.perfect_streak || 0);
    document.getElementById('statsBestPoints').textContent = numberFmt(stats.best_score || 0);
    document.getElementById('statsBestPointsDate').textContent = stats.best_score_game_date || '—';

    renderStatsChart(stats);
}

export function renderEndGameFeedbackFromState(state) {
    const rounds = buildRoundsFromState(state);
    const solved = rounds.filter((round) => round.points > 0).length;
    const totalRounds = rounds.length;
    const total = rounds.reduce((sum, round) => sum + (round.points || 0), 0);
    const isPerfect = totalRounds > 0 && solved === totalRounds;

    const feedback = document.getElementById('guessFeedback');
    feedback.innerHTML = isPerfect
        ? `<div><b>Perfect Game!</b></div><div style="margin-top:8px;">You completed all ${totalRounds} squares and scored <b>${numberFmt(total)}</b> points.</div>`
        : `<div><b>Game Complete</b></div><div style="margin-top:8px;">You completed <b>${solved} / ${totalRounds}</b> squares and scored <b>${numberFmt(total)}</b> points.</div>`;
}

export async function showEndGameSummary() {
    const { response, data: state } = await fetchGameState();
    if (!response.ok) {
        throw new Error(state?.error || 'Failed to fetch game state.');
    }

    const rounds = buildRoundsFromState(state);

    let bestRound = null;
    let bestPoints = -1;
    let solved = 0;

    for (const round of rounds) {
        if (round.points > 0) {
            solved += 1;
        }

        if (round.points > bestPoints) {
            bestPoints = round.points;
            bestRound = {
                round: round.round,
                city: round.city,
                points: round.points,
                expansionPenalty: round.expansionPenalty,
            };
        }
    }

    const total = rounds.reduce((sum, r) => sum + (r.points || 0), 0);
    const totalRounds = rounds.length;
    const isPerfect = totalRounds > 0 && solved === totalRounds;

    renderEndGameFeedbackFromState(state);

    const stats = await fetchPlayerStats();
    const lastGraphPoint = stats.graph_points?.length
        ? stats.graph_points[stats.graph_points.length - 1]
        : null;
    const gameDate = lastGraphPoint ? lastGraphPoint.game_date : '—';

    renderStatsOverlay(stats, {
        total,
        solved,
        totalRounds,
        rounds,
        gameDate,
        bestRound: bestRound && bestRound.points > 0 ? bestRound : null
    });

    await syncStatsUsernameUi(gameState);
    showStatsOverlay();
}