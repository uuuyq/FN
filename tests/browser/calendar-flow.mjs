import { chromium, expect } from "./playwright.mjs";
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync } from "node:fs";
import { createServer } from "node:net";
import { resolve, delimiter } from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";

const root = fileURLToPath(new URL("../../", import.meta.url));
mkdirSync(resolve(root, "runtime"), { recursive: true });
const temp = mkdtempSync(resolve(root, "runtime/e2e-"));
const python =
  process.env.PYTHON || resolve(root, "backend/.venv/Scripts/python.exe");
const localDeployment = true;
const backendPort = process.env.E2E_PORT || await new Promise((accept, reject) => {
  const probe = createServer();
  probe.once("error", reject);
  probe.listen(0, "127.0.0.1", () => {
    const port = probe.address().port;
    probe.close(() => accept(String(port)));
  });
});
const backendOrigin = `http://127.0.0.1:${backendPort}`;
const origin = localDeployment
  ? backendOrigin
  : "http://127.0.0.1:5173";
const env = {
  ...process.env,
  PYTHONPATH:
    root + (process.env.PYTHONPATH ? delimiter + process.env.PYTHONPATH : ""),
  COOKIE_SECURE: "false",
  APP_ORIGIN: origin,
  ...(localDeployment ? { FRONTEND_DIST: resolve(root, "frontend/dist") } : {}),
  DATABASE_URL: "sqlite:///" + resolve(temp, "test.db").replaceAll("\\", "/"),
};
const children = [];
let browser;
let page;
let context;
const logs = [];
const failures = [];
function start(command, args, cwd) {
  const child = spawn(command, args, {
    cwd,
    env,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout.on("data", (chunk) => logs.push(String(chunk)));
  child.stderr.on("data", (chunk) => logs.push(String(chunk)));
  children.push(child);
  return child;
}
async function ready(url) {
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(url)).ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 200));
  }
  throw Error("Server did not start: " + logs.join(""));
}
const workouts = async () =>
  await (await page.request.get(origin + "/api/workouts")).json();
async function waitForTotal(expected) {
  for (let i = 0; i < 50; i++) {
    if ((await workouts()).total === expected) return;
    await new Promise((r) => setTimeout(r, 200));
  }
  throw Error("workout total never reached " + expected);
}
const send = async (text) => {
  await page.getByRole("textbox", { name: "训练消息", exact: true }).fill(text);
  await page.getByRole("button", { name: "发送消息", exact: true }).click();
  if (text !== "故障后重试")
    await expect(page.getByRole("textbox", { name: "训练消息", exact: true })).toHaveValue("");
};
const pendingCard = (operation) => page.locator(
  `[data-action-status="pending"]${operation ? `[data-operation="${operation}"]` : ""}`,
);
const snapshot = async () => {
  const response = await page.request.get(origin + "/api/conversations");
  assert.equal(response.status(), 200);
  const cid = (await response.json()).items.find((c) => c.title === "端到端记录").id;
  const history = await page.request.get(origin + "/api/conversations/" + cid);
  assert.equal(history.status(), 200);
  return history.json();
};
const confirmPending = async () => {
  await page.getByRole("button", { name: /^确认执行/ }).click();
};
async function reopenConversation() {
  await page.getByRole("button", { name: "展开历史对话", exact: true }).click();
  await page.getByRole("button", { name: "端到端记录", exact: true }).click();
}
try {
  for (const args of [
    ["-m", "alembic", "upgrade", "head"],
    ["-m", "tests.tooling.e2e_setup"],
  ]) {
    const p = spawnSync(python, args, {
      cwd: resolve(root, "backend"),
      env,
      windowsHide: true,
      encoding: "utf8",
    });
    assert.equal(p.status, 0, p.stdout + p.stderr);
  }
  start(
    python,
    [
      "-m",
      "uvicorn",
      "tests.tooling.e2e_app:create_app",
      "--factory",
      "--host",
      "127.0.0.1",
      "--port",
      backendPort,
    ],
    resolve(root, "backend"),
  );
  if (!localDeployment)
    start(
      process.execPath,
      [
        "node_modules/vite/bin/vite.js",
        "--host",
        "127.0.0.1",
        "--port",
        "5173",
        "--strictPort",
      ],
      resolve(root, "frontend"),
    );
  await ready(backendOrigin + "/api/health");
  await ready(origin);
  browser = await chromium.launch({
    headless: true,
    ...(process.env.BROWSER_EXECUTABLE
      ? { executablePath: process.env.BROWSER_EXECUTABLE }
      : { channel: "chrome" }),
  });
  context = await browser.newContext();
  context.setDefaultTimeout(15000);
  await context.tracing.start({ screenshots: true, snapshots: true });
  page = await context.newPage();
  page.on("pageerror", (e) => failures.push(String(e)));
  await page.goto(origin);
  await page.getByLabel("账号").fill("e2e-user");
  await page.getByLabel("密码").fill("e2e-test-password");
  await page.getByRole("button", { name: /登\s*录/ }).click();
  await page.getByLabel("训练日历", { exact: true }).waitFor();

  // A proposal card renders, but nothing is written before the button.
  await send("端到端记录");
  await page.getByText(/60 kg × 8 次/).first().waitFor();
  assert.equal(await page.locator('[data-action-status="pending"]').count(), 1);
  assert.equal((await workouts()).total, 0);

  // A new message supersedes the old card and proposes the corrected content.
  await send("第一组改9次");
  await page.getByText(/60 kg × 9 次/).first().waitFor();
  await page
    .locator('[data-action-status="superseded"]')
    .first()
    .waitFor();
  assert.equal((await workouts()).total, 0);

  // History restore shows each card once with server-side statuses.
  await page.reload();
  await reopenConversation();
  await page.getByText(/60 kg × 9 次/).first().waitFor();
  assert.equal(await page.locator('[data-action-status="pending"]').count(), 1);
  assert.equal(
    await page.locator('[data-action-status="superseded"]').count(),
    1,
  );

  // Confirm executes exactly one write.
  await confirmPending();
  await page
    .locator('[data-action-status="confirmed"]')
    .first()
    .waitFor();
  await waitForTotal(1);
  const records = await workouts();
  assert.equal(records.items[0].content.exercises[0].sets[0].reps, 9);
  const csrf = (await (await page.request.get(origin + "/api/auth/me")).json()).csrf_token;
  const savedCard = (await snapshot()).actions.find((a) => a.status === "confirmed");
  const replay = await page.request.post(origin + `/api/conversation-actions/${savedCard.action_id}/confirm`, {
    data: { version: 1 }, headers: { "X-CSRF-Token": csrf, "X-Request-ID": "e2e-confirm-replay" },
  });
  assert.equal(replay.status(), 200, await replay.text());
  assert.equal((await replay.json()).status, "confirmed");
  assert.equal((await workouts()).total, 1, "repeated confirmation must not duplicate the record");
  console.log("PASS: zero writes before confirmation, correction supersedes, history restore, create once");

  // Real read tool results return to the model, then become visible text.
  await send("查询训练");
  await page.getByText("查询完成：共 1 条训练。", { exact: true }).waitFor();
  const queried = await snapshot();
  assert.equal(queried.messages.filter((m) => m.role === "tool").length > 0, true);
  assert.equal(await pendingCard().count(), 0);
  assert.equal(await page.locator('.message-bubble.tool').count(), 0);
  assert.equal(await page.locator('.message-bubble.assistant').filter({ hasText: /^\s*$/ }).count(), 0);

  // Cancel a create, with no side effect; a plain query also supersedes a card.
  await send("取消新增测试");
  const cancelledId = await pendingCard().getAttribute("data-action-id");
  await pendingCard().getByRole("button", { name: "取消新增训练", exact: true }).click();
  await page.locator(`[data-action-id="${cancelledId}"][data-action-status="cancelled"]`).waitFor();
  assert.equal((await workouts()).total, 1);
  await send("取消新增测试");
  const supersededId = await pendingCard().getAttribute("data-action-id");
  await send("查询训练");
  await page.locator(`[data-action-id="${supersededId}"][data-action-status="superseded"]`).waitFor();
  assert.equal(await pendingCard().count(), 0);
  console.log("PASS: query feedback, hidden tool messages, cancellation, query supersedes old card");

  // Successful update retains the workout and stable exercise/set IDs.
  const beforeUpdate = (await workouts()).items[0];
  await send("修改为10次");
  await expect(pendingCard("update_workout")).toHaveCount(1);
  await pendingCard().getByText("修改前", { exact: false }).waitFor();
  await pendingCard().getByText("修改后", { exact: false }).waitFor();
  assert.equal((await workouts()).items[0].version, beforeUpdate.version);
  await confirmPending();
  await expect(pendingCard()).toHaveCount(0);
  const afterUpdate = (await workouts()).items[0];
  assert.equal(afterUpdate.id, beforeUpdate.id);
  assert.equal(afterUpdate.version, beforeUpdate.version + 1);
  assert.equal(afterUpdate.content.exercises[0].id, beforeUpdate.content.exercises[0].id);
  assert.equal(afterUpdate.content.exercises[0].sets[0].id, beforeUpdate.content.exercises[0].sets[0].id);
  assert.equal(afterUpdate.content.exercises[0].sets[0].reps, 10);
  console.log("PASS: multi-tool update, before/after comparison, stable IDs");

  // A stale card (record changed underneath) confirms to a conflict, not a write.
  await send("再记录一次");
  await page.getByText(/60 kg × 10 次/).first().waitFor();
  const current = (await workouts()).items[0];
  const changed = JSON.parse(JSON.stringify(current.content));
  // The list view carries read-only fields (name_snapshot) that the write
  // schema does not accept.
  changed.exercises = changed.exercises.map(
    ({ name_snapshot, ...rest }) => rest,
  );
  changed.exercises[0].sets[0].reps = 99;
  const bumped = await page.request.put(
    origin + "/api/workouts/" + current.id,
    {
      data: { version: current.version, content: changed },
      headers: { "X-CSRF-Token": csrf, "X-Request-ID": "e2e-conflict-setup" },
    },
  );
  assert.equal(bumped.status(), 200, await bumped.text());
  await confirmPending();
  await page
    .locator('[data-action-status="conflict"]')
    .first()
    .waitFor();
  await page.getByText("数据已变化").first().waitFor();
  assert.equal((await workouts()).total, 1);
  assert.equal((await workouts()).items[0].content.exercises[0].sets[0].reps, 99);
  console.log("PASS: stale confirmation returns conflict without overwriting");

  // Deletion goes through its own card.
  await send("删除这条记录");
  await pendingCard("delete_workout").getByRole("button", { name: "取消删除训练", exact: true }).click();
  await expect(pendingCard()).toHaveCount(0);
  assert.equal((await workouts()).total, 1);
  await send("删除这条记录");
  await page
    .locator('[data-action-status="pending"][data-operation="delete_workout"]')
    .first()
    .waitFor();
  await confirmPending();
  await waitForTotal(0);
  assert.equal((await page.request.get(origin + "/api/workouts/" + current.id)).status(), 404);
  console.log("PASS: delete cancellation preserves data, confirmed delete hides record");

  // Ask for missing information; skipping fields still requires a button.
  await send("信息不全");
  await page.getByText("卧推的重量和次数是多少？也可以明确留空。", { exact: true }).waitFor();
  assert.equal(await pendingCard().count(), 0);
  await send("直接写入，重量次数留空");
  await expect(pendingCard("create_workout")).toHaveCount(1);
  assert.equal((await workouts()).total, 0);
  await confirmPending();
  await waitForTotal(1);
  const unknown = (await workouts()).items[0].content.exercises[0].sets[0];
  assert.equal(unknown.weight_kg, null);
  assert.equal(unknown.reps, null);

  // Custom exercise creation is also delayed until confirmation.
  const catalog = async () => {
    const items = [];
    while (true) {
      const response = await page.request.get(origin + `/api/exercises?limit=200&offset=${items.length}`);
      assert.equal(response.status(), 200);
      const batch = await response.json();
      items.push(...batch.items);
      if (items.length >= batch.total) return items;
      assert.ok(batch.items.length, "catalog pagination must make progress");
    }
  };
  await send("自定义动作记录");
  await pendingCard().getByText("确认后将创建自定义动作：端到端自定义划船", { exact: true }).waitFor();
  assert.equal((await catalog()).filter((e) => e.name === "端到端自定义划船").length, 0);
  await confirmPending();
  await waitForTotal(2);
  assert.equal((await catalog()).filter((e) => e.name === "端到端自定义划船").length, 1);
  console.log("PASS: missing-field follow-up, explicit skip, custom creation after confirmation");

  // Other write tools use the same UI confirmation contract.
  for (const [command, operation] of [["更新个人条件", "update_profile"],
    ["更新动作偏好", "update_preferences"], ["新增器械", "add_equipment"]]) {
    await send(command);
    await expect(pendingCard(operation)).toHaveCount(1);
    const turnsBefore = (await snapshot()).turns.length;
    await confirmPending();
    await expect(pendingCard()).toHaveCount(0);
    assert.equal((await snapshot()).turns.length, turnsBefore, "button must not create another model turn");
  }
  assert.equal((await (await page.request.get(origin + "/api/profile")).json()).goal, "端到端增肌目标");
  assert.equal((await catalog()).find((e) => e.id === "bench-press").available, true);
  const equipment = await (await page.request.get(origin + "/api/user-equipment")).json();
  assert.equal(equipment.items.filter((e) => e.name === "端到端弹力带").length, 1);
  console.log("PASS: profile, preferences, equipment use unified confirmation");

  await send("故障后重试");
  await page.getByRole("button", { name: "重试本轮", exact: true }).waitFor();
  await page.getByRole("button", { name: "重试本轮", exact: true }).click();
  await page.getByText("重试成功，原输入未重复保存。", { exact: true }).waitFor();
  const recovered = await snapshot();
  assert.equal(recovered.messages.filter((m) => m.role === "user" && m.content === "故障后重试").length, 1);
  assert.equal(recovered.turns.filter((t) => t.status === "failed").length, 0);
  console.log("PASS: explicit retry preserves one user input");

  // All cards end terminal after a reload; nothing is clickable anymore.
  await page.reload();
  await page.getByLabel("训练日历", { exact: true }).waitFor();
  await reopenConversation();
  assert.equal(await page.locator('[data-action-status="pending"]').count(), 0);
  assert.equal(await page.getByRole("button", { name: /^确认执行/ }).count(), 0);
  assert.deepEqual(failures, []);
  console.log(
    "PASS: proposal card → supersede → history restore → confirm once → conflict on stale card → card-based delete",
  );
} catch (error) {
  if (page) await page.screenshot({ path: resolve(temp, "failure.png"), fullPage: true }).catch(() => {});
  console.error("E2E artifacts:", temp);
  if (page) console.error(await page.locator("body").innerText());
  if (page) console.error(await page.locator("main").ariaSnapshot());
  console.error("Page errors:", failures, "Server logs:", logs.join(""));
  throw error;
} finally {
  if (context) await context.tracing.stop({ path: resolve(temp, "trace.zip") }).catch(() => {});
  if (browser) await browser.close();
  for (const child of children) child.kill();
}
