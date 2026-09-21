const { test, expect } = require('@playwright/test');

test('loads the profile page', async ({ page }) => {
  await page.goto('/profile', { waitUntil: 'load' });

  await expect(page.locator('#profileLoadingState')).toBeHidden();
});