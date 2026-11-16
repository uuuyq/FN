import { runE2E, expect } from "./e2e-harness.mjs";
await runE2E("settings-feedback", async ({ login, scenario }) => {
  await scenario("Markdown history renders safely at desktop and mobile widths", async () => {
    const { page: chat } = await login();
    const user = await (await chat.request.get(new URL("/api/auth/me", chat.url()).href)).json();
    const content = "### 训练建议\n\n- **卧推** 3组\n- 深蹲\n\n> 保持稳定\n\n```text\n60kg\n```\n\n| 动作 | 组次 |\n| --- | --- |\n| 卧推 | 3×8 |\n\n<script>alert(1)</script>";
    await chat.route("**/api/conversations/markdown-test", route => route.fulfill({ json: {
      id: "markdown-test", title: "Markdown", turns: [], actions: [], messages: [
        { id: "m1", role: "assistant", content, sequence: 1, turn_id: "t1" },
      ],
    } }));
    await chat.route("**/api/conversations?limit=200", route => route.fulfill({ json: { items: [{ id: "markdown-test", title: "Markdown" }] } }));
    await chat.getByLabel("展开历史对话").click();
    await chat.getByText("Markdown", { exact: true }).click();
    for (const width of [1280, 390]) {
      await chat.setViewportSize({ width, height: 844 });
      const reply = chat.locator(".markdown-reply");
      await expect(reply.locator("h3")).toHaveText("训练建议");
      await expect(reply.locator("strong")).toHaveText("卧推");
      await expect(reply.locator("li")).toHaveCount(2);
      await expect(reply.locator("table")).toHaveCount(1);
      await expect(reply.locator("script")).toHaveCount(0);
    }
  });
  const { page } = await login();
  await page.getByRole("button", { name: "e2e-user", exact: true }).hover();
  await page.getByRole("menuitem", { name: "设置", exact: true }).click();
  await scenario("AI test and save give distinct feedback", async () => {
    await page.route("**/api/ai-config/test", route => route.fulfill({ json: {} }));
    await page.route("**/api/ai-config", route => route.request().method() === "PUT"
      ? route.fulfill({ json: { configured: true, version: 2, model: "test-model", base_url: "https://example.com" } })
      : route.continue());
    await page.getByRole("button", { name: "AI 模型", exact: true }).click();
    await page.getByLabel("接口地址", { exact: true }).fill("https://example.com");
    await page.getByLabel("模型名称", { exact: true }).fill("test-model");
    await page.getByRole("button", { name: "测试连接", exact: true }).click();
    await expect(page.getByText("连接测试通过", { exact: true })).toBeVisible();
    await page.locator("#settings-ai").getByRole("button", { name: /保\s*存/, exact: true }).click();
    await expect(page.getByText("AI 模型配置已保存", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "个人条件", exact: true }).click();
  });
  await scenario(
    "profile save feedback and failure preserve input",
    async () => {
      await page.getByLabel("个人偏好", { exact: true }).fill("测试目标");
      await page
        .getByRole("button", { name: "保存个人条件", exact: true })
        .click();
      await expect(
        page.getByText("个人条件已保存", { exact: true }),
      ).toBeVisible();
      await page.route("**/api/profile", (route) =>
        route.request().method() === "PUT"
          ? route.fulfill({
              status: 500,
              contentType: "application/json",
              body: JSON.stringify({ detail: "保存失败" }),
            })
          : route.continue(),
      );
      await page.getByLabel("个人偏好", { exact: true }).fill("保留重试");
      await page
        .getByRole("button", { name: "保存个人条件", exact: true })
        .click();
      await expect(page.locator(".ant-message-error")).toBeVisible();
      await expect(page.getByLabel("个人偏好", { exact: true })).toHaveValue(
        "保留重试",
      );
      await page.unroute("**/api/profile");
    },
  );
  await scenario("account success survives return to login", async () => {
    await page.getByRole("button", { name: "安全", exact: true }).click();
    await page
      .getByLabel("当前密码", { exact: true })
      .fill("e2e-test-password");
    await page
      .getByLabel("新密码（至少12个字符，修改后重新登录）", { exact: true })
      .fill("updated-test-password");
    await page
      .getByRole("button", { name: "保存账号信息", exact: true })
      .click();
    await expect(
      page.getByText("账号信息已更新，请重新登录", { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /登\s*录/ })).toBeVisible();
  });
});
