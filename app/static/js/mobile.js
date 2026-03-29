(function () {
    function isMobileLayout() {
        return window.matchMedia('(max-width: 768px)').matches;
    }

    function initMobileLayout() {
        if (!isMobileLayout()) {
            return;
        }

        if (document.body.dataset.mobileLayoutInitialized === 'true') {
            return;
        }

        const sidebar = document.getElementById('sidebar');
        const meta = document.getElementById('meta');
        const guessInput = document.getElementById('guessInput');
        const guessBtn = document.getElementById('guessBtn');
        const passBtn = document.getElementById('passBtn');
        const nextBtn = document.getElementById('nextBtn');
        const guessFeedback = document.getElementById('guessFeedback');
        const closeBtn = document.getElementById('mobileDrawerCloseBtn');

        if (!sidebar || !meta || !guessInput || !guessBtn || !passBtn || !nextBtn || !guessFeedback || !closeBtn) {
            return;
        }

        const scrim = document.createElement('div');
        scrim.className = 'mobile-drawer-scrim';
        scrim.id = 'mobileDrawerScrim';
        document.body.appendChild(scrim);

        const topbar = document.createElement('div');
        topbar.className = 'mobile-topbar';
        topbar.innerHTML = `
            <button id="mobileMenuBtn" class="mobile-menu-btn" type="button">Menu</button>
            <div class="mobile-meta-host"></div>
            <div class="mobile-title">GeoSquare</div>
        `;
        document.body.appendChild(topbar);

        const bottomTray = document.createElement('div');
        bottomTray.className = 'mobile-bottomtray';
        bottomTray.id = 'mobileBottomTray';
        document.body.appendChild(bottomTray);

        const nextRow = document.createElement('div');
        nextRow.className = 'mobile-next-row';
        nextRow.id = 'mobileNextRow';
        document.body.appendChild(nextRow);

        const feedbackBox = document.createElement('div');
        feedbackBox.className = 'mobile-feedback';
        feedbackBox.id = 'mobileFeedback';
        document.body.appendChild(feedbackBox);

        topbar.querySelector('.mobile-meta-host').appendChild(meta);

        bottomTray.appendChild(guessInput);
        bottomTray.appendChild(guessBtn);
        bottomTray.appendChild(passBtn);

        nextRow.appendChild(nextBtn);
        feedbackBox.appendChild(guessFeedback);

        function syncFloatingState() {
            const hasFeedback = guessFeedback.textContent.trim().length > 0 || guessFeedback.children.length > 0;
            feedbackBox.classList.toggle('show', hasFeedback);

            const nextVisible = getComputedStyle(nextBtn).display !== 'none';
            nextRow.classList.toggle('show', nextVisible);
        }

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

        const observer = new MutationObserver(syncFloatingState);
        observer.observe(guessFeedback, { childList: true, subtree: true, characterData: true });
        observer.observe(nextBtn, { attributes: true, attributeFilter: ['style', 'class', 'hidden'] });

        syncFloatingState();

        window.addEventListener('resize', function () {
            if (!isMobileLayout()) {
                window.location.reload();
            }
        });

        document.body.dataset.mobileLayoutInitialized = 'true';
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMobileLayout);
    } else {
        initMobileLayout();
    }
})();