export function initFeedback() {
    const btn = document.getElementById('feedbackBtn');
    const overlay = document.getElementById('feedbackOverlay');
    const closeBtn = document.getElementById('feedbackCloseBtn');
    const allowEmail = document.getElementById('fbAllowEmail');
    const emailWrap = document.getElementById('fbEmailWrap');
    const submit = document.getElementById('fbSubmit');

    if (!btn || !overlay) return;

    btn.onclick = () => {
        overlay.style.display = 'block';
    };

    closeBtn.onclick = () => {
        overlay.style.display = 'none';
    };

    allowEmail.onchange = (e) => {
        emailWrap.style.display = e.target.checked ? 'block' : 'none';
    };

    submit.onclick = async () => {
        const formData = new FormData();

        formData.append('type', document.getElementById('fbType').value);
        formData.append('description', document.getElementById('fbDescription').value);
        formData.append('platform', document.getElementById('fbPlatform').value);
        formData.append('includeDiagnostics', document.getElementById('fbDiagnostics').checked);
        formData.append('allowEmail', document.getElementById('fbAllowEmail').checked);
        formData.append('email', document.getElementById('fbEmail').value);

        const files = document.getElementById('fbScreenshots').files;
        for (let i = 0; i < files.length; i++) {
            formData.append('screenshots', files[i]);
        }

        formData.append('diagnostics', JSON.stringify({
            userAgent: navigator.userAgent,
            url: window.location.href
        }));

        await fetch('/api/feedback', {
            method: 'POST',
            body: formData
        });

        overlay.style.display = 'none';
    };
}