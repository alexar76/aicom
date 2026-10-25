import { expect, test } from '@playwright/test';
import baseline from './fixtures/tailwind-v3-style-contract.json';

// Values captured from the working v3 production build before the dependency migration.
// Ignore only transparent zero-size shadow layers; the visible geometry stays identical.
function visibleShadows(value: string) {
  return value.split(/,(?![^()]*\))/).map((part) => part.trim())
    .filter((part) => !/^rgba\(0, 0, 0, 0\) 0px 0px 0px 0px$/.test(part));
}

for (const width of [375, 1280]) {
  test(`Tailwind migration preserves production utility styles at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/e2e-fixtures/charts-motion');
    await page.waitForLoadState('networkidle');
    const actual = await page.evaluate((cases) => {
      const host = document.createElement('div');
      host.style.cssText = 'position:absolute;left:0;top:0;width:800px';
      document.body.append(host);
      return cases.map((item) => {
        const element = document.createElement('div');
        element.textContent = 'Compatibility';
        element.className = item.className;
        host.append(element);
        const style = getComputedStyle(element);
        return Object.fromEntries(Object.keys(item.expected).map((property) => [property, style.getPropertyValue(
          property.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`),
        )]));
      });
    }, baseline);
    for (let i = 0; i < baseline.length; i++) {
      for (const [property, expected] of Object.entries(baseline[i].expected)) {
        const value = actual[i][property];
        if (property === 'boxShadow') {
          expect(visibleShadows(value), baseline[i].name).toEqual(visibleShadows(expected));
        } else {
          expect(value, `${baseline[i].name}.${property}`).toBe(expected);
        }
      }
    }
  });
}

test('preserves form defaults and migrated non-shrinking layout', async ({ page }) => {
  await page.goto('/e2e-fixtures/charts-motion');
  const defaults = await page.evaluate(() => {
    const host = document.createElement('div');
    host.innerHTML = '<button>Enabled</button><button disabled>Disabled</button><input placeholder="Name"><div class="border shrink-0">Content</div>';
    document.body.append(host);
    const [button, disabled, input, box] = Array.from(host.children);
    return {
      button: getComputedStyle(button).cursor,
      disabled: getComputedStyle(disabled).cursor,
      placeholder: getComputedStyle(input, '::placeholder').color,
      border: getComputedStyle(box).borderTopColor,
      shrink: getComputedStyle(box).flexShrink,
    };
  });
  expect(defaults.button).toBe('pointer');
  expect(defaults.disabled).not.toBe('pointer');
  expect(defaults.placeholder).toBe('rgb(156, 163, 175)');
  expect(defaults.border).toBe('rgb(229, 231, 235)');
  expect(defaults.shrink).toBe('0');
});
