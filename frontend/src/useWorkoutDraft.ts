import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, clean, type Content, type Draft } from "./api";

const withIds = (value: Content): Content => ({
  ...value,
  exercises: value.exercises.map((item) => ({
    ...item,
    id: item.id || crypto.randomUUID(),
    sets: item.sets.map((group) => ({
      ...group,
      id: group.id || crypto.randomUUID(),
    })),
  })),
});
type Pending = {
  path: string;
  method: string;
  body: unknown;
  requestId: string;
  revision: number;
};

// One in-flight request per draft; subsequent edits coalesce into the latest snapshot.
export function useSavedDraft<
  C,
  D extends { id: string; version: number; status: string; content: C },
>(
  owner: string | undefined,
  initial: () => C,
  config: {
    path: string;
    storage: string;
    withIds: (c: C) => C;
    clean: (c: C) => C;
  },
) {
  const { withIds, clean } = config;
  const state = useRef({
    owner,
    content: initial(),
    draft: null as D | null,
    revision: 0,
    saved: 0,
    error: null as Error | null,
    pending: null as Pending | null,
    running: null as Promise<D | null> | null,
    timer: undefined as ReturnType<typeof setTimeout> | undefined,
    restoring: false,
  });
  const [, render] = useState(0);
  const notify = useCallback(() => render((n) => n + 1), []);
  const key = (id: string) => config.storage + id;
  const flush = useCallback(async (): Promise<D | null> => {
    const s = state.current;
    clearTimeout(s.timer);
    if (s.running) return s.running;
    if (s.restoring) throw Error("正在恢复草稿，请稍候");
    // A failed initial load must be retried before creating a replacement draft.
    if (s.error && !s.draft && s.owner && localStorage.getItem(key(s.owner))) {
      const restored = await api<D>(
        config.path + "/" + localStorage.getItem(key(s.owner)),
      );
      if (restored.status !== "editable")
        throw Error("草稿已结束，请查看已保存记录");
      if (s.revision === 0) s.content = withIds(restored.content);
      s.draft = restored;
    }
    if (s.error instanceof ApiError && s.error.status === 409) throw s.error;
    s.error = null;
    s.running = (async () => {
      while (s.saved < s.revision || s.pending) {
        if (!s.pending) {
          s.pending = {
            path: s.draft ? `${config.path}/${s.draft.id}` : config.path,
            method: s.draft ? "PUT" : "POST",
            body: s.draft
              ? { version: s.draft.version, content: clean(s.content) }
              : { content: clean(s.content) },
            requestId: crypto.randomUUID(),
            revision: s.revision,
          };
        }
        const pending = s.pending;
        try {
          const result = await api<D>(
            pending.path,
            pending.method,
            pending.body,
            pending.requestId,
          );
          if (state.current !== s) return null;
          s.draft = result;
          s.saved = pending.revision;
          s.pending = null;
          // Never replace the local buffer with an earlier response.
          if (s.owner) localStorage.setItem(key(s.owner), result.id);
          notify();
        } catch (error) {
          s.error = error instanceof Error ? error : Error(String(error));
          // Definite validation failures may be corrected locally. Uncertain network
          // outcomes retain the exact request ID/body for safe replay on retry.
          if (
            error instanceof ApiError &&
            error.status >= 400 &&
            error.status < 500
          )
            s.pending = null;
          throw s.error;
        }
      }
      return s.draft;
    })();
    notify();
    try {
      return await s.running;
    } finally {
      s.running = null;
      notify();
    }
  }, [notify]);
  const setContent = useCallback(
    (change: C | ((previous: C) => C)) => {
      const s = state.current;
      if (s.restoring) return;
      if (s.error && !s.draft && s.owner && localStorage.getItem(key(s.owner)))
        return;
      s.content = withIds(
        typeof change === "function"
          ? (change as (previous: C) => C)(s.content)
          : change,
      );
      s.revision++;
      clearTimeout(s.timer);
      if (!s.error || (s.error instanceof ApiError && s.error.status === 422)) {
        s.timer = setTimeout(() => {
          void flush().catch(() => {});
        }, 400);
      }
      notify();
    },
    [flush, notify],
  );
  const replace = useCallback(
    (draft: D | null, content?: C) => {
      const s = state.current;
      if (s.running) throw Error("请先等待保存完成");
      clearTimeout(s.timer);
      s.draft = draft;
      s.content = withIds(content || draft?.content || initial());
      s.revision = 0;
      s.saved = 0;
      s.error = null;
      s.pending = null;
      if (s.owner) {
        if (draft) localStorage.setItem(key(s.owner), draft.id);
        else localStorage.removeItem(key(s.owner));
      }
      notify();
    },
    [notify],
  );
  useEffect(() => {
    const previous = state.current;
    clearTimeout(previous.timer);
    const s: typeof previous = {
      ...previous,
      owner,
      content: initial(),
      draft: null,
      revision: 0,
      saved: 0,
      error: null,
      pending: null,
      running: null,
      timer: undefined,
      restoring: !!owner,
    };
    state.current = s;
    notify();
    if (!owner) return;
    const id = localStorage.getItem(key(owner));
    (async () => {
      try {
        if (id) {
          const d = await api<D>(config.path + "/" + id);
          if (state.current !== s) return;
          if (d.status === "editable") {
            s.draft = d;
            s.content = withIds(d.content);
          } else localStorage.removeItem(key(owner));
        }
      } catch (error) {
        if (state.current === s) s.error = error as Error;
      } finally {
        if (state.current === s) {
          s.restoring = false;
          notify();
        }
      }
    })();
    return () => clearTimeout(s.timer);
  }, [owner, notify]);
  useEffect(() => {
    const leave = (event: BeforeUnloadEvent) => {
      const s = state.current;
      if (s.saved < s.revision || s.pending || s.running) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", leave);
    return () => window.removeEventListener("beforeunload", leave);
  }, []);
  const s = state.current;
  return {
    draft: s.draft,
    content: s.content,
    setContent,
    replace,
    flush,
    settle: async () => {
      const current = state.current;
      clearTimeout(current.timer);
      if (current.running) await current.running.catch(() => {});
      if (current.pending) await flush();
      return current.draft;
    },
    restoring: s.restoring,
    dirty: s.saved < s.revision || !!s.pending,
    saving: !!s.running,
    saveError: s.error,
  };
}

export function useWorkoutDraft(
  owner: string | undefined,
  initial: () => Content,
) {
  return useSavedDraft<Content, Draft>(owner, initial, {
    path: "/workout-drafts",
    storage: "fitplan-draft-",
    withIds,
    clean,
  });
}
