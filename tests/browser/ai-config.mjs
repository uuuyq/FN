import { runE2E, expect } from "./e2e-harness.mjs";

await runE2E("ai-config", async ({ login, scenario }) => {
  const { page } = await login();
  await scenario("first login can defer configuration persistently", async () => {
    const dialog = page.getByRole("dialog", { name: "配置 AI 模型" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByLabel("接口地址", { exact: true })).toHaveValue("https://api.deepseek.com");
    await dialog.getByRole("button", { name: "稍后配置" }).click();
    await expect(dialog).not.toBeVisible();
    await page.reload();
    await expect(page.getByRole("button", { name: "配置模型，开始 AI 对话" })).toBeVisible();
    await expect(dialog).not.toBeVisible();
  });
  await scenario("custom configuration failure keeps draft and can retry", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("button", { name: "配置模型，开始 AI 对话" }).click();
    const dialog = page.getByRole("dialog", { name: "配置 AI 模型" });
    await dialog.locator(".ant-select").first().click();
    await page.getByTitle("自定义兼容接口", { exact: true }).click();
    await dialog.getByLabel("接口地址", { exact: true }).fill("https://example.com/v1");
    await dialog.getByLabel("模型", { exact: true }).fill("custom-model");
    await dialog.getByLabel("API Key", { exact: true }).fill("test-key");
    await page.route("**/api/ai-config", route => route.request().method() === "PUT"
      ? route.fulfill({ status: 502, json: { detail: { code: "model_auth_failed" } } })
      : route.continue());
    await dialog.getByRole("button", { name: "验证并保存" }).click();
    await expect(page.locator(".ant-message-error")).toBeVisible();
    await expect(dialog.getByLabel("模型", { exact: true })).toHaveValue("custom-model");
    await page.unroute("**/api/ai-config");
    await page.route("**/api/ai-config", route => route.request().method() === "PUT"
      ? route.fulfill({ json: { configured: true, provider: "custom", version: 2, model: "custom-model", base_url: "https://example.com/v1", has_api_key: true } })
      : route.continue());
    await dialog.getByRole("button", { name: "验证并保存" }).click();
    await expect(dialog).not.toBeVisible();
    await expect(page.getByText("验证通过，AI 模型配置已保存", { exact: true })).toBeVisible();
  });
});
