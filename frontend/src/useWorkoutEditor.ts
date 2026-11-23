import { useEffect, useRef, useState } from "react";
import { api, ApiError, clean, type Content, type Workout } from "./api";

type Submission = {
  path: string;
  method: string;
  body: unknown;
  requestId: string;
};
type Buffer = {
  content: Content;
  original: Workout | null;
  pending: Submission | null;
};

// Editing is local. Only save() submits a business write.
export function useWorkoutEditor(
  owner: string | undefined,
  initial: () => Content,
) {
  const [buffer, setBuffer] = useState<Buffer>(() => ({
    content: initial(),
    original: null,
    pending: null,
  }));
  const [active, setActive] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<Error | null>(null);
  const current = useRef(buffer);
  const currentOwner = useRef(owner);
  const running = useRef<Promise<Workout> | null>(null);
  const update = (value: Buffer, keep: boolean) => {
    current.current = value;
    setBuffer(value);
    setActive(keep);
    setSaveError(null);
  };
  useEffect(() => {
    currentOwner.current = owner;
    update({ content: initial(), original: null, pending: null }, false);
  }, [owner]);
  const discard = () => {
    if (!running.current)
      update({ content: initial(), original: null, pending: null }, false);
  };
  const replace = (original: Workout | null, content?: Content) => {
    if (running.current) throw Error("请等待保存完成");
    if (current.current.pending)
      throw Error("上次保存结果尚未确定，请先重试保存");
    update(
      {
        original,
        content: content || original?.content || initial(),
        pending: null,
      },
      !!original,
    );
  };
  const setContent = (change: Content | ((previous: Content) => Content)) => {
    if (running.current || current.current.pending) return;
    const content =
      typeof change === "function" ? change(current.current.content) : change;
    update({ ...current.current, content }, true);
  };
  const save = async (): Promise<Workout> => {
    if (running.current) return running.current;
    const savingOwner = currentOwner.current;
    const value = current.current;
    const submission = value.pending || {
      path: value.original ? "/workouts/" + value.original.id : "/workouts",
      method: value.original ? "PUT" : "POST",
      body: value.original
        ? { version: value.original.version, content: clean(value.content) }
        : { content: clean(value.content) },
      requestId: crypto.randomUUID(),
    };
    update({ ...value, pending: submission }, true);
    setSaving(true);
    const promise = (async () => {
      try {
        const result = await api<Workout>(
          submission.path,
          submission.method,
          submission.body,
          submission.requestId,
        );
        if (currentOwner.current === savingOwner) {
          update({ content: initial(), original: null, pending: null }, false);
        }
        return result;
      } catch (error) {
        if (currentOwner.current === savingOwner) {
          if (
            error instanceof ApiError &&
            error.status >= 400 &&
            error.status < 500
          ) {
            update({ ...value, pending: null }, true);
          }
          setSaveError(error as Error);
        }
        throw error;
      } finally {
        running.current = null;
        setSaving(false);
      }
    })();
    running.current = promise;
    return promise;
  };
  useEffect(() => {
    const leave = (event: BeforeUnloadEvent) => {
      if (running.current) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", leave);
    return () => window.removeEventListener("beforeunload", leave);
  }, [active, saveError]);
  return {
    content: buffer.content,
    original: buffer.original,
    pending: !!buffer.pending,
    active,
    setContent,
    replace,
    discard,
    save,
    saving,
    saveError,
  };
}
