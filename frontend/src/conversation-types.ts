// Types and pure helpers for the agent conversation API. No React imports:
// this module is also unit-tested through tests/unit/conversation-model.test.mjs.

export type ToolCall = {
  id: string;
  type: string;
  function: { name: string; arguments: string };
};

export type Message = {
  id: string;
  turn_id: string;
  role: "user" | "assistant" | "tool" | "event";
  content: string | null;
  tool_calls: ToolCall[] | null;
  tool_call_id: string | null;
  sequence: number;
  event_kind: string | null;
  event_data: Record<string, unknown> | null;
  created_at: string;
};

export type ActionError = { code: string; message: string };

export type TurnResult = {
  type?: "reply" | "confirmation_required";
  action_id?: string;
  operation?: string;
  status?: string;
  version?: number;
  summary?: string;
  details?: unknown;
  allowed_operations?: string[];
};

export type Turn = {
  id: string;
  conversation_id: string;
  status: "running" | "succeeded" | "failed" | "conflict" | "interrupted";
  error: string | null;
  error_message: string | null;
  result: TurnResult | null;
  mode: "edit" | "read";
  created_at: string;
};

export type ActionStatus =
  | "pending"
  | "confirmed"
  | "cancelled"
  | "superseded"
  | "conflict"
  | "failed";

export type Action = {
  action_id: string;
  operation: string;
  tool_name: string;
  status: ActionStatus | string;
  version: number;
  summary: string | null;
  details: any;
  result: { error?: ActionError; [key: string]: unknown } | null;
  created_at: string;
  completed_at: string | null;
  allowed_operations: string[];
};

export type Snapshot = {
  id: string;
  title: string;
  messages: Message[];
  turns: Turn[];
  actions: Action[];
};

export const operationNames: Record<string, string> = {
  undo_operation: "撤销操作",
  create_workout: "新增训练",
  update_workout: "修改训练",
  delete_workout: "删除训练",
  update_profile: "修改个人条件",
  update_preferences: "修改动作偏好",
  add_equipment: "新增器械",
  add_exercise: "新增动作",
};

export const statusNames: Record<string, string> = {
  pending: "待确认",
  confirmed: "已执行",
  cancelled: "已取消",
  superseded: "已失效",
  conflict: "数据已变化",
  failed: "执行失败",
};

export function operationName(operation: string | undefined): string {
  return (operation && operationNames[operation]) || "操作";
}

export function statusName(status: string | undefined): string {
  return (status && statusNames[status]) || "未知状态";
}

/** Actions are immutable rows; the last row per action_id is the current state. */
export function latestActions(actions: Action[]): Map<string, Action> {
  const byId = new Map<string, Action>();
  for (const action of actions) byId.set(action.action_id, action);
  return byId;
}

export const ACTION_TERMINAL: string[] = [
  "confirmed",
  "cancelled",
  "superseded",
  "conflict",
  "failed",
];

export function actionDecided(action: Action): boolean {
  return ACTION_TERMINAL.includes(action.status);
}

/**
 * Card for one turn: the turn result only holds the action_id snapshot; the
 * current state always comes from the latest matching action row.
 */
export function cardForTurn(
  turn: Turn,
  actions: Action[],
): Action | null {
  if (turn.result?.type !== "confirmation_required" || !turn.result.action_id)
    return null;
  return latestActions(actions).get(turn.result.action_id) ?? null;
}

export type TimelineItem =
  | { kind: "message"; message: Message }
  | { kind: "card"; action: Action };

function displayed(message: Message): boolean {
  if (message.role === "event") return !!message.content;
  if (message.role === "user") return true;
  // Assistant text shows as chat; tool-call-only assistant rows and tool
  // results stay internal and must not render empty bubbles or raw JSON.
  if (message.role === "assistant") return !!message.content;
  return false;
}

/**
 * Ordered display items: user/assistant text, server events, and exactly one
 * card per confirmation turn, rendered after the last message of that turn.
 */
export function buildTimeline(snapshot: Snapshot): TimelineItem[] {
  const cardsByTurn = new Map<string, Action>();
  for (const turn of snapshot.turns) {
    const action = cardForTurn(turn, snapshot.actions);
    if (action) cardsByTurn.set(turn.id, action);
  }
  const items: TimelineItem[] = [];
  const rendered = new Set<string>();
  const flush = (turnId: string | null | undefined) => {
    if (!turnId) return;
    const action = cardsByTurn.get(turnId);
    if (action && !rendered.has(action.action_id)) {
      rendered.add(action.action_id);
      items.push({ kind: "card", action });
    }
  };
  snapshot.messages.forEach((message, index) => {
    if (displayed(message)) items.push({ kind: "message", message });
    const next = snapshot.messages[index + 1];
    if (!next || next.turn_id !== message.turn_id) flush(message.turn_id);
  });
  // Turns whose messages are missing still show their card once.
  for (const action of cardsByTurn.values())
    if (!rendered.has(action.action_id)) items.push({ kind: "card", action });
  return items;
}

/**
 * Only failed/interrupted turns whose user message is still the last one may
 * be retried. Context overflow requires a new conversation instead.
 * The backend re-validates and returns turn_not_retryable.
 */
export function canRetry(turn: Turn, snapshot: Snapshot): boolean {
  if (turn.status !== "failed" && turn.status !== "interrupted") return false;
  if (turn.error === "context_too_large") return false;
  const lastUser = [...snapshot.messages]
    .reverse()
    .find((message) => message.role === "user");
  const outcome = snapshot.messages.find(
    (message) => message.turn_id === turn.id && message.event_kind === "action_result",
  );
  if (outcome) return !lastUser || lastUser.sequence < outcome.sequence;
  return !!lastUser && lastUser.turn_id === turn.id;
}
