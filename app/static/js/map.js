import { postClientLog } from './utils.js';

export async function initCesium() {
    await postClientLog('init_cesium_started', {
        href: window.location.href,
        userAgent: navigator.userAgent
    });

    try {
        await postClientLog('arcgis_provider_create_started', {
            url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer'
        });

        const arcGisImageryProvider = await Cesium.ArcGisMapServerImageryProvider.fromUrl(
            'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer'
        );

        await postClientLog('arcgis_provider_create_succeeded', {});

        if (arcGisImageryProvider.errorEvent) {
            arcGisImageryProvider.errorEvent.addEventListener(function (error) {
                postClientLog('arcgis_provider_error', {
                    message: error?.message || null,
                    timesRetried: error?.timesRetried ?? null,
                    retry: error?.retry ?? null,
                    x: error?.x ?? null,
                    y: error?.y ?? null,
                    level: error?.level ?? null,
                    providerErrorMessage: error?.error?.message || null,
                    providerErrorStack: error?.error?.stack || null
                });
            });
        }

        const baseLayer = new Cesium.ImageryLayer(arcGisImageryProvider);

        await postClientLog('imagery_layer_constructed', {
            show: baseLayer.show,
            alpha: baseLayer.alpha
        });

        window.geoViewer = new Cesium.Viewer('cesiumContainer', {
            animation: false,
            timeline: false,
            sceneModePicker: false,
            baseLayerPicker: false,
            geocoder: false,
            homeButton: false,
            navigationHelpButton: false,
            fullscreenButton: false,
            infoBox: false,
            selectionIndicator: false,
            shouldAnimate: false,
            baseLayer: baseLayer
        });

        await postClientLog('viewer_constructed', {
            imageryLayerCount: window.geoViewer.imageryLayers.length,
            canvasWidth: window.geoViewer.canvas?.width ?? null,
            canvasHeight: window.geoViewer.canvas?.height ?? null,
            clientWidth: window.geoViewer.canvas?.clientWidth ?? null,
            clientHeight: window.geoViewer.canvas?.clientHeight ?? null
        });

        window.geoViewer.scene.globe.enableLighting = false;
        window.geoViewer.scene.screenSpaceCameraController.inertiaSpin = 0;
        window.geoViewer.scene.screenSpaceCameraController.inertiaTranslate = 0;
        window.geoViewer.scene.screenSpaceCameraController.inertiaZoom = 0;
        window.geoViewer.scene.screenSpaceCameraController.minimumZoomDistance = 150000;

        await postClientLog('viewer_config_applied', {
            minimumZoomDistance: window.geoViewer.scene.screenSpaceCameraController.minimumZoomDistance
        });

        window.geoViewer.scene.renderError.addEventListener(function (scene, error) {
            postClientLog('cesium_render_error', {
                message: error?.message || String(error),
                stack: error?.stack || null
            });
        });

        await postClientLog('init_cesium_completed', {
            imageryLayerCount: window.geoViewer.imageryLayers.length,
            baseLayerShow: window.geoViewer.imageryLayers.get(0)?.show ?? null,
            baseLayerAlpha: window.geoViewer.imageryLayers.get(0)?.alpha ?? null
        });
    } catch (error) {
        await postClientLog('init_cesium_failed', {
            message: error?.message || String(error),
            stack: error?.stack || null
        });
        throw error;
    }
}

export function clearMap() {
    window.geoViewer.entities.removeAll();
}

export function drawSquare(data) {
    const b = data.bounds;

    window.geoViewer.entities.add({
        name: 'Daily square',
        rectangle: {
            coordinates: Cesium.Rectangle.fromDegrees(b.min_lon, b.min_lat, b.max_lon, b.max_lat),
            material: Cesium.Color.YELLOW.withAlpha(0.2),
            outline: true,
            outlineColor: Cesium.Color.YELLOW,
            outlineWidth: 2,
        }
    });
}

export function drawCities(cities) {
    for (const city of cities) {
        window.geoViewer.entities.add({
            position: Cesium.Cartesian3.fromDegrees(city.longitude, city.latitude),
            point: {
                pixelSize: 6,
                color: Cesium.Color.CYAN,
            },
            label: {
                text: city.city_name,
                font: '14px sans-serif',
                showBackground: true,
                horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
                pixelOffset: new Cesium.Cartesian2(8, 0),
                distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0.0, 30000000.0),
            }
        });
    }
}

export function zoomToSquare(bounds) {
    const centerLat = (bounds.min_lat + bounds.max_lat) / 2;
    const centerLon = (bounds.min_lon + bounds.max_lon) / 2;

    window.geoViewer.camera.setView({
        destination: Cesium.Cartesian3.fromDegrees(centerLon, centerLat, 10000000)
    });

    window.geoViewer.clock.shouldAnimate = false;
}

export function renderRoundMap(data) {
    clearMap();
    drawSquare(data);
    zoomToSquare(data.bounds);
}

export function showGuessedCity(result) {
    window.geoViewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(result.longitude, result.latitude),
        point: {
            pixelSize: 8,
            color: Cesium.Color.LIME,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
        },
        label: {
            text: result.city,
            font: '14px sans-serif',
            showBackground: true,
            horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
            pixelOffset: new Cesium.Cartesian2(8, 0),
        }
    });
}

export function showIncorrectGuessedCity(city) {
    const entity = window.geoViewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(city.longitude, city.latitude),
        point: {
            pixelSize: 8,
            color: Cesium.Color.RED.withAlpha(0.95),
            outlineColor: Cesium.Color.BLACK.withAlpha(0.8),
            outlineWidth: 2,
        },
        label: {
            text: city.city_name,
            font: '14px sans-serif',
            fillColor: Cesium.Color.RED.withAlpha(0.95),
            showBackground: true,
            backgroundColor: Cesium.Color.BLACK.withAlpha(0.65),
            horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
            pixelOffset: new Cesium.Cartesian2(8, 0),
        }
    });

    let alpha = 0.95;
    const intervalId = window.setInterval(() => {
        alpha -= 0.03;

        if (alpha <= 0) {
            window.clearInterval(intervalId);
            window.geoViewer.entities.remove(entity);
            return;
        }

        entity.point.color = Cesium.Color.RED.withAlpha(alpha);
        entity.point.outlineColor = Cesium.Color.BLACK.withAlpha(Math.max(alpha - 0.15, 0));
        entity.label.fillColor = Cesium.Color.RED.withAlpha(alpha);
        entity.label.backgroundColor = Cesium.Color.BLACK.withAlpha(Math.max(alpha - 0.3, 0));
    }, 60);
}