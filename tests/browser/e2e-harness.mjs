// Shared isolated server/browser lifecycle for the extended acceptance suite.
import { chromium, expect } from "./playwright.mjs";
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { resolve, delimiter } from "node:path";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";

export { expect, assert };
export async function runE2E(name, execute) {
  const root = fileURLToPath(new URL("../../", import.meta.url));
  mkdirSync(resolve(root, "runtime"), { recursive: true });
  const artifacts = mkdtempSync(resolve(root, `runtime/${name}-`));
  const port = await new Promise((accept, reject) => {
    const probe = createServer();
    probe.once("error", reject);
    probe.listen(0, "127.0.0.1", () => {
      const chosen = probe.address().port;
      probe.close(() => accept(chosen));
    });
  });
  const origin = `http://127.0.0.1:${port}`;
  const python = process.env.PYTHON || resolve(root, "backend/.venv/Scripts/python.exe");
  const env = { ...process.env, COOKIE_SECURE: "false", APP_ORIGIN: origin,
    PYTHONPATH: root + (process.env.PYTHONPATH ? delimiter + process.env.PYTHONPATH : ""),
    FRONTEND_DIST: resolve(root, "frontend/dist"),
    DATABASE_URL: "sqlite:///" + resolve(artifacts, "test.db").replaceAll("\\", "/") };
  let child, browser;
  const logs = [], contexts = [];
  let passed = 0;
  const failed = [];
  try {
    for (const args of [["-m", "alembic", "upgrade", "head"], ["-m", "tests.tooling.e2e_setup"]]) {
      const result = spawnSync(python, args, { cwd: resolve(root, "backend"), env,
        windowsHide: true, encoding: "utf8" });
      assert.equal(result.status, 0, result.stdout + result.stderr);
    }
    child = spawn(python, ["-m", "uvicorn", "tests.tooling.e2e_app:create_app", "--factory",
      "--host", "127.0.0.1", "--port", String(port)], {
      cwd: resolve(root, "backend"), env, windowsHide: true, stdio: ["ignore", "pipe", "pipe"],
    });
    child.on("error", (error) => logs.push(String(error)));
    child.stdout.on("data", (data) => logs.push(String(data)));
    child.stderr.on("data", (data) => logs.push(String(data)));
    let ready = false;
    for (let i = 0; i < 100; i++) {
      if (child.exitCode !== null) throw Error(logs.join(""));
      try { ready = (await fetch(origin + "/api/health")).ok; } catch {}
      if (ready) break;
      await new Promise((r) => setTimeout(r, 200));
    }
    assert.ok(ready, "E2E server failed to start");
    browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_EXECUTABLE
      ? { executablePath: process.env.BROWSER_EXECUTABLE } : { channel: "chrome" }) });
    const login = async (username = "e2e-user") => {
      const context = await browser.newContext();
      contexts.push(context);
      context.setDefaultTimeout(15000);
      await context.tracing.start({ screenshots: true, snapshots: true });
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(String(e)));
      await page.goto(origin);
      await page.getByLabel("账号").fill(username);
      await page.getByLabel("密码").fill("e2e-test-password");
      await page.getByRole("button", { name: /登\s*录/ }).click();
      await page.getByLabel("训练日历", { exact: true }).waitFor();
      return { context, page, errors };
    };
    const scenario = async (title, fn) => {
      try {
        await fn();
        passed++;
        console.log(`PASS: ${title}`);
      } catch (error) {
        failed.push({ title, error });
        console.error(`FAIL: ${title}\n${error.message}`);
        for (const [i, context] of contexts.entries()) {
          for (const [j, page] of context.pages().entries()) {
            const prefix = `scenario-${failed.length}-${i}-${j}`;
            await page.screenshot({ path: resolve(artifacts, `${prefix}.png`), fullPage: true }).catch(() => {});
            writeFileSync(resolve(artifacts, `${prefix}.txt`), await page.locator("body").innerText().catch(() => ""));
          }
        }
      }
    };
    await execute({ origin, login, scenario });
    console.log(`${name}: ${passed} passed, ${failed.length} failed`);
    if (failed.length) throw new AggregateError(failed.map((f) => f.error),
      failed.map((f) => f.title).join("\n"));
  } catch (error) {
    for (const [i, context] of contexts.entries()) {
      for (const [j, page] of context.pages().entries()) {
        await page.screenshot({ path: resolve(artifacts, `failure-${i}-${j}.png`), fullPage: true }).catch(() => {});
        writeFileSync(resolve(artifacts, `page-${i}-${j}.txt`), await page.locator("body").innerText().catch(() => ""));
      }
    }
    console.error(`Failed after ${passed} scenarios. Artifacts: ${artifacts}`);
    throw error;
  } finally {
    writeFileSync(resolve(artifacts, "server.log"), logs.join(""));
    for (const [i, context] of contexts.entries())
      await context.tracing.stop({ path: resolve(artifacts, `trace-${i}.zip`) }).catch(() => {});
    if (browser) await browser.close();
    if (child && child.exitCode === null) {
      const stopped = new Promise((accept) => child.once("exit", accept));
      child.kill();
      await Promise.race([stopped, new Promise((accept) => setTimeout(accept, 3000))]);
    }
  }
}
