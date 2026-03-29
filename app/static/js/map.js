export async function initCesium() {
    const arcGisImageryProvider = await Cesium.ArcGisMapServerImageryProvider.fromUrl(
        'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer'
    );

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
        baseLayer: new Cesium.ImageryLayer(arcGisImageryProvider)
    });

    window.geoViewer.scene.globe.enableLighting = false;
    window.geoViewer.scene.screenSpaceCameraController.inertiaSpin = 0;
    window.geoViewer.scene.screenSpaceCameraController.inertiaTranslate = 0;
    window.geoViewer.scene.screenSpaceCameraController.inertiaZoom = 0;
    window.geoViewer.scene.screenSpaceCameraController.minimumZoomDistance = 150000;
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
        alpha -= 0.06;

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