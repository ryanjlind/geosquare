const { test, expect } = require('@playwright/test');

const ROUND_CASES = {
  1: {
    guess: 'Tehran',
    candidates: [
      { city_id: 17727, city: 'Tehran', country_code: 'IR' },
      { city_id: 17972, city: 'Tīrān', country_code: 'IR' },
    ],
    selectedCityId: 17727,
  },
  2: {
    guess: 'Santa Cruz',
    candidates: [
      { city_id: 24027, city: 'Angat', country_code: 'PH' },
      { city_id: 23668, city: 'Pulong Santa Cruz', country_code: 'PH' },
      { city_id: 23613, city: 'Santa Cruz', country_code: 'PH' },
      { city_id: 23614, city: 'Santa Cruz', country_code: 'PH' },
      { city_id: 23615, city: 'Santa Cruz', country_code: 'PH' },
    ],
    selectedCityId: 23613,
  },
  3: {
    guess: 'Phu Quoc',
    candidates: [
      { city_id: 32910, city: 'Phu Quoc', country_code: 'VN' },
      { city_id: 32956, city: 'Phú Quốc', country_code: 'VN' },
    ],
    selectedCityId: 32910,
  },
  5: {
    incorrectGuess: 'Moscow',
    guess: 'Arkhangelsk',
    expectedCity: 'Arkhangel’sk',
  },
};

async function openControls(page) {
  await expect(page.locator('#guessInput')).toBeVisible({ timeout: 10_000 });
}

function progress(projectName, message) {
  console.log(`[${new Date().toISOString()}] [${projectName}] ${message}`);
}

async function submitGuess(page, roundNumber, guess, method) {
  await page.locator('#guessInput').fill(guess);
  const responsePromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/guess')
    && response.request().method() === 'POST'
  ));

  if (method === 'enter') {
    await page.locator('#guessInput').press('Enter');
  } else {
    await page.locator('#guessBtn').click();
  }

  const response = await responsePromise;
  expect(response.request().postDataJSON()).toEqual({
    guess,
    round_number: roundNumber,
    confirmed_city_id: null,
  });
  return response.json();
}

async function submitCity(page, roundNumber, method, projectName) {
  const testCase = ROUND_CASES[roundNumber];

  if (testCase.incorrectGuess) {
    progress(projectName, `round ${roundNumber}: submitting incorrect guess`);
    const incorrectResult = await submitGuess(
      page,
      roundNumber,
      testCase.incorrectGuess,
      method,
    );
    expect(incorrectResult.correct).toBe(false);
    progress(projectName, `round ${roundNumber}: incorrect guess rejected`);
  }

  progress(projectName, `round ${roundNumber}: submitting ${testCase.guess}`);
  const firstBody = await submitGuess(page, roundNumber, testCase.guess, method);

  let result = firstBody;
  if (testCase.candidates) {
    progress(projectName, `round ${roundNumber}: checking disambiguation`);
    expect(firstBody.requires_confirmation).toBe(true);
    expect(firstBody.candidates.map(({ city_id, city, country_code }) => ({
      city_id,
      city,
      country_code,
    }))).toEqual(testCase.candidates);
    expect(firstBody.candidates.every((candidate) => candidate.country_name)).toBe(true);

    const modal = page.locator('#guessConflictModal');
    await expect(modal).toBeVisible();
    const candidateButtons = modal.locator('.modal-btn').filter({ hasNotText: 'None of these' });
    await expect(candidateButtons).toHaveCount(testCase.candidates.length);
    const selectedIndex = testCase.candidates.findIndex(
      (candidate) => candidate.city_id === testCase.selectedCityId,
    );
    const confirmationResponsePromise = page.waitForResponse((response) => (
      response.url().endsWith('/api/guess')
      && response.request().method() === 'POST'
    ));
    await candidateButtons.nth(selectedIndex).click();
    const confirmationResponse = await confirmationResponsePromise;
    const confirmationRequestBody = confirmationResponse.request().postDataJSON();
    result = await confirmationResponse.json();
    expect(confirmationRequestBody.confirmed_city_id).toBe(testCase.selectedCityId);
    await expect(modal).toBeHidden();
    progress(projectName, `round ${roundNumber}: disambiguation confirmed`);
  } else {
    expect(firstBody.requires_confirmation).toBeFalsy();
  }

  expect(result.correct).toBe(true);
  if (testCase.expectedCity) {
    expect(result.city).toBe(testCase.expectedCity);
  }
  await expect(page.locator('#guessFeedback')).toContainText(result.city.toUpperCase());
  progress(projectName, `round ${roundNumber}: guess completed`);
  return result;
}

async function advanceToNextRound(page, nextRoundNumber, projectName) {
  progress(projectName, `round ${nextRoundNumber}: loading`);
  const responsePromise = page.waitForResponse((response) => (
    response.url().includes(`/api/daily-square?round=${nextRoundNumber}`)
  ));
  await page.locator('#nextBtn').click();
  await responsePromise;
  await expect(page.locator('#meta')).toContainText(`${nextRoundNumber} / 5`);
  progress(projectName, `round ${nextRoundNumber}: ready`);
}

async function enterInfinity(page, projectName) {
  progress(projectName, 'entering Infinity Pool');
  const responsePromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/infinity-state')
    && response.request().method() === 'GET'
  ));
  const statsOverlay = page.locator('#statsOverlay');
  let entryButton = page.locator('#statsInfinityInviteBtn');
  if (!await statsOverlay.isVisible()) {
    if (projectName === 'webkit-mobile') {
      const mobileMenuButton = page.locator('#mobileMenuBtn');
      await expect(mobileMenuButton).toBeVisible();
      await mobileMenuButton.click();
      await expect(page.locator('#sidebar')).toHaveClass(/mobile-open/);
    }
    entryButton = page.locator('#infinityModeBtn');
  }
  await entryButton.click();
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  const state = await response.json();
  expect(state.unlocked).toBe(true);
  await expect(page.locator('#infinityPanel')).toBeVisible();
  await expect(page.locator('#guessInput')).toBeEnabled();
  await expect(page.locator('#guessBtn')).toBeEnabled();
  await expect(page.locator('#meta')).toContainText(`Square ${state.current_round} of 5`);
  progress(projectName, `Infinity Pool square ${state.current_round} ready`);
  return state;
}

async function selectInfinityRound(page, roundNumber, infinityPoolSessionId, projectName) {
  progress(projectName, `Infinity Pool square ${roundNumber}: loading`);
  const responsePromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/infinity-round')
    && response.request().method() === 'POST'
  ));
  await page.locator('#nextBtn').click();
  const response = await responsePromise;
  expect(response.request().postDataJSON()).toEqual({
    round_number: roundNumber,
    infinity_pool_session_id: infinityPoolSessionId,
  });
  expect(response.ok()).toBe(true);
  await expect(page.locator('#meta')).toContainText(`Square ${roundNumber} of 5`);
  progress(projectName, `Infinity Pool square ${roundNumber}: ready`);
}

async function submitInfinityGuess(page, roundNumber, infinityPoolSessionId, guess, method) {
  await page.locator('#guessInput').fill(guess);
  const responsePromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/infinity-guess')
    && response.request().method() === 'POST'
  ));

  if (method === 'enter') {
    await page.locator('#guessInput').press('Enter');
  } else {
    await page.locator('#guessBtn').click();
  }

  const response = await responsePromise;
  expect(response.request().postDataJSON()).toEqual({
    guess,
    round_number: roundNumber,
    infinity_pool_session_id: infinityPoolSessionId,
  });
  expect(response.ok()).toBe(true);
  return response.json();
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

test('completes and resumes a five-round game', async ({ page }, testInfo) => {
  const projectName = testInfo.project.name;
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));

  progress(projectName, 'opening game');
  await page.goto('/');
  await openControls(page);
  await expect(page.locator('#meta')).toContainText('1 / 5');
  progress(projectName, 'round 1 ready');

  progress(projectName, 'round 1: expanding square');
  const expansionResponsePromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/expand')
    && response.request().method() === 'POST'
  ));
  await page.locator('#expandBtn').click();
  const expansionBody = await (await expansionResponsePromise).json();
  expect(expansionBody.expansion_level).toBe(1);
  progress(projectName, 'round 1: expansion completed');

  const roundOne = await submitCity(page, 1, 'click', projectName);
  expect(roundOne.expansion_level).toBe(1);
  await advanceToNextRound(page, 2, projectName);

  await submitCity(page, 2, 'enter', projectName);
  progress(projectName, 'reloading after round 2');
  await page.reload();
  await openControls(page);
  await expect(page.locator('#meta')).toContainText('3 / 5');
  progress(projectName, 'round 3 resumed');

  await submitCity(page, 3, 'click', projectName);
  await advanceToNextRound(page, 4, projectName);

  progress(projectName, 'round 4: passing');
  const passResponsePromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/pass')
    && response.request().method() === 'POST'
  ));
  await page.locator('#passBtn').click();
  const passBody = await (await passResponsePromise).json();
  expect(passBody.passed).toBe(true);
  await expect(page.locator('#guessFeedback')).toContainText('No guess submitted');
  progress(projectName, 'round 4: pass completed');
  await advanceToNextRound(page, 5, projectName);

  await submitCity(page, 5, 'enter', projectName);
  progress(projectName, 'checking share text');
  await expect(page.locator('#shareScoreBtn')).toBeVisible();
  await page.locator('#shareScoreBtn').click();
  const copiedText = await page.evaluate(() => window.__copiedText);
  expect(copiedText).toContain('Game Complete | 4/5 solved');
  expect(copiedText).toContain('R1:');
  expect(copiedText).toContain('R5:');
  expect(copiedText).toContain('pop.');
  progress(projectName, 'share text verified');

  progress(projectName, 'opening final summary');
  await page.locator('#nextBtn').click();
  await expect(page.locator('#statsOverlay')).toBeVisible();
  progress(projectName, 'final summary visible');

  progress(projectName, 'checking final game state');
  const state = await page.evaluate(async () => (await fetch('/api/game-state')).json());
  expect(state.state).toBe('completed');
  expect(state.completed_rounds).toHaveLength(5);
  expect(state.completed_rounds.filter((round) => round.round_status === 'Passed')).toHaveLength(1);

  const infinityState = await enterInfinity(page, projectName);
  await selectInfinityRound(
    page,
    2,
    infinityState.infinity_pool_session_id,
    projectName,
  );

  progress(projectName, 'Infinity Pool square 2: submitting Santa Cruz');
  const infinityResult = await submitInfinityGuess(
    page,
    2,
    infinityState.infinity_pool_session_id,
    'Santa Cruz',
    'click',
  );
  expect(infinityResult.correct).toBe(true);
  expect(infinityResult.duplicate).toBe(false);
  expect(infinityResult.guesses.map(({ city_id, city, country_code }) => ({
    city_id,
    city,
    country_code,
  }))).toEqual(ROUND_CASES[2].candidates);
  expect(infinityResult.duplicates).toEqual([]);
  const chips = page.locator('#infinityChips .infinity-chip');
  await expect(chips).toHaveCount(ROUND_CASES[2].candidates.length);
  await expect(page.locator('#infinityChips .infinity-chip-city')).toHaveText(
    ROUND_CASES[2].candidates.map((candidate) => candidate.city).reverse(),
  );
  await expect(page.locator('#infinityRoundScore')).toHaveText(
    infinityResult.round_score.toLocaleString('en-US'),
  );
  await expect(page.locator('#infinityTotalScore')).toHaveText(
    infinityResult.total_score.toLocaleString('en-US'),
  );
  progress(projectName, 'Infinity Pool multi-city result verified');

  progress(projectName, 'Infinity Pool square 2: checking duplicate submission');
  const duplicateResult = await submitInfinityGuess(
    page,
    2,
    infinityState.infinity_pool_session_id,
    'Santa Cruz',
    'enter',
  );
  expect(duplicateResult).toEqual({
    correct: true,
    duplicate: true,
    duplicates: ROUND_CASES[2].candidates.map((candidate) => candidate.city),
    ok: true,
  });
  await expect(chips).toHaveCount(ROUND_CASES[2].candidates.length);
  await expect(page.locator('#infinityRoundScore')).toHaveText(
    infinityResult.round_score.toLocaleString('en-US'),
  );
  await expect(page.locator('#infinityTotalScore')).toHaveText(
    infinityResult.total_score.toLocaleString('en-US'),
  );
  progress(projectName, 'Infinity Pool duplicate left scores unchanged');

  progress(projectName, 'switching Daily to Infinity Pool and checking persistence');
  const mobileMenuButton = page.locator('#mobileMenuBtn');
  if (await mobileMenuButton.isVisible()) {
    await mobileMenuButton.click();
    await expect(page.locator('#sidebar')).toHaveClass(/mobile-open/);
  }
  const dailySquaresResponsePromise = page.waitForResponse(
    (response) => response.url().endsWith('/api/all-daily-squares'),
    { timeout: 90_000 },
  );
  await Promise.all([
    page.waitForLoadState('load'),
    dailySquaresResponsePromise,
    page.locator('#dailyModeBtn').click(),
  ]);
  const restoredState = await enterInfinity(page, projectName);
  expect(restoredState.current_round).toBe(2);
  expect(restoredState.total_score).toBe(infinityResult.total_score);
  expect(restoredState.guesses).toHaveLength(ROUND_CASES[2].candidates.length);
  await expect(page.locator('#infinityChips .infinity-chip')).toHaveCount(
    ROUND_CASES[2].candidates.length,
  );
  expect(pageErrors).toEqual([]);
  progress(projectName, 'test completed');
});