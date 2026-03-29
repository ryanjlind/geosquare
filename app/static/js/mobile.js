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
            <div class="mobile-hero-stats">
                <div class="mobile-hero-stat">
                    <div class="mobile-hero-stat-label">Round</div>
                    <div id="mobileRoundStat" class="mobile-hero-stat-value">1</div>
                </div>
                <div class="mobile-hero-stat">
                    <div class="mobile-hero-stat-label">Points</div>
                    <div id="mobilePointsStat" class="mobile-hero-stat-value">0</div>
                </div>
            </div>
        `;
        document.body.appendChild(topbar);

        const bottomTray = document.createElement('div');
        bottomTray.className = 'mobile-bottomtray';
        document.body.appendChild(bottomTray);

        bottomTray.appendChild(guessBox);
        bottomTray.appendChild(guessFeedback);
        bottomTray.appendChild(nextBtn);

        const mobileRoundStat = document.getElementById('mobileRoundStat');
        const mobilePointsStat = document.getElementById('mobilePointsStat');
        const totalPoints = document.getElementById('totalPoints');

        function syncMobileHeroStats() {
            mobileRoundStat.textContent = String(gameState.currentRound);
            mobilePointsStat.textContent = totalPoints ? totalPoints.textContent : '0';
        }

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
        syncMobileHeroStats();

        const observer = new MutationObserver(syncMobileHeroStats);
        if (totalPoints) {
            observer.observe(totalPoints, { childList: true, characterData: true, subtree: true });
        }

        document.addEventListener('click', () => {
            syncMobileHeroStats();
        });

        document.body.dataset.mobileInit = 'true';
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMobile);
    } else {
        initMobile();
    }
})();