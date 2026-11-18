// Local editing, recovery and explicit record submission through the real UI.
import { runE2E, expect, assert } from "./e2e-harness.mjs";

await runE2E("records-local-cache", async ({ origin, login, scenario }) => {
  const { page, errors } = await login();
  const writes = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/workout") && request.method() !== "GET") {
      writes.push({
        url: request.url(),
        method: request.method(),
        id: request.headers()["x-request-id"],
      });
    }
  });
  await scenario(
    "settings anchors and fixed composer on desktop and mobile",
    async () => {
      for (const width of [1280, 390]) {
        await page.setViewportSize({ width, height: 844 });
        await page.screenshot({ path: `runtime/frontend-${width}.png` });
        const composer = page.locator(".conversation-controls");
        const box = await composer.boundingBox();
        assert.ok(box.y + box.height <= 845);
        await page.getByLabel("展开历史对话").click();
        await expect(page.locator(".history-reveal")).toHaveCSS(
          "transform",
          "none",
        );
        const history = await page.getByLabel("历史对话面板").boundingBox();
        assert.ok(history.y + history.height <= box.y + 1);
        await page.getByLabel("展开历史对话").click();
        await page
          .getByRole("button", { name: "e2e-user", exact: true })
          .hover();
        await page.getByRole("menuitem", { name: "设置", exact: true }).click();
        await expect(page.locator("#settings-profile")).toHaveCount(1);
        await expect(page.locator("#settings-ai")).toHaveCount(1);
        await page.getByRole("button", { name: "安全", exact: true }).click();
        await expect(
          page.getByLabel("当前密码", { exact: true }),
        ).toBeInViewport();
        await expect(
          page.getByRole("button", { name: "安全", exact: true }),
        ).toHaveAttribute("aria-current", "location");
        await page.screenshot({ path: `runtime/settings-${width}.png` });
        await page
          .getByRole("dialog", { name: "设置", exact: true })
          .getByRole("button", { name: "Close", exact: true })
          .click();
      }
      await page.setViewportSize({ width: 1280, height: 844 });
    },
  );
  const workouts = async () =>
    await (
      await page.request.get(
        origin +
          "/api/workouts?on=" +
          new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Shanghai" }),
      )
    ).json();
  const day = new Date().toLocaleDateString("sv-SE", {
    timeZone: "Asia/Shanghai",
  });
  const close = async () => {
    await page
      .getByRole("dialog", { name: "记录训练", exact: true })
      .getByRole("button", { name: "Close", exact: true })
      .click();
    await page
      .getByRole("button", { name: "保存记录", exact: true })
      .waitFor({ state: "hidden" });
  };
  const resume = async () => {
    await page
      .getByRole("button", { name: `${day} 1条训练`, exact: true })
      .click();
    await page.getByRole("button", { name: "编辑记录", exact: true }).click();
  };
  const create = async () => {
    await page.getByRole("button", { name: "新增训练", exact: true }).click();
    await page.getByRole("button", { name: "添加动作", exact: true }).click();
  };
  const weight = () => page.getByLabel("第1组重量");
  const reps = () => page.getByLabel("第1组次数");
  const save = async () => {
    await page.getByRole("button", { name: "保存记录", exact: true }).click();
    await page.getByText("记录已保存", { exact: true }).waitFor();
  };
  await scenario(
    "typing and closing perform zero writes",
    async () => {
      await page
        .getByRole("button", { name: `${day} 没有记录`, exact: true })
        .click();
      await page.getByRole("button", { name: "新增训练", exact: true }).click();
      await page.getByRole("button", { name: "添加动作", exact: true }).click();
      await weight().fill("60");
      await reps().fill("8");
      await close();
      assert.equal(writes.length, 0);
      assert.equal((await workouts()).total, 0);
    },
  );
  await scenario("closing and reload discard unsaved input", async () => {
    await page.reload();
    await expect(
      page.getByRole("button", { name: "继续编辑未保存的记录" }),
    ).toHaveCount(0);
    await page
      .getByRole("button", { name: `${day} 没有记录`, exact: true })
      .click();
    await create();
    await weight().fill("60");
    await reps().fill("9");
    await page.reload();
    await page
      .getByRole("button", { name: `${day} 没有记录`, exact: true })
      .click();
    await create();
    await expect(reps()).not.toHaveValue("9");
    await weight().fill("60");
    await reps().fill("9");
    assert.equal(writes.length, 0);
  });
  await scenario(
    "explicit save sends exactly one direct create request",
    async () => {
      await save();
      assert.equal(writes.length, 1);
      assert.ok(writes[0].url.endsWith("/api/workouts"));
      const records = await workouts();
      assert.equal(records.total, 1);
      assert.equal(records.items[0].content.exercises[0].sets[0].reps, 9);
      await expect(
        page.getByRole("button", { name: "继续编辑未保存的记录" }),
      ).toHaveCount(0);
    },
  );
  await scenario(
    "manual edits stay local until a single update request",
    async () => {
      await page
        .getByRole("button", { name: `${day} 1条训练`, exact: true })
        .click();
      await page.getByRole("button", { name: "编辑记录", exact: true }).click();
      await reps().fill("12");
      await close();
      assert.equal(writes.length, 1);
      assert.equal(
        (await workouts()).items[0].content.exercises[0].sets[0].reps,
        9,
      );
      await resume();
      await expect(reps()).toHaveValue("9");
      await reps().fill("12");
      await save();
      assert.equal(writes.length, 2);
      assert.equal(writes[1].method, "PUT");
      assert.equal(
        (await workouts()).items[0].content.exercises[0].sets[0].reps,
        12,
      );
    },
  );
  await scenario(
    "discarding cached edits leaves saved data intact",
    async () => {
      await page
        .getByRole("button", { name: `${day} 1条训练`, exact: true })
        .click();
      await page.getByRole("button", { name: "编辑记录", exact: true }).click();
      await reps().fill("15");
      await close();
      await expect(
        page.getByRole("button", { name: "继续编辑未保存的记录" }),
      ).toHaveCount(0);
      assert.equal(writes.length, 2);
      assert.equal(
        (await workouts()).items[0].content.exercises[0].sets[0].reps,
        12,
      );
    },
  );
  await scenario(
    "lost save response retries the same request in the open editor",
    async () => {
      await page
        .getByRole("button", { name: `${day} 1条训练`, exact: true })
        .click();
      await page.getByRole("button", { name: "编辑记录", exact: true }).click();
      await reps().fill("16");
      const id = (await workouts()).items[0].id;
      await page.route("**/api/workouts/" + id, async (route) => {
        if (route.request().method() === "PUT") {
          await route.fetch();
          await route.abort("failed");
        } else await route.continue();
      });
      await page.getByRole("button", { name: "保存记录", exact: true }).click();
      await page
        .getByRole("button", { name: "重试保存并核实结果", exact: true })
        .waitFor();
      await page.unroute("**/api/workouts/" + id);
      const requestId = writes.at(-1).id;
      await page
        .getByRole("button", { name: "重试保存并核实结果", exact: true })
        .click();
      await page.getByText("记录已保存", { exact: true }).waitFor();
      assert.equal(writes.at(-1).id, requestId);
      const records = await workouts();
      assert.equal(records.total, 1);
      assert.equal(records.items[0].version, 3);
      assert.equal(records.items[0].content.exercises[0].sets[0].reps, 16);
    },
  );
  await scenario(
    "conflict preserves local input and can adopt the current record",
    async () => {
      await page
        .getByRole("button", { name: `${day} 1条训练`, exact: true })
        .click();
      await page.getByRole("button", { name: "编辑记录", exact: true }).click();
      await reps().fill("19");
      const original = (await workouts()).items[0];
      const content = original.content;
      content.exercises = content.exercises.map(({ name, ...item }) => item);
      content.exercises[0].sets[0].reps = 20;
      const csrf = (
        await (await page.request.get(origin + "/api/auth/me")).json()
      ).csrf_token;
      const response = await page.request.put(
        origin + "/api/workouts/" + original.id,
        {
          data: { content, version: original.version },
          headers: {
            "X-CSRF-Token": csrf,
            "X-Request-ID": crypto.randomUUID(),
          },
        },
      );
      assert.equal(response.status(), 200);
      await page.getByRole("button", { name: "保存记录", exact: true }).click();
      await expect(
        page.getByRole("button", { name: "重试保存", exact: true }),
      ).toBeVisible();
      await expect(reps()).toHaveValue("19");
      assert.equal(
        (await workouts()).items[0].content.exercises[0].sets[0].reps,
        20,
      );
      await page
        .getByRole("button", { name: "查看最新记录", exact: true })
        .click();
      await page
        .getByRole("dialog", { name: "最新训练记录", exact: true })
        .getByRole("button", { name: "采用最新内容", exact: true })
        .click();
      await expect(reps()).toHaveValue("20");
      await reps().fill("21");
      await save();
      assert.equal(
        (await workouts()).items[0].content.exercises[0].sets[0].reps,
        21,
      );
    },
  );
  assert.equal(
    writes.filter((r) => r.url.includes("workout-drafts")).length,
    0,
  );
  assert.deepEqual(errors, []);
});
