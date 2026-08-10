const { test, expect } = require('@playwright/test');
const fixture = require('./artifacts/weekly_fixture.json');


function progress(projectName, message) {
  console.log(`[${new Date().toISOString()}] [weekly-random] [${projectName}] ${message}`);
}

async function submitGuess(page, roundFixture, projectName) {
  const city = roundFixture.correct_city;
  progress(
    projectName,
    `round ${roundFixture.round_number}: submitting correct guess `
    + `${city.city_name} (city ${city.city_id}, ${city.country_code})`,
  );
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
    progress(
      projectName,
      `round ${roundFixture.round_number}: guess response received without disambiguation`,
    );
    return firstBody;
  }

  progress(
    projectName,
    `round ${roundFixture.round_number}: disambiguation required with `
    + `${firstBody.candidates.length} candidates`,
  );
  const candidateIndex = firstBody.candidates.findIndex(
    (candidate) => candidate.city_id === city.city_id,
  );
  expect(candidateIndex).toBeGreaterThanOrEqual(0);
  progress(
    projectName,
    `round ${roundFixture.round_number}: generated city found at candidate index ${candidateIndex}`,
  );

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
  progress(
    projectName,
    `round ${roundFixture.round_number}: confirmed city ${city.city_id}`,
  );
  return confirmationResponse.json();
}

async function submitIncorrectNearbyGuess(page, roundFixture, projectName) {
  const city = roundFixture.incorrect_city;
  if (city === null) {
    progress(
      projectName,
      `round ${roundFixture.round_number}: no next-ring city available; skipping incorrect guess`,
    );
    return;
  }

  const bounds = roundFixture.base_bounds;
  progress(
    projectName,
    `round ${roundFixture.round_number}: verifying ${city.city_name} `
    + `(${city.latitude}, ${city.longitude}) is outside base bounds `
    + `[${bounds.min_lat}, ${bounds.min_lon}] to [${bounds.max_lat}, ${bounds.max_lon}]`,
  );
  expect(
    city.latitude < bounds.min_lat
    || city.latitude > bounds.max_lat
    || city.longitude < bounds.min_lon
    || city.longitude > bounds.max_lon,
  ).toBe(true);
  progress(
    projectName,
    `round ${roundFixture.round_number}: submitting incorrect next-ring guess `
    + `${city.city_name} (city ${city.city_id}, ${city.country_code})`,
  );

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
  progress(
    projectName,
    `round ${roundFixture.round_number}: API and feedback marked ${city.city_name} incorrect`,
  );

  await page.waitForFunction((cityName) => window.geoViewer.entities.values.some((entity) => {
    if (!entity.label || !entity.point) {
      return false;
    }
    const label = entity.label.text.getValue();
    const color = entity.point.color.getValue(Cesium.JulianDate.now());
    return label === cityName && color.red > 0.9 && color.green < 0.1;
  }), city.city_name, { timeout: 1_500 });
  progress(
    projectName,
    `round ${roundFixture.round_number}: red map marker verified for ${city.city_name}`,
  );
}

async function expandSquare(page, roundFixture, projectName) {
  await submitIncorrectNearbyGuess(page, roundFixture, projectName);
  progress(projectName, `round ${roundFixture.round_number}: clicking Expand`);
  const responsePromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/expand')
    && response.request().method() === 'POST'
  ));
  await page.locator('#expandBtn').click();
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  const body = await response.json();
  expect(body.expansion_level).toBe(1);
  progress(
    projectName,
    `round ${roundFixture.round_number}: expansion level 1 loaded and -20% penalty applied`,
  );
}

async function passRound(page, roundNumber, projectName) {
  progress(projectName, `round ${roundNumber}: clicking Pass`);
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
  progress(projectName, `round ${roundNumber}: pass response and feedback verified`);
}

async function advanceToRound(page, roundNumber, projectName) {
  progress(projectName, `round ${roundNumber}: clicking Next and waiting for square data`);
  const responsePromise = page.waitForResponse((response) => (
    response.url().includes(`/api/daily-square?round=${roundNumber}`)
  ));
  await page.locator('#nextBtn').click();
  await responsePromise;
  await expect(page.locator('#meta')).toContainText(`${roundNumber} / 5`);
  progress(projectName, `round ${roundNumber}: square ready`);
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

test('completes five randomly selected squares', async ({ page }, testInfo) => {
  const projectName = testInfo.project.name;
  progress(projectName, `loaded fixture for game ${fixture.game_id}`);
  expect(fixture.rounds).toHaveLength(5);
  progress(
    projectName,
    `fixture contains pool squares: ${fixture.rounds.map((round) => round.pool_square_id).join(', ')}`,
  );
  progress(projectName, 'opening game');
  await page.goto('/');
  await expect(page.locator('#guessInput')).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('#meta')).toContainText('1 / 5');
  progress(projectName, 'round 1 controls ready');
  let solvedCount = 0;

  for (const roundFixture of fixture.rounds) {
    progress(
      projectName,
      `round ${roundFixture.round_number}: starting ${roundFixture.action} action `
      + `for pool square ${roundFixture.pool_square_id}`,
    );
    if (roundFixture.action === 'pass') {
      await passRound(page, roundFixture.round_number, projectName);
    } else {
      if (roundFixture.action === 'expand') {
        await expandSquare(page, roundFixture, projectName);
      }
      const result = await submitGuess(page, roundFixture, projectName);
      expect(result.correct).toBe(true);
      expect(result.city).toBe(roundFixture.correct_city.city_name);
      expect(result.score).toBeGreaterThan(0);
      await expect(page.locator('#guessFeedback'))
        .toContainText(roundFixture.correct_city.city_name.toUpperCase());
      solvedCount += 1;
      progress(
        projectName,
        `round ${roundFixture.round_number}: correct result verified for ${result.city}; `
        + `score ${result.score}; solved count ${solvedCount}/5`,
      );
    }

    if (roundFixture.round_number === 2) {
      progress(projectName, 'round 2 complete: reloading page to verify resume behavior');
      await page.reload();
      await expect(page.locator('#guessInput')).toBeVisible({ timeout: 10_000 });
      await expect(page.locator('#meta')).toContainText('3 / 5');
      progress(projectName, 'resume verified at round 3');
    } else if (roundFixture.round_number < 5) {
      await advanceToRound(page, roundFixture.round_number + 1, projectName);
    }
  }

  progress(projectName, `all rounds complete with ${solvedCount}/5 solved; testing share text`);
  await expect(page.locator('#shareScoreBtn')).toBeVisible();
  await page.locator('#shareScoreBtn').click();
  const copiedText = await page.evaluate(() => window.__copiedText);
  const expectedHeadline = solvedCount === 5 ? 'Perfect Game' : 'Game Complete';
  expect(copiedText).toContain(`${expectedHeadline} | ${solvedCount}/5 solved`);
  expect(copiedText).toContain('R1:');
  expect(copiedText).toContain('R5:');
  progress(
    projectName,
    `share text verified with headline "${expectedHeadline}" and ${solvedCount}/5 solved`,
  );

  progress(projectName, 'fetching final game state');
  const state = await page.evaluate(async () => (await fetch('/api/game-state')).json());
  expect(state.state).toBe('completed');
  expect(state.completed_rounds).toHaveLength(5);
  expect(state.completed_rounds.filter((round) => round.round_status === 'Completed'))
    .toHaveLength(solvedCount);
  expect(state.completed_rounds.filter((round) => round.round_status === 'Passed'))
    .toHaveLength(5 - solvedCount);
  progress(
    projectName,
    `final state verified: ${solvedCount} completed, ${5 - solvedCount} passed`,
  );
  progress(projectName, 'weekly randomized game completed successfully');
});