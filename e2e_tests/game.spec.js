const { test, expect } = require('@playwright/test');
const fixture = require('./artifacts/game_fixture.json');

const SIDE_MISSIONS_BY_ROUND = Object.fromEntries(
  fixture.side_missions.map((mission) => [mission.round_number, mission]),
);

const INFINITY_MULTI_CITY_CASE = {
  guess: 'Santa Cruz',
  candidates: [
    { city_id: 24027, city: 'Angat', country_code: 'PH' },
    { city_id: 23668, city: 'Pulong Santa Cruz', country_code: 'PH' },
    { city_id: 23613, city: 'Santa Cruz', country_code: 'PH' },
    { city_id: 23614, city: 'Santa Cruz', country_code: 'PH' },
    { city_id: 23615, city: 'Santa Cruz', country_code: 'PH' },
  ],
};

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
    guess: SIDE_MISSIONS_BY_ROUND[2].daily_answer.city_name,
    selectedCityId: SIDE_MISSIONS_BY_ROUND[2].daily_answer.city_id,
    expectedCity: SIDE_MISSIONS_BY_ROUND[2].daily_answer.city_name,
  },
  3: {
    guess: SIDE_MISSIONS_BY_ROUND[3].daily_answer.city_name,
    selectedCityId: SIDE_MISSIONS_BY_ROUND[3].daily_answer.city_id,
    expectedCity: SIDE_MISSIONS_BY_ROUND[3].daily_answer.city_name,
  },
  5: {
    guess: SIDE_MISSIONS_BY_ROUND[5].daily_answer.city_name,
    selectedCityId: SIDE_MISSIONS_BY_ROUND[5].daily_answer.city_id,
    expectedCity: SIDE_MISSIONS_BY_ROUND[5].daily_answer.city_name,
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
  if (firstBody.requires_confirmation) {
    progress(projectName, `round ${roundNumber}: checking disambiguation`);
    if (testCase.candidates) {
      expect(firstBody.candidates.map(({ city_id, city, country_code }) => ({
        city_id,
        city,
        country_code,
      }))).toEqual(testCase.candidates);
    }
    expect(firstBody.candidates.every((candidate) => candidate.country_name)).toBe(true);

    const modal = page.locator('#guessConflictModal');
    await expect(modal).toBeVisible();
    const candidateButtons = modal.locator('.modal-btn').filter({ hasNotText: 'None of these' });
    await expect(candidateButtons).toHaveCount(firstBody.candidates.length);
    const selectedIndex = firstBody.candidates.findIndex(
      (candidate) => candidate.city_id === testCase.selectedCityId,
    );
    expect(selectedIndex).toBeGreaterThanOrEqual(0);
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

async function startSideMissions(page, projectName) {
  progress(projectName, 'starting Side Missions');
  await page.locator('#statsCloseBtn').click();
  if (projectName === 'webkit-mobile') {
    await page.locator('#mobileMenuBtn').click();
    await expect(page.locator('#sidebar')).toHaveClass(/mobile-open/);
  }
  const startResponsePromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/side-missions/start')
    && response.request().method() === 'POST'
  ));
  const stateResponsePromise = page.waitForResponse((response) => (
    response.url().includes('/api/infinity-state')
    && response.request().method() === 'GET'
  ));
  await page.locator('#sideMissionsInviteBtn').click();
  const startResponse = await startResponsePromise;
  expect(startResponse.ok()).toBe(true);
  const startData = await startResponse.json();
  expect(startData.side_missions.missions.map(({ round_number, mission_id }) => ({
    round_number,
    mission_id,
  }))).toEqual(fixture.side_missions.map(({ round_number, mission_id }) => ({
    round_number,
    mission_id,
  })));

  const stateResponse = await stateResponsePromise;
  expect(stateResponse.ok()).toBe(true);
  const state = await stateResponse.json();
  expect(state.current_round).toBe(2);
  await expect(page.locator('#sideMissionPanel')).toBeVisible();
  progress(projectName, 'Side Missions ready on square 2');
  return { state, missions: startData.side_missions.missions };
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

async function submitInfinityCity(
  page,
  roundNumber,
  infinityPoolSessionId,
  city,
  projectName,
) {
  progress(projectName, `Side Mission square ${roundNumber}: submitting ${city.city_name}`);
  const firstResult = await submitInfinityGuess(
    page,
    roundNumber,
    infinityPoolSessionId,
    city.city_name,
    'click',
  );
  if (!firstResult.requires_confirmation) return firstResult;

  const candidateIndex = firstResult.candidates.findIndex(
    (candidate) => candidate.city_id === city.city_id,
  );
  expect(candidateIndex).toBeGreaterThanOrEqual(0);
  const responsePromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/infinity-guess')
    && response.request().method() === 'POST'
  ));
  const modal = page.locator('#guessConflictModal');
  await expect(modal).toBeVisible();
  const candidateButtons = modal.locator('.modal-btn').filter({ hasNotText: 'None of these' });
  await candidateButtons.nth(candidateIndex).click();
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  expect(response.request().postDataJSON().confirmed_city_id).toBe(city.city_id);
  return response.json();
}

async function submitInfinityCandidate(
  page,
  roundNumber,
  infinityPoolSessionId,
  candidate,
  method = 'click',
) {
  const firstResult = await submitInfinityGuess(
    page,
    roundNumber,
    infinityPoolSessionId,
    INFINITY_MULTI_CITY_CASE.guess,
    method,
  );
  expect(firstResult.requires_confirmation).toBe(true);
  expect(firstResult.candidates.map(({ city_id, city, country_code }) => ({
    city_id,
    city,
    country_code,
  }))).toEqual(INFINITY_MULTI_CITY_CASE.candidates);

  const candidateIndex = firstResult.candidates.findIndex(
    (resultCandidate) => resultCandidate.city_id === candidate.city_id,
  );
  expect(candidateIndex).toBeGreaterThanOrEqual(0);
  const responsePromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/infinity-guess')
    && response.request().method() === 'POST'
  ));
  const modal = page.locator('#guessConflictModal');
  await expect(modal).toBeVisible();
  const candidateButtons = modal.locator('.modal-btn').filter({ hasNotText: 'None of these' });
  await candidateButtons.nth(candidateIndex).click();
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  expect(response.request().postDataJSON().confirmed_city_id).toBe(candidate.city_id);
  return response.json();
}

async function completeSideMission(
  page,
  assignment,
  mission,
  infinityPoolSessionId,
  projectName,
) {
  await expect(page.locator('#sideMissionPanel')).toBeVisible();
  await expect(page.locator('#sideMissionName')).toHaveText(mission.name);
  await expect(page.locator('#sideMissionPrompt')).toHaveText(mission.prompt);
  expect(mission.progress.current).toBe(0);

  let result;
  for (const [index, city] of assignment.targets.entries()) {
    result = await submitInfinityCity(
      page,
      assignment.round_number,
      infinityPoolSessionId,
      city,
      projectName,
    );
    const updatedMission = result.side_missions.missions.find(
      (candidate) => candidate.round_number === assignment.round_number,
    );
    expect(result.correct).toBe(true);
    expect(result.duplicate).toBe(false);
    expect(updatedMission.progress.current).toBe(index + 1);
    await expect(page.locator('#sideMissionProgress')).toContainText(
      `${index + 1} / ${assignment.targets.length}`,
    );
    await expect(page.locator('#sideMissionAcknowledgement')).toBeVisible();
  }

  const completedMission = result.side_missions.missions.find(
    (candidate) => candidate.round_number === assignment.round_number,
  );
  expect(completedMission.completed_at).not.toBeNull();
  await expect(page.locator('#sideMissionProgress')).toContainText('Complete!');
  progress(projectName, `Side Mission square ${assignment.round_number}: completed`);
  return result;
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
  await expect(page.locator('#shareScoreModal')).toBeVisible();
  await expect(page.locator('#shareFormatBtn')).toHaveAttribute('aria-label', 'Details visible');
  await expect(page.locator('#shareTextPreview')).toContainText('4/5 solved');
  await page.locator('#shareCopyBtn').click();
  await expect(page.locator('#shareScoreModal')).toBeHidden();
  const detailedText = await page.evaluate(() => window.__copiedText);
  expect(detailedText).toContain('🟨 R1  ');
  expect(detailedText).toContain('🟩 R5  ');
  expect(detailedText).toMatch(/· [\d,]+ · \d+(st|nd|rd|th) · \d+ pts/);
  expect(detailedText).not.toContain('pop.');
  expect(detailedText).toContain('?ref=share');

  await page.locator('#shareScoreBtn').click();
  await page.locator('#shareFormatBtn').click();
  await expect(page.locator('#shareFormatBtn')).toHaveAttribute('aria-label', 'Discord spoilers');
  const firstSpoiler = page.locator('.share-card-spoiler').first();
  await expect(firstSpoiler).toHaveAttribute('aria-label', 'Reveal spoiler');
  await expect(page.locator('#shareTextPreview')).not.toContainText('||');
  await firstSpoiler.click();
  await expect(firstSpoiler).toHaveClass(/revealed/);
  await expect(firstSpoiler).toHaveAttribute('aria-label', 'Hide spoiler');
  await page.locator('#shareCopyBtn').click();
  const discordText = await page.evaluate(() => window.__copiedText);
  expect(discordText).toContain('GeoSquare ');
  expect(discordText).toContain('R5  ||');
  expect(discordText).toMatch(/· \d+(st|nd|rd|th)\|\| · \d+ pts/);
  expect(discordText).toContain('?ref=share');

  await page.locator('#shareScoreBtn').click();
  await page.locator('#shareFormatBtn').click();
  await page.locator('#shareFormatBtn').click();
  await expect(page.locator('#shareFormatBtn')).toHaveAttribute('aria-label', 'Details hidden');
  await expect(page.locator('#shareTextPreview')).toContainText('Can you beat me?');
  await page.locator('#shareCopyBtn').click();
  const compactText = await page.evaluate(() => window.__copiedText);
  expect(compactText).toContain('?ref=share');
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

  const sideMissionStart = await startSideMissions(page, projectName);
  const infinityState = sideMissionStart.state;
  let latestResult = await completeSideMission(
    page,
    SIDE_MISSIONS_BY_ROUND[2],
    sideMissionStart.missions.find((mission) => mission.round_number === 2),
    infinityState.infinity_pool_session_id,
    projectName,
  );

  progress(projectName, 'Infinity Pool square 2: submitting Santa Cruz');
  const existingCityIds = new Set([
    SIDE_MISSIONS_BY_ROUND[2].daily_answer.city_id,
    ...SIDE_MISSIONS_BY_ROUND[2].targets.map((city) => city.city_id),
  ]);
  const acceptedCandidates = [];
  let infinityResult = latestResult;
  for (const candidate of INFINITY_MULTI_CITY_CASE.candidates) {
    const candidateResult = await submitInfinityCandidate(
      page,
      2,
      infinityState.infinity_pool_session_id,
      candidate,
      'enter',
    );
    expect(candidateResult.correct).toBe(true);
    if (existingCityIds.has(candidate.city_id)) {
      expect(candidateResult).toEqual({
        correct: true,
        duplicate: true,
        duplicates: [candidate.city],
        ok: true,
      });
    } else {
      expect(candidateResult.duplicate).toBe(false);
      expect(candidateResult.guesses.map(({ city_id, city, country_code }) => ({
        city_id,
        city,
        country_code,
      }))).toEqual([candidate]);
      expect(candidateResult.duplicates).toEqual([]);
      acceptedCandidates.push(candidate);
      existingCityIds.add(candidate.city_id);
      infinityResult = candidateResult;
    }
  }
  const roundTwoCityCount = existingCityIds.size;
  const chips = page.locator('#infinityChips .infinity-chip');
  await expect(chips).toHaveCount(roundTwoCityCount);
  const chipNames = await page.locator('#infinityChips .infinity-chip-city').allTextContents();
  expect(chipNames.slice(0, acceptedCandidates.length)).toEqual(
    acceptedCandidates.map((candidate) => candidate.city).reverse(),
  );
  await expect(page.locator('#infinityRoundScore')).toHaveText(
    infinityResult.round_score.toLocaleString('en-US'),
  );
  await expect(page.locator('#infinityTotalScore')).toHaveText(
    infinityResult.total_score.toLocaleString('en-US'),
  );
  progress(projectName, 'Infinity Pool multi-city result verified');

  progress(projectName, 'Infinity Pool square 2: checking duplicate submission');
  for (const candidate of INFINITY_MULTI_CITY_CASE.candidates) {
    const duplicateResult = await submitInfinityCandidate(
      page,
      2,
      infinityState.infinity_pool_session_id,
      candidate,
    );
    expect(duplicateResult).toEqual({
      correct: true,
      duplicate: true,
      duplicates: [candidate.city],
      ok: true,
    });
  }
  await expect(chips).toHaveCount(roundTwoCityCount);
  await expect(page.locator('#infinityRoundScore')).toHaveText(
    infinityResult.round_score.toLocaleString('en-US'),
  );
  await expect(page.locator('#infinityTotalScore')).toHaveText(
    infinityResult.total_score.toLocaleString('en-US'),
  );
  progress(projectName, 'Infinity Pool duplicate left scores unchanged');

  await selectInfinityRound(
    page,
    3,
    infinityState.infinity_pool_session_id,
    projectName,
  );
  latestResult = await completeSideMission(
    page,
    SIDE_MISSIONS_BY_ROUND[3],
    latestResult.side_missions.missions.find((mission) => mission.round_number === 3),
    infinityState.infinity_pool_session_id,
    projectName,
  );

  await selectInfinityRound(
    page,
    4,
    infinityState.infinity_pool_session_id,
    projectName,
  );
  await expect(page.locator('#sideMissionPanel')).toBeHidden();

  await selectInfinityRound(
    page,
    5,
    infinityState.infinity_pool_session_id,
    projectName,
  );
  latestResult = await completeSideMission(
    page,
    SIDE_MISSIONS_BY_ROUND[5],
    latestResult.side_missions.missions.find((mission) => mission.round_number === 5),
    infinityState.infinity_pool_session_id,
    projectName,
  );

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
  expect(restoredState.current_round).toBe(5);
  expect(restoredState.total_score).toBe(latestResult.total_score);
  expect(restoredState.side_missions.missions.every(
    (mission) => mission.completed_at !== null,
  )).toBe(true);
  await expect(page.locator('#sideMissionPanel')).toBeVisible();
  await expect(page.locator('#sideMissionProgress')).toContainText(
    'Complete!',
  );
  expect(pageErrors).toEqual([]);
  progress(projectName, 'test completed');
});