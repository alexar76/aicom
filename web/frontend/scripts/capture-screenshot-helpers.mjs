/** Shared Playwright helpers for docs screenshots. */
export const delay = (ms) => new Promise((r) => setTimeout(r, ms));

export async function isPasswordlessDemo(base) {
  try {
    const res = await fetch(`${base}/api/public/demo-config`);
    if (!res.ok) return false;
    const body = await res.json();
    return Boolean(body.passwordless_admin);
  } catch {
    return false;
  }
}

export async function preferEnglishLocale(page) {
  await page.evaluate(() => {
    window.localStorage.setItem('admin_locale', 'en');
  });
  const select = page.locator('aside select').first();
  if (await select.isVisible().catch(() => false)) {
    await select.selectOption('en');
    await delay(800);
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 120000 });
    await delay(1500);
  }
  const loginSelect = page.locator('select').first();
  if (await loginSelect.isVisible().catch(() => false)) {
    const val = await loginSelect.inputValue().catch(() => '');
    if (val !== 'en') {
      await loginSelect.selectOption('en');
      await delay(500);
    }
  }
}

/** Reload admin home and wait until KPI numbers render (no spinners). */
export async function waitForDashboardReady(page, { timeout = 240000 } = {}) {
  await page
    .getByText(/Factory health score|Total Products|Всего продуктов|Productos totales/)
    .first()
    .waitFor({ timeout: 90000 });
  await page
    .waitForFunction(
      () => {
        let numericStats = 0;
        for (const node of document.querySelectorAll('.tabular-nums')) {
          const text = (node.textContent || '').trim();
          if (/^\d+$/.test(text)) numericStats += 1;
        }
        const spins = document.querySelectorAll('main .animate-spin');
        const body = document.querySelector('main')?.textContent || '';
        const loading = /Loading metrics|Загрузка метрик/i.test(body);
        return numericStats >= 3 && spins.length === 0 && !loading;
      },
      { timeout },
    )
    .catch(() => delay(12000));
  const statsHeading = page.getByText(/^Total Products$|^Всего продуктов$/);
  if (await statsHeading.isVisible().catch(() => false)) {
    await statsHeading.scrollIntoViewIfNeeded();
  }
  await delay(2000);
}

export async function captureDashboardAndSidebar(page, outDir) {
  await page.goto(`${page.url().split('/admin')[0]}/admin`, {
    waitUntil: 'domcontentloaded',
    timeout: 120000,
  });
  await preferEnglishLocale(page);
  await page.waitForLoadState('networkidle', { timeout: 120000 }).catch(() => {});
  await waitForDashboardReady(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  await delay(1500);
  await page.screenshot({ path: `${outDir}/admin-dashboard.png`, timeout: 120000 });
  await page.locator('aside').first().screenshot({ path: `${outDir}/admin-sidebar.png`, timeout: 120000 });
}

export async function adminLogin(page, { base, password, outDir }) {
  const passwordless = await isPasswordlessDemo(base);
  await page.goto(`${base}/admin/login`, { waitUntil: 'domcontentloaded', timeout: 120000 });
  await page.evaluate(() => {
    window.localStorage.setItem('admin_locale', 'en');
  });
  await delay(1500);
  const loginLocale = page.locator('select').first();
  if (await loginLocale.isVisible().catch(() => false)) {
    await loginLocale.selectOption('en');
    await delay(500);
  }
  if (outDir) {
    await page.screenshot({ path: `${outDir}/admin-login.png`, timeout: 120000 });
  }

  const passInput = page
    .getByPlaceholder('Enter admin password')
    .or(page.locator('input[type="password"]'));
  const passVisible = !passwordless && (await passInput.isVisible().catch(() => false));
  if (passVisible) {
    if (!password) throw new Error('Password field visible — set ADMIN_PASSWORD');
    await passInput.fill(password);
    await page.getByRole('button', { name: /^Login$|^Войти$|^Entrar$/i }).click();
  } else {
    await page
      .getByRole('button', { name: /Enter admin demo|Открыть демо|Entrar al demo|Login|Войти/i })
      .click();
  }
  await page.waitForURL(/\/admin/, { timeout: 90000 });
  await preferEnglishLocale(page);
  await page.waitForLoadState('networkidle', { timeout: 120000 }).catch(() => {});
  await waitForDashboardReady(page);
}

export async function gotoAdminTab(page, base, tabId) {
  await page.goto(`${base}/admin?tab=${tabId}`, { waitUntil: 'domcontentloaded', timeout: 120000 });
  await preferEnglishLocale(page);
  await page.waitForLoadState('networkidle', { timeout: 120000 }).catch(() => {});
  await delay(800);
}

/** Wait until common loading placeholders disappear in <main>. */
export async function waitForMainSettled(page, { timeout = 180000 } = {}) {
  const loadingPatterns = [
    /Fetching first catalog page/i,
    /Loading first catalog page/i,
    /Loading logs/i,
    /Loading products/i,
    /Loading pipeline catalog/i,
    /Loading audit logs/i,
    /Loading security report/i,
    /Loading video/i,
    /Запрос первой страницы каталога/i,
  ];
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const bodyText = await page.locator('main').innerText().catch(() => '');
    const stuck = loadingPatterns.some((re) => re.test(bodyText));
    const spins = await page.locator('main .animate-spin').count();
    if (!stuck && spins === 0) {
      await delay(1500);
      return;
    }
    await delay(1000);
  }
  await delay(3000);
}

/** Pipeline tab: wait for catalog rows, not just summary KPIs. */
export async function waitForPipelineReady(page, { timeout = 300000 } = {}) {
  await page.getByRole('heading', { name: /^Pipeline$|^Пайплайн$/i }).waitFor({ timeout: 90000 });
  await page
    .getByText(/In catalog|В каталоге|En catálogo/i)
    .first()
    .waitFor({ timeout: 120000 })
    .catch(() => {});
  await waitForMainSettled(page, { timeout });
  await page
    .waitForFunction(
      () => {
        const body = document.querySelector('main')?.textContent || '';
        if (/Loading first catalog page|Запрос первой страницы|Fetching first catalog page/i.test(body)) {
          return false;
        }
        if (/Request attempt \d+ of \d+/i.test(body) && !/prod-[a-f0-9]{6,}/i.test(body)) {
          return false;
        }
        return /prod-[a-f0-9]{6,}/i.test(body);
      },
      { timeout },
    )
    .catch(() => delay(15000));
  const productId = page.locator('main').getByText(/prod-[a-f0-9]{6,}/i).first();
  if (await productId.isVisible().catch(() => false)) {
    await productId.scrollIntoViewIfNeeded();
  } else {
    await page.evaluate(() => window.scrollTo(0, 560));
  }
  await delay(1500);
}

export async function captureAdminTab(page, base, tabId, outPath, waitFn) {
  await gotoAdminTab(page, base, tabId);
  if (waitFn) {
    await waitFn(page);
  } else {
    await waitForMainSettled(page);
  }
  await page.screenshot({ path: outPath, timeout: 120000 });
}
