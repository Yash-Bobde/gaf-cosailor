import { expect, test, type Page } from '@playwright/test';

const STUB = 'http://127.0.0.1:8765';

async function useScenario(page: Page, name: string) {
  const res = await page.request.post(`${STUB}/__scenario?name=${name}`);
  expect(res.ok()).toBeTruthy();
}

function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg) => { if (msg.type() === 'error') errors.push(`${msg.text()} @ ${msg.location().url}`); });
  page.on('pageerror', (err) => errors.push(err.message));
  return errors;
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

test('principal path: run → progress → lead → brief with evidence and GAF profile → back', async ({ page }) => {
  await useScenario(page, 'happy');
  const errors = collectConsoleErrors(page);

  await page.goto('/');
  await expect(page.getByText('Your call sheet is empty.')).toBeVisible();
  await expect(page.getByLabel('ZIP code')).toHaveValue('10013');

  await page.getByRole('button', { name: /build call list/i }).click();
  await expect(page.getByRole('progressbar', { name: 'Leads processed' })).toBeVisible();

  const leadLink = page.getByRole('link', { name: 'Allied Brothers Construction', exact: true });
  await expect(leadLink).toBeVisible();
  await expect(page.getByText('Last run scored 1 of 1 contractors.')).toBeVisible();
  await expect(page.getByRole('listitem').getByText('Call first', { exact: true })).toBeVisible();

  await leadLink.click();
  await expect(page.getByRole('heading', { level: 1, name: 'Allied Brothers Construction' })).toBeVisible();
  await expect(page.getByText('Decision-maker', { exact: true })).toBeVisible();
  await expect(page.getByText(/Owner Maria Lopez oversees all bids/).first()).toBeVisible();
  await expect(page.getByRole('link', { name: /bbb\.org/ }).first()).toHaveAttribute('rel', 'noopener noreferrer');

  const profile = page.getByRole('link', { name: /view gaf profile/i });
  await expect(profile).toHaveAttribute('href', /^https:\/\/www\.gaf\.com\//);
  await expect(profile).toHaveAttribute('target', '_blank');
  await expect(profile).toHaveAttribute('rel', 'noopener noreferrer');

  await page.getByRole('link', { name: '← Call sheet' }).click();
  await expect(page.getByRole('heading', { name: /who to call/i })).toBeVisible();
  expect(errors).toEqual([]);
});

test('390 px: call sheet and brief have no horizontal overflow', async ({ page }) => {
  await useScenario(page, 'happy');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByRole('button', { name: /build call list/i }).click();
  await expect(page.getByRole('link', { name: 'Allied Brothers Construction', exact: true })).toBeVisible();
  await expectNoHorizontalOverflow(page);

  await page.getByRole('link', { name: 'Allied Brothers Construction', exact: true }).click();
  await expect(page.getByRole('link', { name: /view gaf profile/i })).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test('cancellation: the run drains and ends cancelled', async ({ page }) => {
  await useScenario(page, 'cancel');
  await page.goto('/');
  await page.getByRole('button', { name: /build call list/i }).click();
  await expect(page.getByText('Researching and scoring each lead…')).toBeVisible();

  await page.getByRole('button', { name: /cancel run/i }).click();
  await expect(page.getByText('Stopping after the leads in progress…')).toBeVisible();
  await expect(page.getByText(/Last run cancelled after scoring 1 leads/)).toBeVisible();
});

test('a failed GAF scrape is reported, not shown as success', async ({ page }) => {
  await useScenario(page, 'run-fails');
  await page.goto('/');
  await page.getByRole('button', { name: /build call list/i }).click();
  await expect(page.getByText(/failed while reading the GAF directory/)).toBeVisible();
  await expect(page.getByText(/Last run scored/)).toHaveCount(0);
});

test('backend unavailable: clear recovery instructions, no stack trace', async ({ page }) => {
  await useScenario(page, 'down');
  await page.goto('/');
  const alert = page.getByRole('alert').filter({ hasText: "Can't reach the leads service." });
  await expect(alert).toBeVisible();
  await expect(alert).toContainText('port 8000');
  await expect(page.getByRole('link', { name: 'Try again' })).toBeVisible();
  await expect(page.getByText(/Traceback|TypeError|ECONNREFUSED/)).toHaveCount(0);
});

test('keyboard: run form fields are reachable with Tab and show a visible focus ring', async ({ page }) => {
  await useScenario(page, 'happy');
  await page.goto('/');
  const zip = page.getByLabel('ZIP code');
  await zip.focus();
  await expect(zip).toBeFocused();
  const outline = await zip.evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(outline).not.toBe('none');
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Max leads')).toBeFocused();
});

test('a lead whose research failed is shown honestly, with no invented brief', async ({ page }) => {
  await useScenario(page, 'failed-lead');
  await page.goto('/');
  const row = page.getByRole('listitem').filter({ hasText: 'Harbor Roofing LLC' });
  await expect(row.getByText('Needs retry', { exact: true })).toBeVisible();
  await expect(page.getByText(/HTTP 401/)).toHaveCount(0);

  await page.getByRole('link', { name: 'Harbor Roofing LLC', exact: true }).click();
  const alert = page.getByRole('alert').filter({ hasText: 'Research failed' });
  await expect(alert).toContainText('Web research for this contractor failed');
  await expect(alert).toContainText('nothing was guessed');
  await expect(page.getByText('Talking points')).toHaveCount(0);
  await expect(page.getByText(/HTTP 401/)).toHaveCount(0);
  await expect(page.getByRole('link', { name: /view gaf profile/i })).toBeVisible();
});
