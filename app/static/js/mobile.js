(function () {
    function isMobile() {
        return window.matchMedia('(max-width: 768px)').matches;
    }

    function initMobile() {
        if (!isMobile()) return;

        if (document.body.dataset.mobileInit === 'true') return;

        const sidebar = document.getElementById('sidebar');
        const guessInput = document.getElementById('guessInput');
        const guessBtn = document.getElementById('guessBtn');
        const passBtn = document.getElementById('passBtn');
        const guessFeedback = document.getElementById('guessFeedback');
        const nextBtn = document.getElementById('nextBtn');
        const closeBtn = document.getElementById('mobileDrawerCloseBtn');

        if (!sidebar || !guessInput || !guessBtn || !passBtn || !guessFeedback || !nextBtn || !closeBtn) return;

        const scrim = document.createElement('div');
        scrim.className = 'mobile-drawer-scrim';
        document.body.appendChild(scrim);

        const topbar = document.createElement('div');
        topbar.className = 'mobile-topbar';
        topbar.innerHTML = `
            <button id="mobileMenuBtn" class="mobile-menu-btn" type="button">Menu</button>
            <div class="mobile-feedback-host"></div>
            <div class="mobile-title">GeoSquare</div>
        `;
        document.body.appendChild(topbar);

        const bottomTray = document.createElement('div');
        bottomTray.className = 'mobile-bottomtray';
        document.body.appendChild(bottomTray);

        bottomTray.appendChild(guessInput);
        bottomTray.appendChild(guessBtn);
        bottomTray.appendChild(passBtn);

        topbar.querySelector('.mobile-feedback-host').appendChild(guessFeedback);

        function openDrawer() {
            sidebar.classList.add('mobile-open');
            scrim.classList.add('mobile-open');
            document.body.style.overflow = 'hidden';
        }

        function closeDrawer() {
            sidebar.classList.remove('mobile-open');
            scrim.classList.remove('mobile-open');
            document.body.style.overflow = '';
        }

        document.getElementById('mobileMenuBtn').addEventListener('click', openDrawer);
        closeBtn.addEventListener('click', closeDrawer);
        scrim.addEventListener('click', closeDrawer);

        document.body.dataset.mobileInit = 'true';
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMobile);
    } else {
        initMobile();
    }
})();