(function () {
const CLIENT_LOG_ENDPOINT = '/api/client-log';
const CSRF_COOKIE_NAME = 'geosquare_csrf';
const CLIENT_ERROR_REPORT_INTERVAL_MS = 60_000;

const clientErrorReports = new Map();


function getCookie(name) {
    const prefix = `${encodeURIComponent(name)}=`;
    const cookie = document.cookie
        .split('; ')
        .find(value => value.startsWith(prefix));
    return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null;
}


function describeError(value) {
    if (value instanceof Error) {
        return {
            message: value.message,
            name: value.name,
            stack: value.stack,
        };
    }

    if (typeof value === 'string') {
        return { message: value };
    }

    return { message: String(value) };
}


function shouldReportError(value) {
    if (!(value instanceof Error)) {
        return true;
    }
    if (value.clientErrorReported === true) {
        return false;
    }
    if (Number.isInteger(value.httpStatus)) {
        return value.httpStatus < 400 || value.httpStatus >= 500;
    }
    return true;
}


function resourceUrl(target) {
    if (target instanceof HTMLScriptElement) {
        return target.src;
    }
    if (target instanceof HTMLImageElement) {
        return target.currentSrc;
    }
    if (target instanceof HTMLLinkElement) {
        return target.href;
    }
    if (target instanceof HTMLSourceElement) {
        return target.src;
    }
    return null;
}


function resourceTagName(target) {
    if (target instanceof Element) {
        return target.tagName;
    }
    return Object.prototype.toString.call(target);
}


async function postClientLog(eventType, details) {
    try {
        const headers = new Headers({ 'Content-Type': 'application/json' });
        const csrfToken = getCookie(CSRF_COOKIE_NAME);
        if (csrfToken !== null) {
            headers.set('X-CSRF-Token', csrfToken);
        }

        await fetch(CLIENT_LOG_ENDPOINT, {
            method: 'POST',
            headers,
            body: JSON.stringify({
                event_type: eventType,
                url: window.location.href,
                user_agent: navigator.userAgent,
                details,
            }),
        });
    } catch (error) {
        console.error('Failed to send client log', error);
    }
}


async function postRateLimitedClientError(eventType, details) {
    if (!details || typeof details.message !== 'string') {
        throw new TypeError('Client error details.message must be a string.');
    }

    const key = `${eventType}:${details.message}`;
    const now = Date.now();
    const previous = clientErrorReports.get(key);

    if (previous && now - previous.lastReportedAt < CLIENT_ERROR_REPORT_INTERVAL_MS) {
        previous.suppressedCount += 1;
        return;
    }

    const suppressedCount = previous ? previous.suppressedCount : 0;
    clientErrorReports.set(key, {
        lastReportedAt: now,
        suppressedCount: 0,
    });

    await postClientLog(eventType, {
        ...details,
        suppressed_count_since_last_report: suppressedCount,
    });
}


function installBrowserErrorLogging() {
    window.addEventListener('error', event => {
        if (event.target !== window) {
            const target = event.target;
            void postRateLimitedClientError('browser_resource_error', {
                message: 'Browser resource failed to load',
                tag_name: resourceTagName(target),
                resource_url: resourceUrl(target),
            });
            return;
        }

        let errorValue = event.error;
        if (errorValue === null) {
            errorValue = event.message;
        }
        if (shouldReportError(errorValue)) {
            void postRateLimitedClientError('browser_uncaught_error', {
                ...describeError(errorValue),
                filename: event.filename,
                line_number: event.lineno,
                column_number: event.colno,
            });
        }
    }, true);

    window.addEventListener('unhandledrejection', event => {
        if (shouldReportError(event.reason)) {
            void postRateLimitedClientError(
                'browser_unhandled_rejection',
                describeError(event.reason),
            );
        }
    });

    if (document.fonts) {
        document.fonts.addEventListener('loadingerror', event => {
            const families = [...event.fontfaces].map(fontFace => fontFace.family);
            void postRateLimitedClientError('browser_font_error', {
                message: `Failed to load fonts: ${families.join(', ')}`,
                font_families: families,
            });
        });
    }
}


async function postCaughtClientError(eventType, error, details) {
    if (shouldReportError(error)) {
        await postRateLimitedClientError(eventType, {
            ...describeError(error),
            ...details,
        });
    }
}


window.GeoSquareBrowserErrors = Object.freeze({
    postClientLog,
    postRateLimitedClientError,
    postCaughtClientError,
});
installBrowserErrorLogging();
}());