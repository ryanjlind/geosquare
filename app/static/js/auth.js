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