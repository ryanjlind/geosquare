import { gameState } from './state.js';

(function () {
    function isMobile() {
        return window.matchMedia('(max-width: 768px)').matches;
    }

    function initProfileMobile({
        sidebar,
        closeBtn,
    }) {
        const scrim = document.createElement('div');
        scrim.className = 'mobile-drawer-scrim';
        document.body.appendChild(scrim);

        const topbar = document.createElement('div');
        topbar.className = 'mobile-topbar';
        topbar.innerHTML = `
            <button id="mobileMenuBtn" class="mobile-menu-btn" type="button">Menu</button>
            <div class="mobile-title">GeoSquare</div>
            <div></div>
        `;
        document.body.appendChild(topbar);

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
    }

    function initGameMobile({
        sidebar,
        closeBtn,
        guessBox,
        guessFeedback,
        nextBtn,
    }) {
        const scrim = document.createElement('div');
        scrim.className = 'mobile-drawer-scrim';
        document.body.appendChild(scrim);

        const topbar = document.createElement('div');
        topbar.className = 'mobile-topbar';
        topbar.innerHTML = `
            <button id="mobileMenuBtn" class="mobile-menu-btn" type="button">Menu</button>
            <div class="mobile-title">GeoSquare</div>
            <div class="mobile-hero-stats">
                <div class="mobile-hero-stat">
                    <div class="mobile-hero-stat-label">Round</div>
                    <div id="mobileRoundStat" class="mobile-hero-stat-value">1</div>
                </div>
                <div class="mobile-hero-stat">
                    <div class="mobile-hero-stat-label">Points</div>
                    <div id="mobilePointsStat" class="mobile-hero-stat-value">0</div>
                </div>
                <div class="mobile-hero-stat">
                    <div class="mobile-hero-stat-label">Cities</div>
                    <div id="mobileCitiesStat" class="mobile-hero-stat-value">0</div>
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

        function syncMobileHeroStats() {
            const mobileRoundStat = document.getElementById('mobileRoundStat');
            const mobilePointsStat = document.getElementById('mobilePointsStat');
            const mobileCitiesStat = document.getElementById('mobileCitiesStat');
            const totalPoints = document.getElementById('totalPoints');
            const meta = document.getElementById('meta');

            if (mobileRoundStat) {
                mobileRoundStat.textContent = String(gameState.currentRound);
            }

            if (mobilePointsStat && totalPoints) {
                mobilePointsStat.textContent = totalPoints.textContent;
            }

            if (mobileCitiesStat && meta) {
                const cityValue = meta.querySelector('[data-mobile-cities-value]');
                mobileCitiesStat.textContent = cityValue ? cityValue.textContent : '0';
            }
        }

        const scrimEl = scrim;

        function openDrawer() {
            sidebar.classList.add('mobile-open');
            scrimEl.classList.add('mobile-open');
        }

        function closeDrawer() {
            sidebar.classList.remove('mobile-open');
            scrimEl.classList.remove('mobile-open');
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
        scrimEl.addEventListener('click', closeDrawer);

        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', syncViewportVars);
            window.visualViewport.addEventListener('scroll', syncViewportVars);
        }

        window.addEventListener('resize', syncViewportVars);

        syncViewportVars();
        syncMobileHeroStats();

        const totalPoints = document.getElementById('totalPoints');
        const observer = new MutationObserver(syncMobileHeroStats);

        if (totalPoints) {
            observer.observe(totalPoints, { childList: true, characterData: true, subtree: true });
        }

        document.addEventListener('click', () => {
            syncMobileHeroStats();
        });
    }

    function initMobile() {
        if (!isMobile()) return;
        if (document.body.dataset.mobileInit === 'true') return;

        const sidebar = document.getElementById('sidebar');
        const closeBtn = document.getElementById('mobileDrawerCloseBtn');

        if (!sidebar || !closeBtn) return;

        const isProfilePage = document.body.classList.contains('profile-page');

        if (isProfilePage) {
            initProfileMobile({ sidebar, closeBtn });
            document.body.dataset.mobileInit = 'true';
            return;
        }

        const guessBox = document.getElementById('guessBox');
        const guessFeedback = document.getElementById('guessFeedback');
        const nextBtn = document.getElementById('nextBtn');

        if (!guessBox || !guessFeedback || !nextBtn) return;

        initGameMobile({
            sidebar,
            closeBtn,
            guessBox,
            guessFeedback,
            nextBtn,
        });

        document.body.dataset.mobileInit = 'true';
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMobile);
    } else {
        initMobile();
    }
})();