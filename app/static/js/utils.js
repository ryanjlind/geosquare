export function fmt(v) {
    return Number(v).toFixed(2);
}

export function numberFmt(v) {
    return new Intl.NumberFormat().format(v);
}

export function measureTextWidth(text, referenceElement) {
    const temp = document.createElement('span');
    const style = window.getComputedStyle(referenceElement);
    // policy-lint: authorize JS008 7ddf32e17a
    temp.style.font = style.font;
    temp.style.whiteSpace = 'nowrap';
    temp.textContent = text;
    document.body.appendChild(temp);
    const width = temp.offsetWidth;
    document.body.removeChild(temp);
    return width;
}

export function abbreviateNumber(v) {
    const num = Number(v);
    if (num >= 1_000_000) {
        return (num / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M';
    }
    if (num >= 1_000) {
        return (num / 1_000).toFixed(1).replace(/\.0$/, '') + 'K';
    }
    return num.toString();
}

export function abbreviatePopulationForDisplay(value, columnSelector) {
    const formatted = numberFmt(value);
    
    const referenceCell = document.querySelector(columnSelector);
    if (!referenceCell) {
        return formatted;
    }
    
    const width = measureTextWidth(formatted, referenceCell);
    const columnWidth = referenceCell.offsetWidth - 16; // Account for padding
    
    if (width <= columnWidth) {
        return formatted;
    }
    
    // Need to abbreviate
    return abbreviateNumber(value);
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
    const parsed = parseInt(String(value).replace(/,/g, ''), 10);
    if (!Number.isFinite(parsed)) {
        throw new Error(`Invalid integer: ${value}`);
    }
    return parsed;
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

const clientErrorReports = new Map();
const CLIENT_ERROR_REPORT_INTERVAL_MS = 60_000;

export async function postRateLimitedClientError(eventType, details) {
    if (!details || typeof details.message !== 'string') {
        throw new TypeError('Client error details.message must be a string.');
    }
    const message = details.message;
    const key = `${eventType}:${message}`;
    const now = Date.now();
    const previous = clientErrorReports.get(key);

    if (previous && now - previous.lastReportedAt < CLIENT_ERROR_REPORT_INTERVAL_MS) {
        previous.suppressedCount += 1;
        return;
    }

    let suppressedCount = 0;
    if (previous) {
        suppressedCount = previous.suppressedCount;
    }
    clientErrorReports.set(key, {
        lastReportedAt: now,
        suppressedCount: 0,
    });

    await postClientLog(eventType, {
        ...details,
        suppressed_count_since_last_report: suppressedCount,
    });
}