let currentRound = 1;
let roundLocked = false;
let sfxCtx = null;
let sfxWarmupPromise = null;

async function init() {
    
    initCesium();
    wireStatsOverlay();
    
    const stateResponse = await fetch('/api/game-state');
    const state = await stateResponse.json();

    if (!stateResponse.ok) {
        document.getElementById('meta').innerHTML = `<div class="value">${state.error}</div>`;
        return;
    }

    const data = await fetchRound(state.round_number || 1);

    currentRound = data.round_number;
    console.log('[DEBUG] init:before-load', { currentRound });
    roundLocked = false;

    renderRound(data);
    restoreSavedState(state);
    wireGuessing();
    wireRoundButtons();

    if (state.completed_at) {
        document.getElementById('guessInput').disabled = true;
        document.getElementById('guessBtn').disabled = true;
        document.getElementById('nextBtn').style.display = 'none';
        document.getElementById('guessBox').style.display = 'none';
        roundLocked = true;
        showEndGameSummary();
    }
}

function initCesium() {
    if (window.CESIUM_ION_TOKEN) {
        Cesium.Ion.defaultAccessToken = window.CESIUM_ION_TOKEN;
    }

    window.geoViewer = new Cesium.Viewer('cesiumContainer', {
        animation: false,
        timeline: false,
        sceneModePicker: false,
        baseLayerPicker: false,
        geocoder: false,
        homeButton: false,
        navigationHelpButton: false,
        fullscreenButton: false,
        infoBox: false,
        selectionIndicator: false,
        shouldAnimate: false,
    });

    geoViewer.scene.globe.enableLighting = false;
    geoViewer.scene.screenSpaceCameraController.inertiaSpin = 0;
    geoViewer.scene.screenSpaceCameraController.inertiaTranslate = 0;
    geoViewer.scene.screenSpaceCameraController.inertiaZoom = 0;
    geoViewer.scene.screenSpaceCameraController.minimumZoomDistance = 150000;
}

async function fetchGameState() {
    const response = await fetch('/api/game-state');
    return await response.json();
}

async function fetchRound(roundNumber) {
    const response = await fetch(`/api/daily-square?round=${roundNumber}`);
    return await response.json();
}

function renderRound(data) {
    renderSidebar(data);
    drawSquare(window.geoViewer, data);
    zoomToSquare(window.geoViewer, data.bounds);
}

function renderNextRound(data) {
    renderSidebar(data);
    window.geoViewer.entities.removeAll();
    drawSquare(window.geoViewer, data);
    zoomToSquare(window.geoViewer, data.bounds);
    roundLocked = false;
}

function restoreSavedState(state) {
    const tbody = document.querySelector('#roundTable tbody');
    const feedback = document.getElementById('guessFeedback');
    const totalEl = document.getElementById('totalPoints');

    tbody.innerHTML = '';
    totalEl.textContent = '0';
    feedback.innerHTML = '';

    for (const round of (state.completed_rounds || [])) {
    const guess = round.guesses && round.guesses.length ? round.guesses[0] : null;

        addRoundRow({
            city: guess ? guess.city_name : '—',
            population: guess ? (guess.population ?? 0) : 0,
            rank: guess ? (guess.rank ?? '—') : '—',
            score: round.score ?? 0
        }, round.round_number);
    }

    const completedRounds = state.completed_rounds || [];
    const currentRoundCompleted = completedRounds.some(r => r.round_number === state.round_number);

    if (currentRoundCompleted) {
        document.getElementById('guessBox').style.display = 'none';
        roundLocked = true;
    } else {
        document.getElementById('guessBox').style.display = 'block';
        roundLocked = false;
    }
}

function wireRoundButtons() {
    document.getElementById('nextBtn').onclick = handleNextRound;
    document.getElementById('passBtn').onclick = handlePass;
}

async function handleNextRound() {
    const btn = document.getElementById('nextBtn');
    btn.style.display = 'none';

    currentRound += 1;

    if (currentRound > 5) {
        document.getElementById('nextBtn').style.display = 'none';
        document.getElementById('guessInput').disabled = true;
        document.getElementById('guessBtn').disabled = true;
        showEndGameSummary();
        return;
    }

    const data = await fetchRound(currentRound);
    renderNextRound(data);
}

async function handlePass() {
    roundLocked = true;
    getSfxCtx();

    const response = await fetch('/api/pass', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            round_number: currentRound
        })
    });

    const data = await response.json();

    if (!response.ok) {
        document.getElementById('guessFeedback').innerHTML = escapeHtml(data.error || 'Pass failed.');
        roundLocked = false;
        return;
    }

    const largestCity = data.largest_city;

    document.getElementById('guessFeedback').innerHTML = `No guess submitted.<br>
        Largest city: <b>${escapeHtml(largestCity.city_name)}</b><br>
        Population: ${numberFmt(largestCity.population)}<br>
        Points awarded: <b>0</b>`;

    addRoundRow({
        city: '—',
        population: 0,
        rank: '—',
        score: 0
    }, currentRound);

    drawCities(window.geoViewer, [largestCity]);
    playFail();

    if (currentRound === 5) {
        showEndGameSummary();
    } else {
        const nextBtn = document.getElementById('nextBtn');
        nextBtn.textContent = 'Next Round';
        nextBtn.style.display = 'inline-block';
    }

    document.getElementById('guessInput').value = '';
    document.getElementById('guessBox').style.display = 'none';
}

function renderSidebar(data) {
    const meta = document.getElementById('meta');

    window.currentSquareLargestCity = data.largest_city;
    meta.innerHTML = `
        <div class="label">Round</div>
        <div class="value">${data.round_number} / 5</div>
        
        <div class="label">Population in square</div>
        <div class="value">${numberFmt(data.total_population)}</div>

        <div class="label">Cities in square</div>
        <div class="value">${numberFmt(data.total_city_count)}</div>

        <div class="label">Largest city population</div>
        <div class="value">${numberFmt(data.largest_city.population)}</div>

        <div class="label">Gameplay</div>
        <div class="value">
            Squares have a minimum total population of ${numberFmt(data.rules.min_total_population)}.<br>            
            At least ${numberFmt(data.rules.min_city_count)} cities have a population ≥ ${numberFmt(data.rules.min_city_population)}.<br><br>
            Name the smallest city you can within the square. <br><br>
            Smaller cities = more points. <br><br>
            Database contains most cities ≥ 15,000 population.
        </div>
    `;

    document.getElementById('guessBox').style.display = 'block';
    document.getElementById('guessInput').value = '';
    document.getElementById('guessFeedback').innerHTML = '';
}

function drawSquare(viewer, data) {
    const b = data.bounds;

    viewer.entities.add({
        name: 'Daily square',
        rectangle: {
            coordinates: Cesium.Rectangle.fromDegrees(b.min_lon, b.min_lat, b.max_lon, b.max_lat),
            material: Cesium.Color.YELLOW.withAlpha(0.2),
            outline: true,
            outlineColor: Cesium.Color.YELLOW,
            outlineWidth: 2,
        }
    });
}

function drawCities(viewer, cities) {
    for (const city of cities) {
        viewer.entities.add({
            position: Cesium.Cartesian3.fromDegrees(city.longitude, city.latitude),
            point: {
                pixelSize: 6,
                color: Cesium.Color.CYAN,
            },
            label: {
                text: city.city_name,
                font: '14px sans-serif',
                showBackground: true,
                horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
                pixelOffset: new Cesium.Cartesian2(8, 0),
                distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0.0, 30000000.0),
            }
        });
    }
}

function zoomToSquare(viewer, bounds) {
    const centerLat = (bounds.min_lat + bounds.max_lat) / 2;
    const centerLon = (bounds.min_lon + bounds.max_lon) / 2;

    viewer.camera.setView({
        destination: Cesium.Cartesian3.fromDegrees(centerLon, centerLat, 20000000)
    });

    viewer.clock.shouldAnimate = false;
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

function handleGuessKeyDown(e) {
    if (e.key === 'Enter') {
        submitGuess();
    }
}
async function submitGuess() {
    getSfxCtx();

    const input = document.getElementById('guessInput');
    const feedback = document.getElementById('guessFeedback');
    const guess = input.value.trim();

    const response = await fetch('/api/guess', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            guess,
            round_number: currentRound
        })
    });

    const data = await response.json();

    if (data.correct) {
        roundLocked = true;

        feedback.innerHTML = `<b>${escapeHtml(data.city.toUpperCase())}</b> is the ${data.rank === 1 ? 'largest' : `${ordinal(data.rank)} largest`} city in the square.<br><br>
        With a population of ${numberFmt(data.population)}, you are awarded <b>${numberFmt(data.score)}</b> points.<br>`;

        showGuessedCity(window.geoViewer, data);
        addRoundRow(data, currentRound);
        playSuccess();
        document.getElementById('guessInput').value = '';
        document.getElementById('guessBox').style.display = 'none';

        if (currentRound === 5) {
            showEndGameSummary();
        } else {
            showNextButton();
        }

        return;
    }

    feedback.innerHTML = `Not in the square or population < 15,000`;

    if (data.matched_city) {
        showIncorrectGuessedCity(window.geoViewer, data.matched_city);
    }

    playFail();
    input.focus();
}

function showGuessedCity(viewer, result) {
    viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(result.longitude, result.latitude),
        point: {
            pixelSize: 8,
            color: Cesium.Color.LIME,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
        },
        label: {
            text: result.city,
            font: '14px sans-serif',
            showBackground: true,
            horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
            pixelOffset: new Cesium.Cartesian2(8, 0),
        }
    });
}

function getSfxCtx() {
    if (!sfxCtx) {
        sfxCtx = new (window.AudioContext || window.webkitAudioContext)();
    }

    return sfxCtx;
}

async function warmUpSfx() {
    if (!sfxWarmupPromise) {
        sfxWarmupPromise = (async () => {
            const ctx = getSfxCtx();

            await ctx.resume();

            await new Promise((resolve) => {
                const o = ctx.createOscillator();
                const g = ctx.createGain();
                const start = ctx.currentTime + 0.05;
                const end = start + 0.25;

                o.type = 'sine';
                o.frequency.setValueAtTime(440, start);

                g.gain.setValueAtTime(0.0001, start);
                g.gain.linearRampToValueAtTime(0.02, start + 0.02);
                g.gain.exponentialRampToValueAtTime(0.0001, end);

                o.onended = resolve;

                o.connect(g);
                g.connect(ctx.destination);

                o.start(start);
                o.stop(end);
            });
        })();
    }

    return sfxWarmupPromise;
}

function playTone({ type, frequency, duration, volume = 0.03 }) {
    const ctx = getSfxCtx();
    const start = ctx.currentTime + 0.02;
    const end = start + duration;

    const o = ctx.createOscillator();
    const g = ctx.createGain();

    o.type = type;
    o.frequency.setValueAtTime(frequency, start);

    g.gain.cancelScheduledValues(start);
    g.gain.setValueAtTime(0.0001, start);
    g.gain.linearRampToValueAtTime(volume, start + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, end);

    o.connect(g);
    g.connect(ctx.destination);

    o.start(start);
    o.stop(end);
}

function playSuccess() {
    playTone({ type: 'sine', frequency: 800, duration: 1.5 });
}

function playFail() {
    playTone({ type: 'sawtooth', frequency: 200, duration: 1.5 });
}

function fmt(v) {
    return Number(v).toFixed(2);
}

function numberFmt(v) {
    return new Intl.NumberFormat().format(v);
}

function ordinal(n) {
    const mod100 = n % 100;

    if (mod100 >= 11 && mod100 <= 13) {
        return `${n}th`;
    }

    const mod10 = n % 10;

    if (mod10 === 1) {
        return `${n}st`;
    }

    if (mod10 === 2) {
        return `${n}nd`;
    }

    if (mod10 === 3) {
        return `${n}rd`;
    }

    return `${n}th`;
}

function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function addRoundRow(result, roundNumber) {
    const tbody = document.querySelector('#roundTable tbody');
    const totalEl = document.getElementById('totalPoints');
    const tr = document.createElement('tr');

    tr.innerHTML = `
        <td>${roundNumber}</td>
        <td><span class="round-city">${escapeHtml(result.city)}</span></td>
        <td>${numberFmt(result.population)}</td>
        <td>${result.rank}</td>
        <td>${numberFmt(result.score)}</td>
    `;

    tbody.appendChild(tr);

    const currentTotal = parseInt(totalEl.textContent.replace(/,/g, '')) || 0;
    totalEl.textContent = numberFmt(currentTotal + result.score);
}

function showNextButton() {
    const btn = document.getElementById('nextBtn');
    nextBtn.textContent = currentRound === 5 ? 'Finish Game' : 'Next Round';
    btn.style.display = 'inline-block';
}

async function fetchPlayerStats() {
    const response = await fetch('/api/player-stats');
    return await response.json();
}

function wireStatsOverlay() {
    const overlay = document.getElementById('statsOverlay');
    const closeBtn = document.getElementById('statsCloseBtn');
    const backdrop = overlay.querySelector('.stats-backdrop');

    closeBtn.onclick = hideStatsOverlay;
    backdrop.onclick = hideStatsOverlay;

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && overlay.style.display !== 'none') {
            hideStatsOverlay();
        }
    });
}

function hideStatsOverlay() {
    document.getElementById('statsOverlay').style.display = 'none';
}

function showStatsOverlay() {
    document.getElementById('statsOverlay').style.display = 'block';
}

function renderStatsChart(stats) {
    const svg = document.getElementById('statsChart');
    const points = stats.graph_points || [];
    const width = 640;
    const height = 220;
    const leftPad = 22;
    const rightPad = 14;
    const topPad = 14;
    const bottomPad = 26;
    const innerWidth = width - leftPad - rightPad;
    const innerHeight = height - topPad - bottomPad;

    if (points.length === 0) {
        svg.innerHTML = `
            <text x="${width / 2}" y="${height / 2}" text-anchor="middle" fill="#9dacbf" font-size="16">
                No games yet
            </text>
        `;
        return;
    }

    const scores = points.map(p => p.score);
    const maxScore = Math.max(...scores, 1);
    const minScore = Math.min(...scores, 0);
    const range = Math.max(maxScore - minScore, 1);

    const xFor = (index) => {
        if (points.length === 1) {
            return leftPad + innerWidth / 2;
        }
        return leftPad + (index / (points.length - 1)) * innerWidth;
    };

    const yFor = (score) => topPad + ((maxScore - score) / range) * innerHeight;

    const polylinePoints = points
        .map((p, i) => `${xFor(i)},${yFor(p.score)}`)
        .join(' ');

    const averageY = yFor(stats.average_score || 0);

    const circles = points.map((p, i) => `
        <circle cx="${xFor(i)}" cy="${yFor(p.score)}" r="4.5" fill="#8fd3ff"></circle>
    `).join('');

    const labels = points.map((p, i) => `
        <text x="${xFor(i)}" y="${height - 8}" text-anchor="middle" fill="#9dacbf" font-size="10">
            ${p.game_date.slice(5)}
        </text>
    `).join('');

    svg.innerHTML = `
        <line x1="${leftPad}" y1="${averageY}" x2="${width - rightPad}" y2="${averageY}"
              stroke="#4d607a" stroke-width="1.5" stroke-dasharray="5 5"></line>

        <polyline fill="none" stroke="#8fd3ff" stroke-width="3" points="${polylinePoints}"></polyline>

        ${circles}
        ${labels}

        <text x="${leftPad}" y="${averageY - 8}" fill="#9dacbf" font-size="11">Avg ${numberFmt(stats.average_score || 0)}</text>
        <text x="${leftPad}" y="${topPad + 10}" fill="#9dacbf" font-size="11">${numberFmt(maxScore)}</text>
        <text x="${leftPad}" y="${height - bottomPad + 4}" fill="#9dacbf" font-size="11">${numberFmt(minScore)}</text>
    `;
}

function renderStatsOverlay(stats) {
    document.getElementById('statsCurrentStreak').textContent = numberFmt(stats.current_streak || 0);
    document.getElementById('statsAverageScore').textContent = numberFmt(stats.average_score || 0);
    document.getElementById('statsBestScore').textContent = numberFmt(stats.best_score || 0);
    document.getElementById('statsGamesPlayed').textContent = numberFmt(stats.games_played || 0);
    document.getElementById('statsLongestStreak').textContent = numberFmt(stats.longest_streak || 0);
    document.getElementById('statsMedianScore').textContent = numberFmt(stats.median_score || 0);
    document.getElementById('statsLastScore').textContent = numberFmt(stats.last_score || 0);

    const bestGuess = stats.best_guess;
    document.getElementById('statsBestGuess').innerHTML = bestGuess
        ? `<div>${escapeHtml(bestGuess.city_name)}</div>
           <div style="font-size:14px; color:#b7c4d4; font-weight:400; margin-top:4px;">
               ${numberFmt(bestGuess.score)} pts · ${escapeHtml(bestGuess.game_date)} · Round ${bestGuess.round_number}
           </div>`
        : '—';

    renderStatsChart(stats);
}

async function showEndGameSummary() {
    const total = document.getElementById('totalPoints').textContent;
    const rows = Array.from(document.querySelectorAll('#roundTable tbody tr'));

    let bestRound = null;
    let bestPoints = -1;

    for (const row of rows) {
        const cells = row.querySelectorAll('td');
        const round = cells[0].textContent.trim();
        const city = cells[1].textContent.trim();
        const points = parseInt(cells[4].textContent.replace(/,/g, ''), 10) || 0;

        if (points > bestPoints) {
            bestPoints = points;
            bestRound = { round, city, points };
        }
    }

    const avg = rows.length ? Math.round((parseInt(total.replace(/,/g, ''), 10) || 0) / rows.length) : 0;
    const feedback = document.getElementById('guessFeedback');

    feedback.innerHTML = `
        <div><b>Game Complete</b></div>
        <div style="margin-top:8px;">Final score: <b>${escapeHtml(total)}</b></div>
        <div>Average per round: <b>${numberFmt(avg)}</b></div>
        ${bestRound ? `<div style="margin-top:8px;">Best round: <b>Round ${escapeHtml(bestRound.round)}</b> · ${escapeHtml(bestRound.city)} · <b>${numberFmt(bestRound.points)}</b> pts</div>` : ''}
    `;

    const stats = await fetchPlayerStats();
    renderStatsOverlay(stats);
    showStatsOverlay();
}
function showIncorrectGuessedCity(viewer, city) {
    const entity = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(city.longitude, city.latitude),
        point: {
            pixelSize: 8,
            color: Cesium.Color.RED.withAlpha(0.95),
            outlineColor: Cesium.Color.BLACK.withAlpha(0.8),
            outlineWidth: 2,
        },
        label: {
            text: city.city_name,
            font: '14px sans-serif',
            fillColor: Cesium.Color.RED.withAlpha(0.95),
            showBackground: true,
            backgroundColor: Cesium.Color.BLACK.withAlpha(0.65),
            horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
            pixelOffset: new Cesium.Cartesian2(8, 0),
        }
    });

    let alpha = 0.95;
    const intervalId = window.setInterval(() => {
        alpha -= 0.06;

        if (alpha <= 0) {
            window.clearInterval(intervalId);
            viewer.entities.remove(entity);
            return;
        }

        entity.point.color = Cesium.Color.RED.withAlpha(alpha);
        entity.point.outlineColor = Cesium.Color.BLACK.withAlpha(Math.max(alpha - 0.15, 0));
        entity.label.fillColor = Cesium.Color.RED.withAlpha(alpha);
        entity.label.backgroundColor = Cesium.Color.BLACK.withAlpha(Math.max(alpha - 0.3, 0));
    }, 60);
}

init();