const { test, expect } = require('@playwright/test');

async function openControls(page) {
  const menuButton = page.locator('#mobileMenuBtn');
  if (await menuButton.isVisible()) {
    await menuButton.click();
  }
  await expect(page.locator('#guessInput')).toBeVisible();
}

async function fetchRound(page, roundNumber) {
  return page.evaluate(async (round) => {
    const response = await fetch(`/api/daily-square?round=${round}`);
    if (!response.ok) {
      throw new Error(`Round ${round} request failed with ${response.status}`);
    }
    return response.json();
  }, roundNumber);
}

async function submitCity(page, roundNumber, method) {
  const round = await fetchRound(page, roundNumber);
  const cityName = round.cities[0].city_name;
  await page.locator('#guessInput').fill(cityName);

  const firstResponsePromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/guess')
    && response.request().method() === 'POST'
  ));

  if (method === 'enter') {
    await page.locator('#guessInput').press('Enter');
  } else {
    await page.locator('#guessBtn').click();
  }

  const firstResponse = await firstResponsePromise;
  const firstRequestBody = firstResponse.request().postDataJSON();
  const firstBody = await firstResponse.json();
  expect(firstRequestBody).toEqual({
    guess: cityName,
    round_number: roundNumber,
    confirmed_city_id: null,
  });

  let result = firstBody;
  if (firstBody.requires_confirmation) {
    const modal = page.locator('#guessConflictModal');
    await expect(modal).toBeVisible();
    const candidate = modal.locator('.modal-btn').filter({ hasNotText: 'None of these' }).first();
    const confirmationResponsePromise = page.waitForResponse((response) => (
      response.url().endsWith('/api/guess')
      && response.request().method() === 'POST'
    ));
    await candidate.click();
    const confirmationResponse = await confirmationResponsePromise;
    const confirmationRequestBody = confirmationResponse.request().postDataJSON();
    result = await confirmationResponse.json();
    expect(Number.isInteger(confirmationRequestBody.confirmed_city_id)).toBe(true);
    await expect(modal).toBeHidden();
  }

  expect(result.correct).toBe(true);
  await expect(page.locator('#guessFeedback')).toContainText(result.city.toUpperCase());
  return result;
}

async function advanceToNextRound(page, nextRoundNumber) {
  const responsePromise = page.waitForResponse((response) => (
    response.url().includes(`/api/daily-square?round=${nextRoundNumber}`)
  ));
  await page.locator('#nextBtn').click();
  await responsePromise;
  await expect(page.locator('#meta')).toContainText(`${nextRoundNumber} / 5`);
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
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

test('completes and resumes a five-round game', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));

  await page.goto('/');
  await openControls(page);
  await expect(page.locator('#meta')).toContainText('1 / 5');

  const expansionResponsePromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/expand')
    && response.request().method() === 'POST'
  ));
  await page.locator('#expandBtn').click();
  const expansionBody = await (await expansionResponsePromise).json();
  expect(expansionBody.expansion_level).toBe(1);

  const roundOne = await submitCity(page, 1, 'click');
  expect(roundOne.expansion_level).toBe(1);
  await advanceToNextRound(page, 2);

  await submitCity(page, 2, 'enter');
  await page.reload();
  await openControls(page);
  await expect(page.locator('#meta')).toContainText('3 / 5');

  await submitCity(page, 3, 'click');
  await advanceToNextRound(page, 4);

  const passResponsePromise = page.waitForResponse((response) => (
    response.url().endsWith('/api/pass')
    && response.request().method() === 'POST'
  ));
  await page.locator('#passBtn').click();
  const passBody = await (await passResponsePromise).json();
  expect(passBody.passed).toBe(true);
  await expect(page.locator('#guessFeedback')).toContainText('No guess submitted');
  await advanceToNextRound(page, 5);

  await submitCity(page, 5, 'enter');
  await expect(page.locator('#shareScoreBtn')).toBeVisible();
  await page.locator('#shareScoreBtn').click();
  const copiedText = await page.evaluate(() => window.__copiedText);
  expect(copiedText).toContain('Game Complete | 4/5 solved');
  expect(copiedText).toContain('R1:');
  expect(copiedText).toContain('R5:');
  expect(copiedText).toContain('pop.');

  await page.locator('#nextBtn').click();
  await expect(page.locator('#statsOverlay')).toBeVisible();

  const state = await page.evaluate(async () => (await fetch('/api/game-state')).json());
  expect(state.state).toBe('completed');
  expect(state.completed_rounds).toHaveLength(5);
  expect(state.completed_rounds.filter((round) => round.round_status === 'Passed')).toHaveLength(1);
  expect(pageErrors).toEqual([]);
});