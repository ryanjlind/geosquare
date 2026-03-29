(function () {
    function isMobile() {
        return window.matchMedia('(max-width: 768px)').matches;
    }

    function initMobile() {
        if (!isMobile()) return;
        if (document.body.dataset.mobileInit === 'true') return;

        const sidebar = document.getElementById('sidebar');
        const guessBox = document.getElementById('guessBox');
        const guessFeedback = document.getElementById('guessFeedback');
        const nextBtn = document.getElementById('nextBtn');
        const closeBtn = document.getElementById('mobileDrawerCloseBtn');

        if (!sidebar || !guessBox || !guessFeedback || !nextBtn || !closeBtn) return;

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

        topbar.querySelector('.mobile-feedback-host').appendChild(guessFeedback);
        bottomTray.appendChild(guessBox);
        bottomTray.appendChild(nextBtn);

        function openDrawer() {
            sidebar.classList.add('mobile-open');
            scrim.classList.add('mobile-open');
        }

        function closeDrawer() {
            sidebar.classList.remove('mobile-open');
            scrim.classList.remove('mobile-open');
        }

        function syncViewportVars() {
            const root = document.documentElement;
            const vv = window.visualViewport;

            let vh = window.innerHeight;
            let offsetTop = 0;
            let keyboardInset = 0;

            if (vv) {
                vh = vv.height;
                offsetTop = vv.offsetTop;
                keyboardInset = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
            }

            root.style.setProperty('--mobile-vh', `${vh}px`);
            root.style.setProperty('--mobile-offset-top', `${offsetTop}px`);
            root.style.setProperty('--mobile-keyboard-inset', `${keyboardInset}px`);
        }

        document.getElementById('mobileMenuBtn').addEventListener('click', openDrawer);
        closeBtn.addEventListener('click', closeDrawer);
        scrim.addEventListener('click', closeDrawer);

        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', syncViewportVars);
            window.visualViewport.addEventListener('scroll', syncViewportVars);
        }

        window.addEventListener('resize', syncViewportVars);

        syncViewportVars();

        document.body.dataset.mobileInit = 'true';
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMobile);
    } else {
        initMobile();
    }
})();