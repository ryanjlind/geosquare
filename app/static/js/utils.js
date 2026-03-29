export function fmt(v) {
    return Number(v).toFixed(2);
}

export function numberFmt(v) {
    return new Intl.NumberFormat().format(v);
}

export function ordinal(n) {
    const mod100 = n % 100;

    if (mod100 >= 11 && mod100 <= 13) {
        return `${n}th`;
    }

    const mod10 = n % 10;

    if (mod10 === 1) {
        return `${n}st`;
    }

    if (mod10 === 2) {
        return `${n}nd`;
    }

    if (mod10 === 3) {
        return `${n}rd`;
    }

    return `${n}th`;
}

export function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

export function parseFormattedInt(value) {
    return parseInt(String(value).replace(/,/g, ''), 10) || 0;
}

export async function postClientLog(eventType, details) {
    try {
        await fetch('/api/client-log', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                event_type: eventType,
                url: window.location.href,
                user_agent: navigator.userAgent,
                details: details
            })
        });
    } catch (err) {
        console.error('Failed to send client log', err);
    }
}