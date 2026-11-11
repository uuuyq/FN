import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "../../frontend/node_modules/typescript/lib/typescript.js";
const compile = async (name) =>
  ts.transpileModule(
    await readFile(
      new URL(`../../frontend/src/${name}.ts`, import.meta.url),
      "utf8",
    ),
    {
      compilerOptions: {
        target: ts.ScriptTarget.ES2022,
        module: ts.ModuleKind.ESNext,
      },
    },
  ).outputText;
const url = (source) =>
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
const errorsUrl = url(await compile("errors"));
const { api, ApiError, conversationStream, getErrorMessage } = await import(
  url(
    (await compile("api")).replaceAll('"./errors"', JSON.stringify(errorsUrl)),
  )
);
const originalFetch = globalThis.fetch;
const mock = (fn) => {
  globalThis.fetch = fn;
};
test("request error handling", async (t) => {
  t.after(() => {
    globalThis.fetch = originalFetch;
  });
  await t.test("network failure is normalized", async () => {
    mock(async () => {
      throw new TypeError("Failed to fetch");
    });
    await assert.rejects(
      api("/test"),
      (e) =>
        e instanceof ApiError &&
        e.status === 0 &&
        e.message === "未知异常，请稍后重试。",
    );
  });
  await t.test("HTML gateway failure preserves HTTP status", async () => {
    mock(
      async () => new Response("<html>gateway error</html>", { status: 503 }),
    );
    await assert.rejects(
      api("/test"),
      (e) => e.status === 503 && !e.message.includes("html"),
    );
  });
  await t.test(
    "conflicts preserve structured detail and request ID",
    async () => {
      mock(async () =>
        Response.json(
          { detail: { code: "version_conflict", latest_version: 9 } },
          { status: 409, headers: { "X-Request-ID": "trace-id" } },
        ),
      );
      await assert.rejects(
        api("/test"),
        (e) =>
          e.status === 409 &&
          e.detail.latest_version === 9 &&
          e.requestId === "trace-id",
      );
    },
  );
  await t.test("validation does not expose submitted secrets", async () => {
    mock(async () =>
      Response.json(
        { detail: [{ input: "secret-password", msg: "invalid" }] },
        { status: 422 },
      ),
    );
    await assert.rejects(
      api("/test"),
      (e) =>
        e.message === "未知异常，请稍后重试。" && !e.message.includes("secret"),
    );
  });
  await t.test("empty success and malformed success", async () => {
    mock(async () => new Response(null, { status: 204 }));
    assert.equal(await api("/test"), undefined);
    mock(async () => new Response("bad json"));
    await assert.rejects(api("/test"), (e) => e.status === 502);
  });
  await t.test("stream HTTP errors use the same mapping", async () => {
    mock(async () =>
      Response.json(
        {
          detail: {
            code: "invalid_credentials",
            message: "账号或密码不正确，请重新输入。",
          },
        },
        { status: 401 },
      ),
    );
    await assert.rejects(
      conversationStream("/test", "GET", null, "request-id", () => {}),
      (e) => e.message.includes("账号或密码"),
    );
  });
  await t.test("interrupted stream instructs recovery", async () => {
    mock(
      async () =>
        new Response(
          new ReadableStream({
            start(c) {
              c.error(new Error("socket"));
            },
          }),
        ),
    );
    await assert.rejects(
      conversationStream("/test", "GET", null, "request-id", () => {}),
      /未知异常/,
    );
  });
  assert.equal(getErrorMessage(new Error("请先选择任务")), "请先选择任务");
  assert.equal(getErrorMessage({}), "未知异常，请稍后重试。");
  assert.equal(
    new ApiError(422, { code: "new_code", message: "后端新增的提示" }).message,
    "后端新增的提示",
  );
});
