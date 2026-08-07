const { test, expect } = require('@playwright/test');
const fixture = require('./artifacts/weekly_fixture.json');


function progress(message) {
  console.log(`[${new Date().toISOString()}] [weekly-random] ${message}`);
}

async function submitGuess(page, roundFixture) {
  const guessInput = page.locator('#guessInput');
  await guessInput.fill(roundFixture.city_name);
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
    (candidate) => candidate.city_id === roundFixture.city_id,
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
    .toBe(roundFixture.city_id);
  return confirmationResponse.json();
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
  });
});

test('completes five randomly selected squares', async ({ page }) => {
  expect(fixture.rounds).toHaveLength(5);
  await page.goto('/');
  await expect(page.locator('#guessInput')).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('#meta')).toContainText('1 / 5');

  for (const roundFixture of fixture.rounds) {
    progress(
      `round ${roundFixture.round_number}: submitting ${roundFixture.city_name} `
      + `for pool square ${roundFixture.pool_square_id}`,
    );
    const result = await submitGuess(page, roundFixture);
    expect(result.correct).toBe(true);
    expect(result.city).toBe(roundFixture.city_name);
    expect(result.score).toBeGreaterThan(0);
    await expect(page.locator('#guessFeedback'))
      .toContainText(roundFixture.city_name.toUpperCase());

    if (roundFixture.round_number === 2) {
      progress('reloading to verify resume behavior');
      await page.reload();
      await expect(page.locator('#guessInput')).toBeVisible({ timeout: 10_000 });
      await expect(page.locator('#meta')).toContainText('3 / 5');
    } else if (roundFixture.round_number < 5) {
      await advanceToRound(page, roundFixture.round_number + 1);
    }
  }

  const state = await page.evaluate(async () => (await fetch('/api/game-state')).json());
  expect(state.state).toBe('completed');
  expect(state.completed_rounds).toHaveLength(5);
  expect(state.completed_rounds.every((round) => round.round_status === 'Completed'))
    .toBe(true);
  progress('weekly randomized game completed');
});