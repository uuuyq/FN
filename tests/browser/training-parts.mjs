import { runE2E, expect, assert } from "./e2e-harness.mjs";
await runE2E("training-parts", async ({ login, scenario }) => {
  const { page } = await login();
  await scenario("Welcome dismiss persists and guide reopens", async () => {
    await expect(
      page.getByText("从一句提问开始，快速了解功能。", { exact: true }),
    ).toBeVisible();
    await expect(page.getByLabel("训练消息", {exact: true})).toHaveValue("你有哪些功能？我该怎么开始记录训练或生成训练计划？");
    await expect(page.getByRole("button", {name: "发送消息", exact: true})).toBeEnabled();
    await Promise.all([
      page.waitForResponse(r => r.url().endsWith("/auth/onboarding/dismiss") && r.ok()),
      page.getByRole("button", { name: "关闭对话引导" }).click(),
    ]);
    await page.reload();
    await expect(page.getByLabel("训练日历", { exact: true })).toBeVisible();
    await expect(
      page.getByText("从一句提问开始，快速了解功能。", { exact: true }),
    ).toHaveCount(0);
    await page.getByLabel("训练消息", {exact: true}).fill("保留我的问题");
    await page.getByRole("button", { name: "通知与公告" }).click();
    await page.getByRole("button", { name: "使用指南", exact: true }).click();
    await expect(
      page.getByText("从一句提问开始，快速了解功能。", { exact: true }),
    ).toBeVisible();
    await expect(page.getByLabel("训练消息", {exact: true})).toHaveValue("保留我的问题");
    await page.getByRole("button", { name: "关闭对话引导" }).click();
  });
  await scenario("Seven parts fit desktop and mobile", async () => {
    await page.route("**/api/workouts/calendar?*", async (route) => {
      const month = new URL(route.request().url()).searchParams.get("month");
      await route.fulfill({
        json: {
          month,
          training_days: 1,
          days: [
            {
              date: `${month}-01`,
              count: 3,
              parts: ["胸", "背", "腿", "二头", "三头", "肩", "腹"],
            },
          ],
        },
      });
    });
    await page.reload();
    await expect(page.locator(".calendar-day .training-part")).toHaveCount(2);
    for (const width of [1280, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      const calendar = page.locator(".calendar-card");
      assert.ok((await calendar.boundingBox()).width <= width);
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      );
      for (const part of await page
        .locator(".calendar-day .training-part")
        .all()) {
        assert.ok(
          await part.evaluate((el) => !el.getBoundingClientRect().width || el.scrollWidth <= el.clientWidth),
        );
      }
      await page.screenshot({
        path: `runtime/training-calendar-${width}.png`,
        fullPage: true,
      });
    }
  });

  await scenario("Stacked parts expand in date details", async () => {
    await page.setViewportSize({width: 1280, height: 1000});
    await page.locator(".calendar-day").first().click();
    await expect(page.locator(".date-training-parts .training-part")).toHaveCount(7);
    await page.getByRole("button", {name: "Close", exact: true}).click();
  });
  await scenario("Square calendar fits available screen height", async () => {
    let parts = [];
    await page.unroute("**/api/workouts/calendar?*");
    await page.route("**/api/workouts/calendar?*", async route => {
      const month = new URL(route.request().url()).searchParams.get("month");
      await route.fulfill({json: {month, training_days: 1, days: [{date: `${month}-01`, count: 1, parts}]}});
    });
    for (const [width, height] of [[1280, 720], [1280, 900], [390, 844], [320, 667]]) {
      await page.setViewportSize({width, height});
      for (const count of [0, 1, 3, 7]) {
        parts = ["胸", "背", "腿", "二头", "三头", "肩", "腹"].slice(0, count);
        await page.reload();
        await expect(page.locator(".calendar-day .training-part")).toHaveCount(Math.min(count, 2));
        const metrics = await page.locator('.calendar-card').evaluate(el => {
          const days = [...el.querySelectorAll('.calendar-day')];
          const part = el.querySelector('.training-part');
          return {
            bottom: el.getBoundingClientRect().bottom,
            composerTop: document.querySelector('.conversation-controls').getBoundingClientRect().top,
            square: days.every(day => Math.abs(day.getBoundingClientRect().width - day.getBoundingClientRect().height) < 1),
            overflow: days.some(day => day.scrollHeight > day.clientHeight + 1),
            partHeight: part?.getBoundingClientRect().height,
          };
        });
        assert.ok(metrics.square, JSON.stringify({width, height, count, metrics}));
        assert.equal(metrics.overflow, false, JSON.stringify({width, height, count, metrics}));
        if (count) assert.equal(metrics.partHeight, width > 600 ? 28 : 20);
        assert.ok(metrics.bottom <= metrics.composerTop, JSON.stringify({width, height, count, metrics}));
      }
      await page.screenshot({path: `runtime/calendar-fit-${width}-${height}.png`, fullPage: true});
    }
  });

});
