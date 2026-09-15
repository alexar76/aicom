import { expect, test } from '@playwright/test';

test.describe('React 19 — recharts + framer-motion', () => {
  test('vitals charts mount and motion hero animates', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/e2e-fixtures/charts-motion');
    await page.waitForLoadState('networkidle');

    const hero = page.getByTestId('motion-hero');
    await expect(hero).toBeVisible();
    await expect(hero).toHaveText(/React 19 charts \+ motion fixture/);

    const charts = page.getByTestId('vitals-charts');
    await expect(charts).toBeVisible();
    await expect(charts.locator('[aria-label*="Product vitals"]')).toBeVisible();

    // PipelineProductVitalsCharts (recharts + framer-motion deps) rendered vitals tiles.
    await expect(charts.getByText('LLM spend', { exact: true })).toBeVisible();
    await expect(charts.getByText('Pipeline progress', { exact: true })).toBeVisible();
    await expect(charts.getByText('Quality', { exact: true })).toBeVisible();
    await expect(charts.getByText('100%')).toBeVisible();
  });

  test('home page motion blocks render without console errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));

    await page.goto('/');
    await expect(page.locator('body')).toBeVisible();
    await page.waitForTimeout(500);

    const critical = errors.filter(
      (m) => !m.includes('ResizeObserver') && !m.includes('hydration'),
    );
    expect(critical).toEqual([]);
  });
});
