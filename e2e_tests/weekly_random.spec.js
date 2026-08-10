const { test, expect } = require('@playwright/test');
const fixture = require('./artifacts/weekly_fixture.json');


function progress(message) {
  console.log(`[${new Date().toISOString()}] [weekly-random] ${message}`);
}

async function submitGuess(page, roundFixture) {
  const city = roundFixture.correct_city;
  const guessInput = page.locator('#guessInput');
  await guessInput.fill(city.city_name);
  const responsePromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/guess')
    && response.request().method() === 'POST'
  ));
  await page.locator('#guessBtn').click();
  const firstResponse = await responsePromise;
  expect(firstResponse.ok()).toBe(true);
  const firstBody = await firstResponse.json();

  if (!firstBody.requires_confirmation) {
    return firstBody;
  }

  const candidateIndex = firstBody.candidates.findIndex(
    (candidate) => candidate.city_id === city.city_id,
  );
  expect(candidateIndex).toBeGreaterThanOrEqual(0);

  const modal = page.locator('#guessConflictModal');
  await expect(modal).toBeVisible();
  const candidateButtons = modal.locator('.modal-btn').filter({ hasNotText: 'None of these' });
  const confirmationPromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/guess')
    && response.request().method() === 'POST'
  ));
  await candidateButtons.nth(candidateIndex).click();
  const confirmationResponse = await confirmationPromise;
  expect(confirmationResponse.ok()).toBe(true);
  expect(confirmationResponse.request().postDataJSON().confirmed_city_id)
    .toBe(city.city_id);
  return confirmationResponse.json();
}

async function submitIncorrectNearbyGuess(page, roundFixture) {
  const city = roundFixture.incorrect_city;
  if (city === null) {
    progress(`round ${roundFixture.round_number}: no next-ring city available`);
    return;
  }

  const bounds = roundFixture.base_bounds;
  expect(
    city.latitude < bounds.min_lat
    || city.latitude > bounds.max_lat
    || city.longitude < bounds.min_lon
    || city.longitude > bounds.max_lon,
  ).toBe(true);

  await page.locator('#guessInput').fill(city.city_name);
  const responsePromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/guess')
    && response.request().method() === 'POST'
  ));
  await page.locator('#guessBtn').click();
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  const body = await response.json();
  expect(body.correct).toBe(false);
  expect(body.matched_city.city_name).toBe(city.city_name);
  await expect(page.locator('#guessFeedback')).toContainText('Not in the square');

  await page.waitForFunction((cityName) => window.geoViewer.entities.values.some((entity) => {
    if (!entity.label || !entity.point) {
      return false;
    }
    const label = entity.label.text.getValue();
    const color = entity.point.color.getValue(Cesium.JulianDate.now());
    return label === cityName && color.red > 0.9 && color.green < 0.1;
  }), city.city_name, { timeout: 1_500 });
}

async function expandSquare(page, roundFixture) {
  await submitIncorrectNearbyGuess(page, roundFixture);
  const responsePromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/expand')
    && response.request().method() === 'POST'
  ));
  await page.locator('#expandBtn').click();
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  const body = await response.json();
  expect(body.expansion_level).toBe(1);
}

async function passRound(page, roundNumber) {
  const responsePromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/pass')
    && response.request().method() === 'POST'
  ));
  await page.locator('#passBtn').click();
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  const body = await response.json();
  expect(body.passed).toBe(true);
  expect(body.round_number).toBe(roundNumber);
  await expect(page.locator('#guessFeedback')).toContainText('No guess submitted');
}

async function advanceToRound(page, roundNumber) {
  const responsePromise = page.waitForResponse((response) => (
    response.url().includes(`/api/daily-square?round=${roundNumber}`)
  ));
  await page.locator('#nextBtn').click();
  await responsePromise;
  await expect(page.locator('#meta')).toContainText(`${roundNumber} / 5`);
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.__E2E_REQUEST_RENDER_MODE = true;
    window.__copiedText = '';
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: async (text) => {
          window.__copiedText = text;
        },
      },
    });
  });
});

test('completes five randomly selected squares', async ({ page }) => {
  expect(fixture.rounds).toHaveLength(5);
  await page.goto('/');
  await expect(page.locator('#guessInput')).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('#meta')).toContainText('1 / 5');
  let solvedCount = 0;

  for (const roundFixture of fixture.rounds) {
    progress(`round ${roundFixture.round_number}: ${roundFixture.action}`);
    if (roundFixture.action === 'pass') {
      await passRound(page, roundFixture.round_number);
    } else {
      if (roundFixture.action === 'expand') {
        await expandSquare(page, roundFixture);
      }
      const result = await submitGuess(page, roundFixture);
      expect(result.correct).toBe(true);
      expect(result.city).toBe(roundFixture.correct_city.city_name);
      expect(result.score).toBeGreaterThan(0);
      await expect(page.locator('#guessFeedback'))
        .toContainText(roundFixture.correct_city.city_name.toUpperCase());
      solvedCount += 1;
    }

    if (roundFixture.round_number === 2) {
      progress('reloading to verify resume behavior');
      await page.reload();
      await expect(page.locator('#guessInput')).toBeVisible({ timeout: 10_000 });
      await expect(page.locator('#meta')).toContainText('3 / 5');
    } else if (roundFixture.round_number < 5) {
      await advanceToRound(page, roundFixture.round_number + 1);
    }
  }

  await expect(page.locator('#shareScoreBtn')).toBeVisible();
  await page.locator('#shareScoreBtn').click();
  const copiedText = await page.evaluate(() => window.__copiedText);
  expect(copiedText).toContain(`Game Complete | ${solvedCount}/5 solved`);
  expect(copiedText).toContain('R1:');
  expect(copiedText).toContain('R5:');

  const state = await page.evaluate(async () => (await fetch('/api/game-state')).json());
  expect(state.state).toBe('completed');
  expect(state.completed_rounds).toHaveLength(5);
  expect(state.completed_rounds.filter((round) => round.round_status === 'Completed'))
    .toHaveLength(solvedCount);
  expect(state.completed_rounds.filter((round) => round.round_status === 'Passed'))
    .toHaveLength(5 - solvedCount);
  progress('weekly randomized game completed');
});