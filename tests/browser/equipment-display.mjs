import { runE2E, expect, assert } from './e2e-harness.mjs';
await runE2E('equipment-display', async ({ login, scenario, origin }) => {
  const { page } = await login();
  const me = await (await page.request.get(origin + '/api/auth/me')).json();
  const headers = { 'X-CSRF-Token': me.csrf_token, 'X-Request-ID': crypto.randomUUID() };
  await page.request.post(origin + '/api/user-equipment', { headers, data: { equipment_id: 'dumbbell', name: '我的哑铃' } });
  await page.getByRole('button', { name: '动作与器械', exact: true }).click();
  await page.getByRole('tab', { name: '器械', exact: true }).click();
  const presets = (await (await page.request.get(origin + '/api/equipment')).json()).items;
  const presetCount = presets.length;
  const categoryCount = new Set(presets.map(item => item.category)).size;
  const catalog = page.locator('.equipment-catalog');
  await scenario('all public equipment grouped once with user name and original-name search', async () => {
    await expect(catalog.locator('section .equipment-row')).toHaveCount(presetCount);
    await expect(catalog.locator('section')).toHaveCount(categoryCount);
    await page.getByLabel('搜索器械', { exact: true }).fill('哑铃');
    await expect(catalog.locator('section .equipment-row')).toHaveCount(1);
    await expect(catalog.getByLabel('器械名称', { exact: true })).toHaveValue('我的哑铃');
  });
  await scenario('failed rename preserves input and retry saves', async () => {
    await catalog.getByLabel('器械名称', { exact: true }).fill('家中哑铃');
    await page.route('**/api/user-equipment/*', route => route.fulfill({ status: 500, json: { detail: 'failed' } }));
    await catalog.getByRole('button', { name: '保存名称', exact: true }).click();
    await expect(page.locator('.ant-message-error')).toBeVisible();
    await expect(catalog.getByLabel('器械名称', { exact: true })).toHaveValue('家中哑铃');
    await page.unroute('**/api/user-equipment/*');
    await catalog.getByRole('button', { name: '保存名称', exact: true }).click();
    await expect(page.getByText('器械名称已保存', { exact: true })).toBeVisible();
    await expect(catalog.getByRole('button', { name: '保存名称', exact: true })).toBeDisabled();
    await catalog.getByRole('button', { name: /移\s*除/, exact: true }).click();
    await expect(catalog.getByText('哑铃', { exact: true })).toBeVisible();
    await expect(catalog.getByLabel('器械名称', { exact: true })).toHaveCount(0);
  });
  await scenario('custom create and remove on mobile preserve public catalog', async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByLabel('搜索器械', { exact: true }).fill('');
    await page.getByLabel('自定义器械名称').fill('弹力绳');
    await page.getByRole('button', { name: '新增器械', exact: true }).click();
    const other = page.getByRole('region', { name: '其他', exact: true });
    await expect(other.getByLabel('器械名称', { exact: true })).toHaveValue('弹力绳');
    await expect(catalog.locator('section .equipment-row')).toHaveCount(presetCount + 1);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await other.getByRole('button', { name: /移\s*除/, exact: true }).click();
    await expect(catalog.locator('section .equipment-row')).toHaveCount(presetCount);
  });
  await scenario('failed public loading can retry', async () => {
    await page.getByRole('tab', { name: '动作', exact: true }).click();
    await page.route('**/api/equipment', route => route.fulfill({ status: 500, json: { detail: 'failed' } }));
    await page.getByRole('tab', { name: '器械', exact: true }).click();
    await expect(catalog.getByRole('alert')).toBeVisible();
    await page.unroute('**/api/equipment');
    await catalog.getByRole('button', { name: /重\s*试/, exact: true }).click();
    await expect(catalog.getByRole('alert')).toHaveCount(0);
    await expect(catalog.locator('section .equipment-row')).toHaveCount(presetCount);
  });
});
