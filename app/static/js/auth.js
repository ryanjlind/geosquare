export function login() {
    const popup = openLoginPopup();

    if (!popup) {
        console.log('Login popup was blocked.');
    }
}

export async function logout() {
    await fetch('/logout', { method: 'POST' });
    window.location.reload();
}

export function setAuthUi(isAuthenticated) {
    const loginBtn = document.getElementById('loginBtn');
    const logoutBtn = document.getElementById('logoutBtn');

    if (loginBtn) loginBtn.classList.toggle('hidden', isAuthenticated);
    if (logoutBtn) logoutBtn.classList.toggle('hidden', !isAuthenticated);
}

function openLoginPopup() {
    const width = 560;
    const height = 700;
    const left = Math.max(0, Math.round((window.screen.width - width) / 2));
    const top = Math.max(0, Math.round((window.screen.height - height) / 2));

    return window.open(
        '/login',
        'geosquare_lastlogin',
        `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`
    );
}

async function refreshAfterAuth() {
    const { response: stateResponse, data: state } = await fetchGameState();

    if (!stateResponse.ok) {
        setMetaError(state.error);
        return;
    }

    setAuthUi(state.is_authenticated);

    const data = await fetchRound(state.round_number || 1);

    gameState.currentRound = data.round_number;
    gameState.isPerfect = state.is_perfect;
    gameState.roundLocked = false;

    renderRound(data);
    restoreSavedState(state);

    if (state.completed_at) {
        setGuessControlsEnabled(false);
        hideNextButton();
        setGuessBoxVisible(false);
        await showEndGameSummary();
        return;
    }

    setGuessControlsEnabled(true);
    setGuessBoxVisible(true);
}

function ensureAuthConflictModal() {
    let modal = document.getElementById('authConflictModal');
    if (modal) return modal;

    modal = document.createElement('div');
    modal.id = 'authConflictModal';
    modal.style.display = 'none';
    modal.style.position = 'fixed';
    modal.style.inset = '0';
    modal.style.background = 'rgba(0, 0, 0, 0.7)';
    modal.style.zIndex = '10000';
    modal.style.alignItems = 'center';
    modal.style.justifyContent = 'center';
    modal.innerHTML = `
        <div style="max-width: 560px; width: calc(100% - 32px); background: #1f2937; color: white; border-radius: 12px; padding: 20px;">
            <div id="authConflictMessage" style="white-space: pre-line; line-height: 1.5; margin-bottom: 16px;"></div>
            <div style="display: flex; flex-direction: column; gap: 10px;">
                <button id="authConflictDiscardBtn" type="button">Discard the conflicting gameplay from this device</button>
                <button id="authConflictOverwriteBtn" type="button">Overwrite the gameplay in my profile with gameplay from this device</button>
                <button id="authConflictAbortBtn" type="button">Abort linking this device to my profile</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    return modal;
}

async function resolveAuthConflict(action) {
    const { response, data } = await fetchJson('/auth/resolve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
    });

    if (!response.ok) {
        console.log(data.error || 'Unable to resolve login conflict.');
        return;
    }

    hideAuthConflictModal();
    await refreshAfterAuth();
}

function showAuthConflictModal(message) {
    const modal = ensureAuthConflictModal();
    document.getElementById('authConflictMessage').textContent = message;
    document.getElementById('authConflictDiscardBtn').onclick = () => resolveAuthConflict('discard_this_device_conflicts');
    document.getElementById('authConflictOverwriteBtn').onclick = () => resolveAuthConflict('overwrite_profile');
    document.getElementById('authConflictAbortBtn').onclick = () => resolveAuthConflict('abort');
    modal.style.display = 'flex';
}

function hideAuthConflictModal() {
    const modal = document.getElementById('authConflictModal');
    if (modal) modal.style.display = 'none';
}