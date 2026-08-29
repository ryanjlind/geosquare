import { fetchJson } from './api.js?v=4';
import { numberFmt } from './utils.js?v=4';


function formatDate(dateString) {
    const date = new Date(`${dateString}T00:00:00`);
    return date.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
    });
}


function createSquareLink(pool, square) {
    const link = document.createElement('a');
    const params = new URLSearchParams({
        infinity_pool_session_id: String(pool.infinity_pool_session_id),
        round: String(square.round_number),
    });
    link.href = `/?${params.toString()}`;
    link.className = 'infinity-pool-square';
    if (square.round_number === pool.current_round) {
        link.classList.add('is-current');
    }

    const squareName = document.createElement('strong');
    squareName.textContent = `Square ${square.round_number}`;
    link.appendChild(squareName);

    const activity = document.createElement('span');
    activity.textContent = `${numberFmt(square.city_count)} cities`;
    link.appendChild(activity);

    const score = document.createElement('span');
    score.textContent = `${numberFmt(square.score)} pts`;
    link.appendChild(score);

    return link;
}


function createPool(pool) {
    const section = document.createElement('section');
    section.className = 'infinity-pool-item';

    const header = document.createElement('div');
    header.className = 'infinity-pool-header';

    const titleGroup = document.createElement('div');
    const title = document.createElement('h3');
    title.textContent = formatDate(pool.game_date);
    titleGroup.appendChild(title);

    const updated = document.createElement('div');
    updated.className = 'infinity-pool-updated';
    updated.textContent = `Last played ${new Date(pool.updated_at).toLocaleString()}`;
    titleGroup.appendChild(updated);
    header.appendChild(titleGroup);

    const total = document.createElement('div');
    total.className = 'infinity-pool-total';
    total.textContent = `${numberFmt(pool.total_score)} pts`;
    header.appendChild(total);
    section.appendChild(header);

    const squares = document.createElement('div');
    squares.className = 'infinity-pool-squares';
    pool.squares.forEach(square => squares.appendChild(createSquareLink(pool, square)));
    section.appendChild(squares);

    return section;
}


async function loadInfinityPools() {
    const status = document.getElementById('infinityPoolsStatus');
    const list = document.getElementById('infinityPoolsList');
    const { response, data } = await fetchJson('/api/profile/infinity-pools');

    if (!response.ok) {
        throw new Error(data.error || 'Unable to load Infinity Pools.');
    }

    if (!data.pools.length) {
        status.textContent = 'No Infinity Pools started yet.';
        return;
    }

    data.pools.forEach(pool => list.appendChild(createPool(pool)));
    status.classList.add('hidden');
    list.classList.remove('hidden');
}


loadInfinityPools().catch(error => {
    document.getElementById('infinityPoolsStatus').textContent = error.message;
});