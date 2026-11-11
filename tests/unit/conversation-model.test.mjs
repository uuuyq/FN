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
const {
  buildTimeline,
  canRetry,
  cardForTurn,
  latestActions,
  actionDecided,
  statusName,
  operationName,
} = await import(url(await compile("conversation-types")));

let sequence = 0;
const message = (role, turnId, content = null, extra = {}) => ({
  id: "m" + ++sequence,
  turn_id: turnId,
  role,
  content,
  tool_calls: null,
  tool_call_id: null,
  sequence: sequence,
  event_kind: null,
  event_data: null,
  created_at: "2026-01-01T00:00:00",
  ...extra,
});
const turn = (id, status, result = null, mode = "edit") => ({
  id,
  conversation_id: "c1",
  status,
  error: null,
  error_message: null,
  result,
  mode,
  created_at: "2026-01-01T00:00:00",
});
const action = (id, status, version = 1, extra = {}) => ({
  action_id: id,
  operation: "create_workout",
  tool_name: "save_workout",
  status,
  version,
  summary: "新增训练记录",
  details: { content: { actual_date: "2026-01-02", exercises: [] } },
  result: null,
  created_at: "2026-01-01T00:00:00",
  completed_at: null,
  allowed_operations: status === "pending" ? ["confirm", "cancel"] : [],
  ...extra,
});

test("conversation timeline and retry eligibility", async (t) => {
  await t.test("cards attach to their turn once, internal messages stay hidden", () => {
    const snapshot = {
      id: "c1",
      title: "对话",
      messages: [
        message("user", "t1", "记录卧推"),
        // Tool-call-only assistant row and tool result must not render.
        message("assistant", "t1", null, {
          tool_calls: [{ id: "x", type: "function", function: { name: "save_workout", arguments: "{}" } }],
        }),
        message("tool", "t1", '{"ok": true}'),
        message("user", "t2", "改成9次"),
        message("assistant", "t2", "好的"),
        message("event", "t2", "此前的待确认操作已因新消息失效，如仍需要请重新发起。"),
      ],
      turns: [
        turn("t1", "succeeded", { type: "confirmation_required", action_id: "a1" }),
        turn("t2", "succeeded", { type: "confirmation_required", action_id: "a2" }),
      ],
      actions: [
        action("a1", "superseded"),
        action("a2", "pending", 2),
      ],
    };
    const items = buildTimeline(snapshot);
    const kinds = items.map((item) => item.kind);
    // Hidden rows are skipped; the t1 card renders after t1's last message
    // and before t2's user text.
    assert.deepEqual(
      kinds,
      ["message", "card", "message", "message", "message", "card"],
    );
    // Card for t1 renders right after t1's last message, before t2's user text.
    assert.equal(items[1].action.action_id, "a1");
    assert.equal(items[1].action.status, "superseded");
    assert.equal(items[5].action.action_id, "a2");
    // No empty bubble and no raw tool JSON anywhere.
    const texts = items
      .filter((item) => item.kind === "message")
      .map((item) => item.message.content);
    assert.ok(!texts.some((text) => text === null || text.includes('"ok"')));
  });

  await t.test("the latest action row wins for the same action_id", () => {
    const actions = [action("a1", "pending", 1), action("a1", "confirmed", 2)];
    assert.equal(latestActions(actions).get("a1").status, "confirmed");
    const snapshot = {
      id: "c1",
      title: "对话",
      messages: [message("user", "t1", "记录")],
      turns: [turn("t1", "succeeded", { type: "confirmation_required", action_id: "a1" })],
      actions,
    };
    const items = buildTimeline(snapshot);
    assert.equal(items.length, 2);
    assert.equal(items[1].action.status, "confirmed");
    assert.ok(actionDecided(items[1].action));
  });

  await t.test("only the last user turn may retry a failed run", () => {
    const snapshot = {
      id: "c1",
      title: "对话",
      messages: [
        message("user", "t1", "第一句"),
        message("user", "t2", "第二句"),
      ],
      turns: [turn("t1", "failed"), turn("t2", "failed", null, "read")],
      actions: [],
    };
    assert.equal(canRetry(snapshot.turns[0], snapshot), false);
    const retryable = canRetry(snapshot.turns[1], snapshot);
    assert.equal(retryable, true);
    assert.equal(snapshot.turns[1].mode, "read");
    assert.equal(canRetry(turn("t3", "succeeded"), snapshot), false);
    assert.equal(canRetry(turn("t3", "interrupted"), snapshot), false
    );
  });

  await t.test("context overflow cannot retry, while timeout can", () => {
    const current = turn("t1", "failed");
    const snapshot = { id: "c1", title: "对话", messages: [message("user", "t1", "记录")],
      turns: [current], actions: [] };
    for (const status of ["failed", "interrupted"]) {
      current.status = status;
      current.error = "context_too_large";
      assert.equal(canRetry(current, snapshot), false);
      current.error = "model_timeout";
      assert.equal(canRetry(current, snapshot), true);
    }
  });

  await t.test("labels keep unknown values visible", () => {
    assert.equal(operationName("delete_workout"), "删除训练");
    assert.equal(operationName("future_operation"), "future_operation");
    assert.equal(statusName("conflict"), "数据已变化");
    assert.equal(statusName("mystery"), "mystery");
    assert.equal(statusName(undefined), "未知状态");
  });

  await t.test("cardForTurn needs a confirmation result", () => {
    const actions = [action("a1", "pending")];
    assert.equal(cardForTurn(turn("t1", "succeeded", { type: "reply" }), actions), null);
    assert.equal(cardForTurn(turn("t1", "succeeded", { type: "confirmation_required" }), actions), null);
    assert.equal(
      cardForTurn(turn("t1", "succeeded", { type: "confirmation_required", action_id: "a1" }), actions)
        .action_id,
      "a1",
    );
  });
});
