export type Group = {
  id?: string;
  kind: "working" | "warmup";
  weight_kg: string | null;
  reps: number | null;
  notes: string;
};
export type Entry = {
  exercise_id?: string | null;
  custom_name?: string | null;
  confirm_create?: boolean;
  training_parts?: string[];
  name?: string;
  sets: Group[];
};
export type Content = {
  actual_date: string;
  actual_time: string | null;
  notes: string;
  exercises: Entry[];
  missing_information: Record<string, string>;
};
export type Workout = {
  id: string;
  version: number;
  deleted_at: string | null;
  content: Content;
};
export type Exercise = {
  id: string;
  name: string;
  aliases: string;
  training_parts: string[];
  primary_muscles: string;
  secondary_muscles: string;
  equipment: string;
  category: string | null;
  owner_id: string | null;
  active: boolean;
  description: string;
  preference_version: number;
  version: number;
};
let csrf = "";
import { ApiError } from "./errors";
export { ApiError, getErrorMessage } from "./errors";
async function request(path: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch("/api" + path, init);
  } catch {
    throw new ApiError(0, { code: "network_error" });
  }
  if (!response.ok) {
    let data: any;
    try {
      data = await response.json();
    } catch {
      /* Non-JSON proxy error. */
    }
    throw new ApiError(
      response.status,
      data?.detail ?? data,
      response.headers.get("X-Request-ID") ?? undefined,
    );
  }
  return response;
}
export function setCSRF(value: string) {
  csrf = value;
}
export type StreamMessage = { message_id: string; text: string; ended?: boolean };
export type ConversationStreamEvent =
  | { event: "snapshot"; payload: { turn_id: string; sequence: number; messages: StreamMessage[] } }
  | { event: "message_start" | "text_delta" | "message_end"; payload: { turn_id: string; sequence: number; message_id: string; text: string } };
export async function conversationStream(
  path: string,
  method: "GET" | "POST",
  body: unknown,
  requestId: string,
  onAccepted: (id: string) => void,
  onEvent?: (update: ConversationStreamEvent) => void,
  signal?: AbortSignal,
): Promise<any> {
  const response = await request(path, {
    method,
    signal,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
      "X-Request-ID": requestId,
    },
    body: method === "GET" ? undefined : JSON.stringify(body),
  });
  if (!response.body) throw new ApiError(0, undefined);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "",
    result: any = null;
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      buffer = buffer.replaceAll("\r\n", "\n");
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = block
          .split("\n")
          .find((l) => l.startsWith("event:"))
          ?.slice(6)
          .trim();
        const data = block
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).trimStart())
          .join("\n");
        if (!data) continue;
        const parsed = JSON.parse(data);
        if (event === "snapshot" || event === "message_start" || event === "text_delta" || event === "message_end")
          onEvent?.({ event, payload: parsed });
        if (event === "accepted") onAccepted(parsed.turn_id);
        if (event === "completed" || event === "failed") result = parsed;
      }
      if (done) break;
    }
  } catch {
    throw new ApiError(0, undefined);
  } finally {
    reader.releaseLock();
  }
  if (!result) throw new ApiError(0, undefined);
  return result;
}
export async function api<T = any>(
  path: string,
  method = "GET",
  body?: unknown,
  requestId: string = crypto.randomUUID(),
): Promise<T> {
  const response = await request(path, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
      "X-Request-ID": requestId,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204 || response.status === 205) return undefined as T;
  try {
    return await response.json();
  } catch {
    throw new ApiError(502, { code: "invalid_response" });
  }
}
export const blankSet = (): Group => ({
  kind: "working",
  weight_kg: null,
  reps: null,
  notes: "",
});
export const clean = (content: Content): Content => ({
  ...content,
  exercises: content.exercises.map(({ name, ...item }) => item),
});
