import { fetchJson } from './api.js';

let authCallbacks = {
    onAuthSuccess: null,
    onAuthConflict: null,
    onAuthError: null,
};

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

export function initAuth(state, callbacks = {}) {
    authCallbacks = {
        onAuthSuccess: callbacks.onAuthSuccess || null,
        onAuthConflict: callbacks.onAuthConflict || null,
        onAuthError: callbacks.onAuthError || null,
    };

    setAuthUi(state.is_authenticated);
    wireAuthButtons();
    wireAuthMessageListener();
}

export async function resolveAuthConflict(action) {
    const { response, data } = await fetchJson('/auth/resolve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
    });

    if (!response.ok) {
        if (authCallbacks.onAuthError) {
            authCallbacks.onAuthError(data.error || 'Unable to resolve login conflict.');
        } else {
            console.log(data.error || 'Unable to resolve login conflict.');
        }
        return;
    }

    if (authCallbacks.onAuthSuccess) {
        await authCallbacks.onAuthSuccess();
    }
}

function wireAuthButtons() {
    const loginBtn = document.getElementById('loginBtn');
    const logoutBtn = document.getElementById('logoutBtn');

    if (loginBtn) loginBtn.onclick = login;
    if (logoutBtn) logoutBtn.onclick = logout;
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

function wireAuthMessageListener() {
    if (window.__authMessageListenerWired) return;
    window.__authMessageListenerWired = true;

    window.addEventListener('message', async (event) => {
        if (event.origin !== window.location.origin) return;
        if (!event.data || typeof event.data !== 'object') return;

        if (event.data.type === 'auth_success') {
            if (authCallbacks.onAuthSuccess) {
                await authCallbacks.onAuthSuccess();
            }
            return;
        }

        if (event.data.type === 'auth_conflict') {
            if (authCallbacks.onAuthConflict) {
                authCallbacks.onAuthConflict(event.data.message);
            }
            return;
        }

        if (event.data.type === 'auth_error') {
            if (authCallbacks.onAuthError) {
                authCallbacks.onAuthError(event.data.message || 'Login failed.');
            } else {
                console.log(event.data.message || 'Login failed.');
            }
        }
    });
}