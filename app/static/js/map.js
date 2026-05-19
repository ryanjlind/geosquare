import { postClientLog, numberFmt } from './utils.js';
import { gameState } from './state.js';
import { expandSquareRequest } from './api.js';

let expansionEntity = null;
let currentBounds = null;
let baseSquareEntity = null;

export async function initCesium() {
    await postClientLog('init_cesium_started', {
        href: window.location.href,
        userAgent: navigator.userAgent
    });

    try {
        const arcGisImageryProvider = await Cesium.ArcGisMapServerImageryProvider.fromUrl(
            'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer'
        );

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

        window.geoViewer.scene.globe.enableLighting = false;
        window.geoViewer.scene.screenSpaceCameraController.inertiaSpin = 0;
        window.geoViewer.scene.screenSpaceCameraController.inertiaTranslate = 0;
        window.geoViewer.scene.screenSpaceCameraController.inertiaZoom = 0;
        window.geoViewer.scene.screenSpaceCameraController.minimumZoomDistance = 150000;

        window.geoViewer.scene.renderError.addEventListener(function (scene, error) {
            postClientLog('cesium_render_error', {
                message: error?.message || String(error),
                stack: error?.stack || null
            });
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

export function drawSquare(data, options = {}) {
    const { replaceExisting = true } = options;
    const b = data.bounds;

    if (replaceExisting && baseSquareEntity) {
        window.geoViewer.entities.remove(baseSquareEntity);
        baseSquareEntity = null;
    }

    const crossesDateline = b.min_lon > b.max_lon;

    const makeRect = (west, east) => {
        return window.geoViewer.entities.add({
            name: `Round ${data.round_number || ''}`.trim(),
            rectangle: {
                coordinates: Cesium.Rectangle.fromDegrees(
                    west,
                    b.min_lat,
                    east,
                    b.max_lat
                ),
                material: Cesium.Color.YELLOW.withAlpha(0.2),
                outline: true,
                outlineColor: Cesium.Color.YELLOW,
                outlineWidth: 2,
            }
        });
    };

    let entity;

    if (!crossesDateline) {
        entity = makeRect(b.min_lon, b.max_lon);
    } else {
        const westPart = makeRect(b.min_lon, 180);
        const eastPart = makeRect(-180, b.max_lon);

        entity = { westPart, eastPart };
    }

    if (replaceExisting) {
        baseSquareEntity = entity;
        setCurrentBounds(b);
    }

    return entity;
}

export function drawCities(cities) {
    for (const city of cities) {
        window.geoViewer.entities.add({
            position: Cesium.Cartesian3.fromDegrees(city.longitude, city.latitude),
            point: {
                pixelSize: city.pixel_size || 6,
                color: city.color || Cesium.Color.CYAN,
                outlineColor: city.outline_color || Cesium.Color.BLACK,
                outlineWidth: city.outline_width ?? 1,
            },
            label: {
                text: city.label || city.city_name,
                font: '14px sans-serif',
                showBackground: true,
                horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
                pixelOffset: new Cesium.Cartesian2(8, 0),
                distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0.0, 30000000.0),
            }
        });
    }
}

export function drawLabel({ text, latitude, longitude }) {
    window.geoViewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(longitude, latitude),
        label: {
            text,
            font: '16px sans-serif',
            showBackground: true,
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.CENTER,
            pixelOffset: new Cesium.Cartesian2(0, 0),
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0.0, 30000000.0),
        }
    });
}

export function zoomToSquare(bounds) {
    const centerLat = (bounds.min_lat + bounds.max_lat) / 2;
    const centerLon = (bounds.min_lon + bounds.max_lon) / 2;

    const rectangle = Cesium.Cartesian3.fromDegrees(centerLon, centerLat, 10000000)    
    
    window.geoViewer.camera.flyTo({
        destination: rectangle,
        duration: 1.8
    });

    window.geoViewer.clock.shouldAnimate = false;
}

function spinGlobeOnce(durationMs = 1500) {
    return new Promise((resolve) => {
        const camera = window.geoViewer.camera;        
        const startHeading = camera.heading;        
        const startTime = performance.now();

        function step(now) {
            const elapsed = now - startTime;
            const t = Math.min(elapsed / durationMs, 1);
            const heading = startHeading - (Cesium.Math.TWO_PI * t);

            const delta = -Cesium.Math.TWO_PI / 60;
            camera.rotate(Cesium.Cartesian3.UNIT_Z, delta);

            if (t < 1) {
                window.requestAnimationFrame(step);
                return;
            }

            resolve();
        }

        window.requestAnimationFrame(step);
    });
}

export async function zoomToAllSquares(rounds) {
    const roundFive = rounds.find(round => round.round_number === 5);

    if (!roundFive) {
        throw new Error('Round 1 not found for end-game animation.');
    }

    await spinGlobeOnce();

    zoomToSquare(roundFive.bounds);        
}

export function renderRoundMap(data) {
    clearMap();
    drawSquare(data);
    zoomToSquare(data.bounds);
}

export async function renderAllSquares(rounds, options = {}) {
    const { preview = false } = options;

    clearMap();

    for (const round of rounds) {
        for (const level of round.levels) {
            console.log('ROUND DEBUG', round);
            drawSquare(
                {
                    bounds: level.bounds
                },
                {
                    replaceExisting: false
                }
            );
        }

        if (preview) {
            for (const level of round.levels) {
                drawLabel({
                    text: `${round.round_number} L${level.expansion_level}`,
                    latitude: level.seed.lat,
                    longitude: level.seed.lon
                });
            }
        }

        if (!preview) {
            if (round.player_guess && round.player_guess.latitude != null && round.player_guess.longitude != null) {
                drawCities([{
                    city_name: round.player_guess.city_name,
                    label: `${round.player_guess.city_name} (${numberFmt(round.player_guess.population || 0)})`,
                    latitude: round.player_guess.latitude,
                    longitude: round.player_guess.longitude,
                    pixel_size: 8,
                    color: Cesium.Color.LIME,
                    outline_color: Cesium.Color.BLACK,
                    outline_width: 2,
                }]);
            }

            if (round.reveal_cities && round.reveal_cities.length) {
                drawCities(
                    round.reveal_cities.map(city => ({
                        ...city,
                        label: `${city.city_name} (${numberFmt(city.population)})`,
                        pixel_size: 6,
                        color: Cesium.Color.CYAN,
                        outline_color: Cesium.Color.BLACK,
                        outline_width: 1,
                    }))
                );
            }
        }
    }

    await zoomToAllSquares(rounds);
}

export function renderEndGameRound(rounds, roundNumber) {
    const round = rounds.find(r => r.round_number === roundNumber);

    if (!round) {
        throw new Error(`Round ${roundNumber} not found in end-game data.`);
    }

    zoomToSquare(round.bounds);
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

export function updateExpandButton(square) {
    const btn = document.getElementById('expandBtn');

    const shouldShow = Boolean(square && square.has_next_expansion);

    btn.style.display = shouldShow ? 'inline-block' : 'none';
    btn.disabled = !shouldShow;
}

export function setCurrentBounds(bounds) {
    currentBounds = bounds;
}

function animateExpansion(from, to, duration = 900) {
    const start = performance.now();

    if (expansionEntity) {
        window.geoViewer.entities.remove(expansionEntity);
        expansionEntity = null;
    }

    expansionEntity = window.geoViewer.entities.add({
        rectangle: {
            coordinates: Cesium.Rectangle.fromDegrees(
                from.min_lon,
                from.min_lat,
                from.max_lon,
                from.max_lat
            ),
            material: Cesium.Color.YELLOW.withAlpha(0.35),
            outline: true,
            outlineColor: Cesium.Color.YELLOW,
            outlineWidth: 2,
        }
    });

    function step(now) {
        const t = Math.min((now - start) / duration, 1);

        const minLat = from.min_lat + (to.min_lat - from.min_lat) * t;
        const maxLat = from.max_lat + (to.max_lat - from.max_lat) * t;
        const minLon = from.min_lon + (to.min_lon - from.min_lon) * t;
        const maxLon = from.max_lon + (to.max_lon - from.max_lon) * t;

        expansionEntity.rectangle.coordinates =
            Cesium.Rectangle.fromDegrees(minLon, minLat, maxLon, maxLat);

        if (t < 1) {
            requestAnimationFrame(step);
            return;
        }

        if (baseSquareEntity) {
            window.geoViewer.entities.remove(baseSquareEntity);
        }

        baseSquareEntity = window.geoViewer.entities.add({
            rectangle: {
                coordinates: Cesium.Rectangle.fromDegrees(
                    to.min_lon,
                    to.min_lat,
                    to.max_lon,
                    to.max_lat
                ),
                material: Cesium.Color.YELLOW.withAlpha(0.2),
                outline: true,
                outlineColor: Cesium.Color.YELLOW,
                outlineWidth: 2,
            }
        });

        setCurrentBounds(to);

        window.geoViewer.entities.remove(expansionEntity);
        expansionEntity = null;
    }

    requestAnimationFrame(step);
}

export async function handleExpand() {
    const btn = document.getElementById('expandBtn');
    if (btn.disabled) return;

    btn.disabled = true;
    btn.classList.add('pressed');

    try {
        const roundNumber = gameState.currentRound;

        const { response, data } = await expandSquareRequest(roundNumber);

        if (!response.ok) {
            throw new Error(data?.error || 'Expand request failed');
        }

        if (!data || !data.square_id || !data.bounds) {
            throw new Error('Invalid expand response payload');
        }

        const previousBounds = currentBounds;

        animateExpansion(previousBounds, data.bounds);

        currentBounds = data.bounds;

        const updatedSquareState = {
            has_next_expansion: Boolean(data.has_next_expansion)
        };

        updateExpandButton(updatedSquareState);

        document.dispatchEvent(
            new CustomEvent('squareExpanded', {
                detail: { has_next_expansion: data.has_next_expansion }
            })
        );
    } finally {
        btn.disabled = false;
        btn.classList.remove('pressed');
    }
}