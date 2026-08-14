async function collectUserAgentData() {
    if (!navigator.userAgentData) {
        return null;
    }

    try {
        return await navigator.userAgentData.getHighEntropyValues([
            'architecture',
            'bitness',
            'fullVersionList',
            'model',
            'platformVersion',
            'wow64',
        ]);
    } catch (error) {
        return {
            error: error?.message || String(error),
        };
    }
}

function collectWebGlDiagnostics(canvas) {
    if (!canvas) {
        return null;
    }

    const context = canvas.getContext('webgl2') || canvas.getContext('webgl');
    if (!context) {
        return {
            available: false,
        };
    }

    const debugRendererInfo = context.getExtension('WEBGL_debug_renderer_info');

    return {
        available: true,
        version: context.getParameter(context.VERSION),
        shadingLanguageVersion: context.getParameter(context.SHADING_LANGUAGE_VERSION),
        vendor: context.getParameter(context.VENDOR),
        renderer: context.getParameter(context.RENDERER),
        unmaskedVendor: debugRendererInfo
            ? context.getParameter(debugRendererInfo.UNMASKED_VENDOR_WEBGL)
            : null,
        unmaskedRenderer: debugRendererInfo
            ? context.getParameter(debugRendererInfo.UNMASKED_RENDERER_WEBGL)
            : null,
        contextLost: context.isContextLost(),
        contextAttributes: context.getContextAttributes(),
        drawingBuffer: {
            width: context.drawingBufferWidth,
            height: context.drawingBufferHeight,
        },
    };
}

function collectCesiumDiagnostics() {
    const viewer = window.geoViewer;
    if (!viewer) {
        return null;
    }

    const scene = viewer.scene;
    const canvas = scene.canvas;
    const imageryLayer = viewer.imageryLayers.length > 0
        ? viewer.imageryLayers.get(0)
        : null;

    return {
        version: window.Cesium?.VERSION || null,
        cameraHeight: viewer.camera.positionCartographic.height,
        canvas: {
            width: canvas.width,
            height: canvas.height,
            clientWidth: canvas.clientWidth,
            clientHeight: canvas.clientHeight,
        },
        globe: {
            tilesLoaded: scene.globe.tilesLoaded,
        },
        imagery: {
            layerCount: viewer.imageryLayers.length,
            providerReady: imageryLayer?.imageryProvider?.ready ?? null,
        },
        webgl: collectWebGlDiagnostics(canvas),
    };
}

async function collectDiagnostics() {
    const visualViewport = window.visualViewport;

    return {
        userAgent: navigator.userAgent,
        userAgentData: await collectUserAgentData(),
        url: window.location.href,
        viewport: {
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
            devicePixelRatio: window.devicePixelRatio,
            visualViewport: visualViewport ? {
                width: visualViewport.width,
                height: visualViewport.height,
                offsetLeft: visualViewport.offsetLeft,
                offsetTop: visualViewport.offsetTop,
                scale: visualViewport.scale,
            } : null,
        },
        screen: {
            width: window.screen.width,
            height: window.screen.height,
            availWidth: window.screen.availWidth,
            availHeight: window.screen.availHeight,
            colorDepth: window.screen.colorDepth,
            pixelDepth: window.screen.pixelDepth,
            orientation: window.screen.orientation ? {
                type: window.screen.orientation.type,
                angle: window.screen.orientation.angle,
            } : null,
        },
        cesium: collectCesiumDiagnostics(),
    };
}

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
        const includeDiagnostics = document.getElementById('fbDiagnostics').checked;

        formData.append('type', document.getElementById('fbType').value);
        formData.append('description', document.getElementById('fbDescription').value);
        formData.append('platform', document.getElementById('fbPlatform').value);
        formData.append('includeDiagnostics', includeDiagnostics);
        formData.append('allowEmail', document.getElementById('fbAllowEmail').checked);
        formData.append('email', document.getElementById('fbEmail').value);

        const files = document.getElementById('fbScreenshots').files;
        for (let i = 0; i < files.length; i++) {
            formData.append('screenshots', files[i]);
        }

        if (includeDiagnostics) {
            try {
                formData.append('diagnostics', JSON.stringify(await collectDiagnostics()));
            } catch (error) {
                formData.append('diagnostics', JSON.stringify({
                    collectionError: error?.message || String(error),
                }));
            }
        }

        await fetch('/api/feedback', {
            method: 'POST',
            body: formData
        });

        overlay.style.display = 'none';
    };
}