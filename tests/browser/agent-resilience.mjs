// Extended real-browser acceptance cases. Only the model provider is scripted.
import { runE2E, expect, assert } from "./e2e-harness.mjs";

await runE2E("agent-resilience", async ({ origin, login, scenario }) => {
  const { page, context, errors } = await login();
  const cards = () => page.locator('[data-action-status="pending"]');
  const newChat = async () => {
    await page.getByRole("button", { name: "新对话", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "训练消息", exact: true })).toHaveValue("");
  };
  const request = async (path, method = "GET", data, requestId = crypto.randomUUID()) => {
    const csrf = (await (await page.request.get(origin + "/api/auth/me")).json()).csrf_token;
    return page.request.fetch(origin + "/api" + path, {
      method, data, headers: { "X-CSRF-Token": csrf, "X-Request-ID": requestId },
    });
  };
  const send = async (text) => {
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.request().method() === "POST" &&
        /\/conversations\/[^/]+\/messages$/.test(r.url())),
      (async () => {
        await page.getByRole("textbox", { name: "训练消息", exact: true }).fill(text);
        await page.getByRole("button", { name: "发送消息", exact: true }).click();
      })(),
    ]);
    assert.equal(response.status(), 200);
    const body = await response.text();
    const events = body.split("\n").filter((line) => line.startsWith("data: "))
      .map((line) => JSON.parse(line.slice(6)));
    const turn = events.at(-1);
    // The SSE can finish before React processes the history reload. Do not
    // overwrite the next input while the previous send is still completing.
    if (turn.status === "succeeded")
      await expect(page.getByRole("textbox", { name: "训练消息", exact: true })).toHaveValue("");
    return { cid: response.url().split("/conversations/")[1].split("/")[0], turn };
  };
  const snapshot = async (cid) => (await (await request("/conversations/" + cid)).json());
  const count = async () => (await (await request("/workouts?on=" + new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Shanghai" }))).json()).total;

  await scenario("SSE displays text before completion and reconciles once", async () => {
    await page.getByRole("textbox", { name: "训练消息", exact: true }).fill("SSE incremental test");
    await page.getByRole("button", { name: "发送消息", exact: true }).click();
    await expect(page.locator(".thinking-status")).toBeVisible();
    const partial = page.locator(".message-bubble.assistant").filter({hasText: "SSE first chunk"});
    await expect(partial).toHaveText("SSE first chunk", {timeout: 1500});
    await expect(page.locator(".thinking-status")).toHaveCount(0);
    await expect(page.getByRole("textbox", { name: "训练消息", exact: true })).toHaveValue("SSE incremental test");
    await expect(partial).toHaveText("SSE first chunk and final chunk");
    await expect(page.getByRole("textbox", { name: "训练消息", exact: true })).toHaveValue("");
    await expect(partial).toHaveCount(1);
    await newChat();
  });

  await scenario("pending card survives reload once, with the same ID", async () => {
    const { cid } = await send("取消新增测试");
    await expect(cards()).toHaveCount(1);
    const detail = cards().locator("details");
    await expect(detail).not.toHaveAttribute("open", "");
    await detail.locator("summary").click();
    await expect(detail).toHaveAttribute("open", "");
    const id = await cards().getAttribute("data-action-id");
    await page.reload();
    await page.getByRole("button", { name: "展开历史对话", exact: true }).click();
    await page.getByRole("button", { name: "取消新增测试", exact: true }).click();
    await expect(cards()).toHaveCount(1);
    assert.equal(await cards().getAttribute("data-action-id"), id);
    assert.equal((await snapshot(cid)).actions[0].status, "pending");
    await cards().getByRole("button", { name: "取消新增训练", exact: true }).click();
    await expect(cards()).toHaveCount(0);
  });

  await scenario("plain query keeps a card executable; cancelled card cannot confirm", async () => {
    await newChat();
    const { cid } = await send("取消新增测试");
    const pending = (await snapshot(cid)).actions[0];
    await send("查询训练");
    // G13: a plain query neither invalidates the card nor blocks confirming.
    await expect(page.locator(`[data-action-id="${pending.action_id}"]`)).toHaveAttribute("data-action-status", "pending");
    const cancelled = await request(`/conversation-actions/${pending.action_id}/cancel`, "POST", { version: pending.version });
    assert.equal(cancelled.status(), 200);
    const response = await request(`/conversation-actions/${pending.action_id}/confirm`, "POST", { version: pending.version });
    assert.equal(response.status(), 409);
    assert.equal(await count(), 0);
  });

  await scenario("double click confirms one write and one result event", async () => {
    await newChat();
    const { cid } = await send("端到端记录");
    await expect(cards()).toHaveCount(1);
    await cards().getByRole("button", { name: "确认执行新增训练", exact: true })
      .evaluate((button) => { button.click(); button.click(); });
    await expect(cards()).toHaveCount(0);
    assert.equal(await count(), 1);
    const history = await snapshot(cid);
    assert.equal(history.messages.filter((m) => m.event_kind === "action_confirmed").length, 1);
    assert.equal(history.turns.length, 2);
    assert.equal(history.messages.filter((m) => m.role === "user").length, 1);
    await expect(page.getByText("Agent 收到操作结果：confirmed", { exact: true })).toBeVisible();
  });

  await scenario("lost confirm response recovers committed state without a second write", async () => {
    await newChat();
    const { cid } = await send("取消新增测试");
    await expect(cards()).toHaveCount(1);
    const before = await count();
    let savedRequest;
    await page.route("**/api/conversation-actions/*/confirm", async (route) => {
      savedRequest = { headers: route.request().headers(), data: route.request().postDataJSON(), url: route.request().url() };
      const upstream = await route.fetch();
      assert.equal(upstream.status(), 200);
      await route.abort("failed"); // commit happened, browser never received the response
    }, { times: 1 });
    await cards().getByRole("button", { name: "确认执行新增训练", exact: true }).click();
    await expect(cards()).toHaveCount(0);
    assert.equal(await count(), before + 1);
    const replay = await page.request.post(savedRequest.url, { data: savedRequest.data,
      headers: { "X-CSRF-Token": savedRequest.headers["x-csrf-token"],
        "X-Request-ID": savedRequest.headers["x-request-id"] } });
    assert.equal(replay.status(), 200);
    assert.equal(await count(), before + 1);
    assert.equal((await snapshot(cid)).messages.filter((m) => m.event_kind === "action_confirmed").length, 1);
  });

  await scenario("page reload during running turn observes it without duplicating input", async () => {
    await newChat();
    await page.getByRole("textbox", { name: "训练消息", exact: true }).fill("慢速记录");
    await page.getByRole("button", { name: "发送消息", exact: true }).click();
    await expect.poll(() => page.evaluate(() => Object.keys(localStorage)
      .some((key) => key.startsWith("fnote-turn-") && localStorage.getItem(key)))).toBe(true);
    await page.reload();
    await page.getByRole("button", { name: "展开历史对话", exact: true }).click();
    await page.getByRole("button", { name: "慢速记录", exact: true }).click();
    await expect(cards()).toHaveCount(1);
    const conversations = await (await request("/conversations")).json();
    const cid = conversations.items.find((c) => c.title === "慢速记录").id;
    const history = await snapshot(cid);
    assert.equal(history.turns.length, 1);
    assert.equal(history.messages.filter((m) => m.role === "user").length, 1);
    await cards().getByRole("button", { name: "取消新增训练", exact: true }).click();
    await expect(cards()).toHaveCount(0);
  });

  for (const [command, code, hint] of [
    ["模拟上下文超限", "context_too_large", "新建会话"],
    ["模拟模型超时", "model_timeout", "超时"],
    ["循环查询", "agent_loop_limit", "上限"],
  ]) await scenario(`${code}: visible hint, no write or pending card`, async () => {
    await newChat();
    const before = await count();
    const { turn } = await send(command);
    assert.equal(turn.status, "failed");
    assert.equal(turn.error, code);
    await expect(page.getByRole("alert").first()).toContainText(hint);
    assert.equal(await cards().count(), 0);
    assert.equal(await count(), before);
    if (code === "context_too_large")
      await expect(page.getByRole("button", { name: "重试本轮", exact: true })).toHaveCount(0);
  });

  await scenario("authenticated second user cannot read or confirm another user's resources", async () => {
    await newChat();
    const { cid, turn } = await send("取消新增测试");
    const action = (await snapshot(cid)).actions[0];
    const other = await login("e2e-other");
    const otherCSRF = (await (await other.page.request.get(origin + "/api/auth/me")).json()).csrf_token;
    for (const path of ["/conversations/" + cid, "/turns/" + turn.id])
      assert.equal((await other.page.request.get(origin + "/api" + path)).status(), 404);
    assert.equal((await other.page.request.post(origin + `/api/conversation-actions/${action.action_id}/confirm`, {
      data: { version: action.version }, headers: { "X-CSRF-Token": otherCSRF, "X-Request-ID": crypto.randomUUID() },
    })).status(), 404);
    assert.equal((await (await other.page.request.get(origin + "/api/workouts?on=" + new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Shanghai" }))).json()).total, 0);
    assert.equal((await (await other.page.request.get(origin + "/api/conversations")).json()).items.length, 0);
    assert.deepEqual(other.errors, []);
    await cards().getByRole("button", { name: "取消新增训练", exact: true }).click();
    await expect(cards()).toHaveCount(0);
  });

  await scenario("conversation rename/delete through UI preserves saved workouts", async () => {
    await newChat();
    const { cid } = await send("查询训练");
    const before = await count();
    await page.getByRole("button", { name: "展开历史对话", exact: true }).click();
    await page.getByRole("button", { name: "管理对话 查询训练", exact: true }).click();
    await page.getByRole("menuitem", { name: "重命名", exact: true }).click();
    await page.getByLabel("对话名称").fill("端到端重命名");
    await page.getByRole("dialog").getByRole("button", { name: /保\s*存/ }).click();
    await expect(page.getByRole("button", { name: "端到端重命名", exact: true })).toBeVisible();
    assert.equal((await snapshot(cid)).title, "端到端重命名");
    await page.getByRole("button", { name: "管理对话 端到端重命名", exact: true }).click();
    await page.getByRole("menuitem", { name: "删除", exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: /删\s*除/ }).click();
    await expect(page.getByRole("button", { name: "端到端重命名", exact: true })).toHaveCount(0);
    assert.equal((await request("/conversations/" + cid)).status(), 404);
    assert.equal(await count(), before);
  });

  await scenario("full conversation beyond 40 messages reaches model and survives reload", async () => {
    await newChat();
    const { cid } = await send("检查长历史");
    for (let i = 0; i < 41; i++) await send("查询训练");
    await send("检查长历史");
    await page.getByText("历史中保留 43 条用户输入。", { exact: true }).waitFor();
    const history = await snapshot(cid);
    assert.equal(history.messages.filter((m) => m.role === "user").length, 43);
    assert.equal(new Set(history.messages.map((m) => m.sequence)).size, history.messages.length);
    await page.reload();
    await page.getByRole("button", { name: "展开历史对话", exact: true }).click();
    await page.getByRole("button", { name: "检查长历史", exact: true }).click();
    await page.getByText("历史中保留 1 条用户输入。", { exact: true }).waitFor();
    await page.getByText("历史中保留 43 条用户输入。", { exact: true }).waitFor();
  });

  await scenario("CSRF rejection and same request ID with changed payload never write", async () => {
    await newChat();
    const { cid } = await send("取消新增测试");
    const action = (await snapshot(cid)).actions[0];
    const before = await count();
    const denied = await page.request.post(origin + `/api/conversation-actions/${action.action_id}/confirm`, {
      data: { version: action.version }, headers: { "X-Request-ID": crypto.randomUUID() },
    });
    assert.equal(denied.status(), 403);
    assert.equal((await snapshot(cid)).actions[0].status, "pending");
    const key = crypto.randomUUID();
    const path = `/conversation-actions/${action.action_id}/cancel`;
    assert.equal((await request(path, "POST", { version: action.version }, key)).status(), 200);
    assert.equal((await request(path, "POST", { version: action.version + 1 }, key)).status(), 409);
    assert.equal(await count(), before);
  });

  assert.deepEqual(errors, []);
});
