import { MarkdownReply } from "./MarkdownReply";
import { getErrorMessage } from "./errors";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Dropdown, Input, Modal, Space, Typography } from "antd";
import { api, ApiError, conversationStream } from "./api";
import {
  buildTimeline,
  canRetry,
  latestActions,
  type Action,
  type Snapshot,
  type Turn,
} from "./conversation-types";
import { ConversationActionCard } from "./ConversationActionCard";

type Pending = {
  path: string;
  body: unknown;
  requestId: string;
  turnId?: string;
  mode: "edit" | "read";
  sentText?: string;
};

// Error codes with dedicated guidance on top of the server's message.
const turnErrorHints: Record<string, string> = {
  context_too_large:
    "对话内容已超过模型上下文上限，请新建会话继续，不建议反复重试。",
  model_timeout: "模型响应超时，可在对话未继续时点击“重试本轮”。",
  agent_loop_limit: "本轮处理达到次数上限，可缩小问题或发送新消息。",
  model_tool_calling_unsupported:
    "当前模型连接不支持工具调用，请检查 AI 配置。",
};

export function Conversation({
  owner,
  onSend,
  onLock,
  onNearBottomChange,
  refresh,
  names,
  newChatSignal,
  onboarding = false,
  guideSignal = 0,
}: {
  owner: string;
  onSend?: () => void;
  onLock: (locked: boolean) => void;
  onNearBottomChange?: (nearBottom: boolean) => void;
  refresh: () => Promise<void>;
  names: Record<string, string>;
  newChatSignal?: number;
  onboarding?: boolean;
  guideSignal?: number;
}) {
  const [drafts, setDrafts] = useState<{ message_id: string; text: string }[]>(
    [],
  );
  const [partialFailed, setPartialFailed] = useState(false);
  const [sentDraft, setSentDraft] = useState("");
  const streamController = useRef<AbortController | null>(null);
  const streamGeneration = useRef(0);
  const resumingAcceptedTurn = useRef(false);
  useEffect(() => () => streamController.current?.abort(), []);
  const [deleting, setDeleting] = useState<{
    id: string;
    title: string;
  } | null>(null);
  const [renaming, setRenaming] = useState<{
    id: string;
    title: string;
  } | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [managing, setManaging] = useState(false);
  const [historyMounted, setHistoryMounted] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [items, setItems] = useState<{ id: string; title: string }[]>([]);
  const [id, setIdState] = useState<string | null>(null),
    [data, setData] = useState<Snapshot | null>(null);
  const starterQuestion = "你有哪些功能？我该怎么开始记录训练或生成训练计划？";
  const [text, setText] = useState(onboarding ? starterQuestion : "");
  const [guideOpen, setGuideOpen] = useState(onboarding);
  const [guideError, setGuideError] = useState("");
  const guideDismissed = useRef(!onboarding);
  const previousGuideSignal = useRef(guideSignal);
  useEffect(() => {
    if (guideSignal === previousGuideSignal.current) return;
    previousGuideSignal.current = guideSignal;
    setGuideOpen(true);
    setText(current => current.trim() ? current : starterQuestion);
    controls.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [guideSignal]);
  async function dismissGuide() {
    setGuideOpen(false);
    if (guideDismissed.current) return;
    try {
      await api("/auth/onboarding/dismiss", "POST", {});
      guideDismissed.current = true;
      setGuideError("");
    } catch (e) {
      setGuideError(getErrorMessage(e));
    }
  }
  const [hasStreamText, setHasStreamText] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [sendError, setSendError] = useState(false);
  const retryText = useRef("");
  const [online, setOnline] = useState<any>(null);
  // Button request in flight; one X-Request-ID per action and kind is reused
  // across retries so a repeated click never duplicates the write.
  const [working, setWorking] = useState<{
    actionId: string;
    kind: "confirm" | "cancel";
  } | null>(null);
  const actionRequestIds = useRef<Map<string, string>>(new Map());
  const loadRevision = useRef(0);
  const idRef = useRef<string | null>(null);
  const pending = useRef<Pending | null>(null);
  const alive = useRef(true);
  const previousSignal = useRef(newChatSignal);
  const nearBottom = useRef(true);
  const end = useRef<HTMLDivElement>(null);
  const [showScrollToEnd, setShowScrollToEnd] = useState(false);
  const controls = useRef<HTMLDivElement>(null);
  const scrollToEnd = () => {
    nearBottom.current = true;
    requestAnimationFrame(() =>
      end.current?.scrollIntoView({
        block: "end",
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
      }),
    );
  };
  useEffect(() => {
    const element = controls.current;
    if (!element) return;
    const resize = () =>
      document.documentElement.style.setProperty(
        "--composer-height",
        `${element.getBoundingClientRect().height}px`,
      );
    const viewport = () => {
      const view = window.visualViewport;
      element.style.bottom = `${view ? Math.max(0, window.innerHeight - view.height - view.offsetTop) : 0}px`;
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    window.visualViewport?.addEventListener("resize", viewport);
    window.visualViewport?.addEventListener("scroll", viewport);
    resize();
    viewport();
    return () => {
      observer.disconnect();
      window.visualViewport?.removeEventListener("resize", viewport);
      window.visualViewport?.removeEventListener("scroll", viewport);
      document.documentElement.style.removeProperty("--composer-height");
    };
  }, []);
  const setId = (value: string | null) => {
    idRef.current = value;
    setIdState(value);
  };
  useEffect(() => {
    const check = () => {
      nearBottom.current =
        window.innerHeight + window.scrollY >=
        document.documentElement.scrollHeight - 160;
      setShowScrollToEnd(!nearBottom.current);
      onNearBottomChange?.(nearBottom.current);
    };
    const observer = new ResizeObserver(check);
    observer.observe(document.body);
    window.addEventListener("scroll", check, { passive: true });
    window.addEventListener("resize", check);
    check();
    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", check);
      window.removeEventListener("resize", check);
    };
  }, [onNearBottomChange]);
  useEffect(() => {
    if (!data?.messages.length && !drafts.length && !sentDraft) return;
    if (nearBottom.current)
      end.current?.scrollIntoView({
        block: "end",
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
      });
  }, [data?.messages.length, drafts, sentDraft]);
  const storage = "fnote-conversation-" + owner;
  const turnKey = "fnote-turn-" + owner;
  const resetCurrent = () => {
    streamController.current?.abort();
    streamGeneration.current++;
    setDrafts([]);
    setSentDraft("");
    setId(null);
    setData(null);
    setWorking(null);
    setText("");
    setError("");
    setSendError(false);
    setNotice("");
    setHistoryOpen(false);
    pending.current = null;
    onLock(false);
  };
  const startNewChat = () => {
    localStorage.removeItem(storage);
    resetCurrent();
    scrollToEnd();
  };
  const load = async (target?: string | null): Promise<Snapshot | null> => {
    const key = target ?? idRef.current;
    if (!key) return null;
    const revision = ++loadRevision.current;
    let value: Snapshot;
    try {
      value = await api<Snapshot>("/conversations/" + key);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        // Stale migrated IDs disappear instead of showing a dead restore button.
        localStorage.removeItem(storage);
        localStorage.removeItem(turnKey);
        if (idRef.current === key) {
          setId(null);
          setData(null);
          pending.current = null;
          onLock(false);
        }
        throw new ApiError(404, {
          code: "not_found",
          message: "该对话不存在或已删除，已返回新对话。",
        });
      }
      throw e;
    }
    // A response for a conversation the user already left must not win.
    if (
      alive.current &&
      idRef.current === key &&
      revision === loadRevision.current
    )
      setData(value);
    return idRef.current === key ? value : null;
  };
  useEffect(() => {
    alive.current = true;
    // A page refresh starts with a blank conversation. History is opened explicitly.
    streamController.current?.abort();
    streamGeneration.current++;
    setDrafts([]);
    setSentDraft("");
    setId(null);
    setData(null);
    setWorking(null);
    setHistoryOpen(false);
    pending.current = null;
    setSendError(false);
    onLock(false);
    void api("/ai/status")
      .then((value) => {
        if (alive.current) setOnline(value);
      })
      .catch(() => {});
    return () => {
      alive.current = false;
    };
  }, [owner]);
  useEffect(() => {
    if (newChatSignal === previousSignal.current) return;
    previousSignal.current = newChatSignal;
    localStorage.removeItem(storage);
    resetCurrent();
  }, [newChatSignal]);
  useEffect(() => {
    if (historyOpen) return;
    const timer = setTimeout(
      () => setHistoryMounted(false),
      matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 240,
    );
    return () => clearTimeout(timer);
  }, [historyOpen]);
  useEffect(() => {
    if (!historyOpen) return;
    let live = true;
    void api("/conversations?limit=200")
      .then((value) => {
        if (live) setItems(value.items);
      })
      .catch((e) => {
        if (live) setError(getErrorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [historyOpen]);
  const observe = async (
    p: Pending,
    method: "GET" | "POST",
    target: string,
  ) => {
    streamController.current?.abort();
    const controller = new AbortController();
    streamController.current = controller;
    const generation = ++streamGeneration.current;
    let sequence = -1;
    let currentDrafts: { message_id: string; text: string }[] = [];
    let timer: ReturnType<typeof setTimeout> | undefined;
    const valid = () =>
      alive.current &&
      generation === streamGeneration.current &&
      idRef.current === target;
    const flush = () => {
      timer = undefined;
      if (valid()) setDrafts(currentDrafts.map((item) => ({ ...item })));
    };
    setHasStreamText(false);
    setPartialFailed(false);
    setDrafts([]);
    setSentDraft(p.sentText || "");
    setBusy(true);
    setWorking(null);
    onLock(p.mode === "edit");
    setError("");
    setSendError(false);
    try {
      const result: Turn = await conversationStream(
        p.turnId && method === "GET" ? `/turns/${p.turnId}/events` : p.path,
        method,
        p.body,
        p.requestId,
        (turnId) => {
          p.turnId = turnId;
          if (valid()) localStorage.setItem(turnKey, turnId);
        },
        ({ event, payload }) => {
          if (!valid() || payload.turn_id !== p.turnId) return;
          if (event === "snapshot") {
            setSentDraft("");
            void load(target).catch(() => {});
            sequence = payload.sequence;
            currentDrafts = payload.messages;
          } else if (
            ["message_start", "text_delta", "message_end"].includes(event)
          ) {
            if (payload.sequence <= sequence) return;
            sequence = payload.sequence;
            if (event === "message_start")
              currentDrafts.push({ message_id: payload.message_id, text: "" });
            if (event === "text_delta") {
              if (payload.text) setHasStreamText(true);
              const item = currentDrafts.find(
                (item) => item.message_id === payload.message_id,
              );
              if (item) item.text += payload.text;
            }
          } else return;
          if (!timer) timer = setTimeout(flush, 50);
        },
        controller.signal,
      );
      if (!valid()) return;
      if (timer) clearTimeout(timer);
      flush();
      const snapshot = await load(target);
      if (!valid()) return;
      if (timer) clearTimeout(timer);
      timer = undefined;
      setSentDraft("");
      const durableText = snapshot?.messages
        .filter((m) => m.turn_id === result.id && m.role === "assistant")
        .map((m) => m.content || "");
      currentDrafts = currentDrafts.filter(
        (item) => item.text && !durableText?.includes(item.text),
      );
      setDrafts(result.status === "succeeded" ? [] : currentDrafts);
      setPartialFailed(result.status !== "succeeded");
      // completed only means the turn ended; confirmation_required waits for
      // the card button, and nothing is written during the turn itself.
      if (result.status !== "succeeded") {
        const hint = result.error ? turnErrorHints[result.error] : undefined;
        setError(
          "本轮未完成：" +
            getErrorMessage(new Error(result.error_message || "")) +
            "。" +
            (hint || "对话信息已保留。"),
        );
      }
      pending.current = null;
      localStorage.removeItem(turnKey);
      if (!snapshot && idRef.current === target) throw Error("会话恢复失败");
    } catch (e) {
      if (!valid()) return;
      flush();
      if (alive.current) {
        retryText.current = p.sentText || retryText.current;
        setSendError(true);
      }
      if (e instanceof ApiError && e.status >= 400 && e.status < 500)
        pending.current = null;
      // If accepted was received, keep the input locked until recovery establishes a terminal state.
      if (p.turnId) return;
    } finally {
      if (timer) clearTimeout(timer);
      if (valid()) {
        setBusy(false);
        onLock(!!pending.current && pending.current.mode === "edit");
      }
    }
  };
  const sendText = async (value: string) => {
    if (guideOpen) void dismissGuide();
    scrollToEnd();
    onSend?.();
    setError("");
    setSendError(false);
    setBusy(true);
    // Clear the composer as soon as the text is captured for sending.
    setText("");
    try {
      let target = idRef.current;
      if (!target) {
        const created = await api<{ id: string }>("/conversations", "POST", {
          title: value.slice(0, 30) || "训练对话",
        });
        target = created.id;
        setId(target);
        localStorage.setItem(storage, target);
        setItems((await api("/conversations?limit=200")).items);
      }
      const p: Pending = {
        path: `/conversations/${target}/messages`,
        body: {
          text: value,
          mode: "edit",
        },
        requestId: crypto.randomUUID(),
        mode: "edit",
        sentText: value,
      };
      pending.current = p;
      await observe(p, "POST", target);
    } catch (e) {
      retryText.current = value;
      setSendError(true);
      // The send never reached a durable turn; put the draft back.
      setText((current) => (current.trim() ? current : value));
    } finally {
      setBusy(false);
    }
  };
  const send = () => {
    if (!text.trim()) return;
    void sendText(text);
  };
  // Failure under the latest user message: resume the accepted turn, or resend
  // the text when the request never reached a durable turn.
  const retrySend = async () => {
    const p = pending.current;
    if (p && idRef.current) {
      await observe(p, p.turnId ? "GET" : "POST", idRef.current);
      return;
    }
    const value = retryText.current;
    if (value?.trim()) await sendText(value);
  };
  const recover = async () => {
    const p = pending.current;
    if (p && idRef.current)
      return observe(p, p.turnId ? "GET" : "POST", idRef.current);
    if (idRef.current) {
      await load();
      onLock(false);
    }
  };
  useEffect(() => {
    const resumeAcceptedTurn = () => {
      if (document.visibilityState !== "visible" || busy || resumingAcceptedTurn.current ||
          !pending.current?.turnId || !idRef.current) return;
      resumingAcceptedTurn.current = true;
      void observe(pending.current, "GET", idRef.current)
        .catch(() => {})
        .finally(() => { resumingAcceptedTurn.current = false; });
    };
    document.addEventListener("visibilitychange", resumeAcceptedTurn);
    window.addEventListener("online", resumeAcceptedTurn);
    return () => {
      document.removeEventListener("visibilitychange", resumeAcceptedTurn);
      window.removeEventListener("online", resumeAcceptedTurn);
    };
  });
  // Decisions return their durable model continuation, including execution failures.
  const decide = async (requested: Action, kind: "confirm" | "cancel") => {
    const conversationId = idRef.current;
    if (!conversationId) return;
    // Read the current row instead of a possibly stale rendered copy.
    const action = latestActions(data?.actions || []).get(requested.action_id);
    if (!action || action.status !== "pending") {
      await safe(async () => {
        await load();
      });
      return;
    }
    let requestId = actionRequestIds.current.get(action.action_id + kind);
    if (!requestId) {
      requestId = crypto.randomUUID();
      actionRequestIds.current.set(action.action_id + kind, requestId);
    }
    setError("");
    setNotice("");
    setSendError(false);
    setWorking({ actionId: action.action_id, kind });
    try {
      const updated = await api<Action>(
        `/conversation-actions/${action.action_id}/${kind}`,
        "POST",
        { version: action.version },
        requestId,
      );
      if (idRef.current !== conversationId) return;
      if (kind === "confirm" && updated.status === "confirmed") {
        let refreshed = true;
        try {
          await refresh();
        } catch {
          refreshed = false;
        }
        await load();
        setNotice(
          refreshed
            ? ""
            : "操作已执行，但界面刷新失败，请手动核对训练与设置数据。",
        );
      } else {
        // cancelled/conflict/failed only need the conversation back: the
        // event message and the card's terminal state carry the outcome.
        await load();
      }
      const continuationId = updated.result?.continuation_turn_id;
      if (typeof continuationId === "string") {
        const p: Pending = {
          path: `/turns/${continuationId}/events`,
          body: {},
          requestId: crypto.randomUUID(),
          mode: "edit",
          sentText: "",
          turnId: continuationId,
        };
        pending.current = p;
        await observe(p, "GET", conversationId);
      }
    } catch (e) {
      if (idRef.current === conversationId) setError(getErrorMessage(e));
      // A stale card (409) or vanished action (404): the reloaded snapshot
      // disables the outdated buttons with server state.
      await safe(async () => {
        await load();
      });
    } finally {
      if (alive.current) setWorking(null);
    }
  };
  const safe = async (fn: () => Promise<void>) => {
    try {
      setError("");
      setSendError(false);
      await fn();
    } catch (e) {
      setError(getErrorMessage(e));
    }
  };
  const timeline = data ? buildTimeline(data) : [];
  const lastTurn = data?.turns[data.turns.length - 1];
  const retryable = lastTurn && canRetry(lastTurn, data!) ? lastTurn : null;
  let lastUserId: string | undefined;
  for (const item of timeline)
    if (item.kind !== "card" && item.message.role === "user")
      lastUserId = item.message.id;
  const retryControl = sendError ? (
    <div style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 8 }}>
      <Typography.Text type="danger">未知异常</Typography.Text>
      <Button
        size="small"
        disabled={busy || !!working}
        onClick={() => void retrySend()}
      >
        重试
      </Button>
    </div>
  ) : null;
  const requestInFlight = busy || !!pending.current || !!working;
  return (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      {error && (
        <Alert
          type="error"
          message={error}
          action={
            pending.current ? (
              <Button onClick={() => void safe(recover)}>恢复轮次</Button>
            ) : undefined
          }
        />
      )}
      {notice && <Alert type="warning" message={notice} />}
      <div aria-label="对话消息" aria-live="polite">
        {timeline.map((item) => {
          if (item.kind === "card")
            return (
              <ConversationActionCard
                key={item.action.action_id}
                action={item.action}
                names={names}
                working={working}
                locked={busy || !!pending.current}
                onConfirm={(action) =>
                  void safe(() => decide(action, "confirm"))
                }
                onCancel={(action) => void safe(() => decide(action, "cancel"))}
              />
            );
          const message = item.message;
          return (
            <div
              key={message.id}
              className={`message-bubble ${message.role}`}
              style={{ marginBottom: 12 }}
            >
              {message.role === "event" ? (
                <Typography.Text type="secondary">
                  {message.content}
                </Typography.Text>
              ) : message.role === "assistant" ? (
                <MarkdownReply content={message.content || ""} />
              ) : (
                <>
                  <Typography.Paragraph
                    style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}
                  >
                    {message.content}
                  </Typography.Paragraph>
                  {message.id === lastUserId && retryControl}
                </>
              )}
            </div>
          );
        })}
        {sentDraft && (
          <div className="message-bubble user">
            {sentDraft}
            {retryControl}
          </div>
        )}
        {busy && !hasStreamText && <div className="thinking-status" role="status" aria-live="polite">思考中…</div>}
        {drafts
          .filter(
            (item) =>
              item.text &&
              !data?.messages.some(
                (m) =>
                  m.turn_id === pending.current?.turnId &&
                  m.role === "assistant" &&
                  m.content === item.text,
              ),
          )
          .map((item) => (
            <div
              key={item.message_id}
              className="message-bubble assistant"
              style={{ whiteSpace: "pre-wrap", marginBottom: 12 }}
            >
              <MarkdownReply content={item.text} />
              {partialFailed && (
                <Typography.Text type="warning">（未完成）</Typography.Text>
              )}
            </div>
          ))}
      </div>
      {retryable && (
        <Space>
          <Typography.Text type="warning">
            未完成轮次：
            {getErrorMessage(new Error(retryable.error_message || ""))}
          </Typography.Text>
          <Button
            disabled={requestInFlight}
            onClick={() =>
              void safe(async () => {
                const p: Pending = {
                  path: `/turns/${retryable.id}/retry`,
                  body: {},
                  requestId: crypto.randomUUID(),
                  mode: retryable.mode,
                };
                pending.current = p;
                await observe(p, "POST", idRef.current!);
              })
            }
          >
            重试本轮
          </Button>
        </Space>
      )}
      <div
        ref={end}
        style={{ scrollMarginBottom: "calc(var(--composer-height) + 16px)" }}
      />
      <div className="conversation-controls" ref={controls}>
        {showScrollToEnd && (
          <Button
            className="new-reply-shortcut"
            aria-label="跳到最新消息"
            title="跳到最新消息"
            onClick={scrollToEnd}
          >
            <span className="scroll-shortcut-arrow arrow-down" aria-hidden="true" />
          </Button>
        )}
        {guideOpen && <div className="conversation-guide" role="status">
          <div><strong>从一句提问开始，快速了解功能。</strong></div>
          <Button type="text" aria-label="关闭对话引导" onClick={() => void dismissGuide()}>×</Button>
        </div>}
        {guideError && <Alert type="warning" message="引导关闭状态未保存" description={guideError} action={<Button onClick={() => void dismissGuide()}>重试</Button>} />}
        <div className="composer-row">
          <Button
            type="text"
            title="历史对话"
            className="history-toggle"
            aria-label="展开历史对话"
            aria-expanded={historyOpen}
            onClick={() => {
              if (historyOpen) setHistoryOpen(false);
              else {
                setHistoryMounted(true);
                requestAnimationFrame(() =>
                  requestAnimationFrame(() => setHistoryOpen(true)),
                );
              }
            }}
            icon={
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                aria-hidden="true"
              >
                <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" />
              </svg>
            }
          />

          <Button
            type="text"
            title="新建对话"
            className="new-chat"
            aria-label="新对话"
            disabled={requestInFlight}
            onClick={startNewChat}
            icon={
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                aria-hidden="true"
              >
                <path d="M12 5v14M5 12h14" />
              </svg>
            }
          />

          <div className="chat-composer">
            <Input.TextArea
              aria-label="训练消息"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing &&
                  text.trim() &&
                  !requestInFlight
                ) {
                  e.preventDefault();
                  void send();
                }
              }}
              maxLength={8000}
              autoSize={{ minRows: 1, maxRows: 6 }}
              placeholder="提问或记录训练"
            />
            <Button
              className={`send-arrow ${guideOpen ? "guide-send" : ""}`}
              type="primary"
              aria-label="发送消息"
              title="发送"
              loading={busy}
              disabled={!text.trim() || requestInFlight}
              onClick={() => void send()}
              icon={
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="m6 12 6-6 6 6M12 6v13" />
                </svg>
              }
            />
          </div>
        </div>
        <div
          className={`history-reveal ${historyOpen ? "open" : ""}`}
          aria-hidden={!historyOpen}
          inert={!historyOpen}
        >
          <div className="history-reveal-inner">
            {(historyMounted || historyOpen) && (
              <section
                className="conversation-history"
                aria-label="历史对话面板"
              >
                {online && !online.configured && (
                  <Alert
                    type="warning"
                    message="模型尚未配置，可以继续手动记录。"
                  />
                )}
                <div className="history-heading">
                  <strong>历史对话</strong>
                </div>
                {items.length === 0 && <p>还没有历史对话</p>}
                <div className="history-list">
                  {items.map((item) => (
                    <div className="history-row" key={item.id}>
                      <button
                        type="button"
                        disabled={requestInFlight}
                        className={item.id === id ? "active" : ""}
                        onClick={() =>
                          void safe(async () => {
                            setWorking(null);
                            setId(item.id);
                            localStorage.setItem(storage, item.id);
                            const snapshot = await load(item.id);
                            setHistoryOpen(false);
                            scrollToEnd();
                            onSend?.();
                            const active = snapshot?.turns.find(
                              (t) => t.status === "running",
                            );
                            if (active) {
                              const p: Pending = {
                                path: `/turns/${active.id}/events`,
                                body: null,
                                requestId: crypto.randomUUID(),
                                turnId: active.id,
                                mode: active.mode,
                              };
                              pending.current = p;
                              await observe(p, "GET", item.id);
                            }
                          })
                        }
                      >
                        <span>{item.title}</span>
                      </button>
                      <Dropdown
                        trigger={["click"]}
                        menu={{
                          items: [
                            { key: "rename", label: "重命名" },
                            { key: "delete", label: "删除", danger: true },
                          ],
                          onClick: ({ key }) => {
                            if (key === "rename") {
                              setRenaming(item);
                              setRenameTitle(item.title);
                            } else setDeleting(item);
                          },
                        }}
                      >
                        <Button
                          type="text"
                          className="history-menu"
                          aria-label={`管理对话 ${item.title}`}
                          disabled={busy || managing || !!pending.current}
                        >
                          ···
                        </Button>
                      </Dropdown>
                    </div>
                  ))}
                </div>
                {id && (
                  <Button
                    type="text"
                    disabled={busy}
                    onClick={() => void safe(recover)}
                  >
                    恢复轮次
                  </Button>
                )}
              </section>
            )}
          </div>
        </div>
      </div>
      <Modal
        centered
        width={420}
        title="删除对话？"
        open={!!deleting}
        onCancel={() => setDeleting(null)}
        okText="删除"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        confirmLoading={managing}
        onOk={async () => {
          if (!deleting) return;
          const item = deleting;
          setManaging(true);
          try {
            await api(`/conversations/${item.id}`, "DELETE", {});
            setItems((rows) => rows.filter((row) => row.id !== item.id));
            if (idRef.current === item.id) {
              localStorage.removeItem(storage);
              localStorage.removeItem(turnKey);
              resetCurrent();
            }
            setDeleting(null);
          } catch (e) {
            setError(getErrorMessage(e));
          } finally {
            setManaging(false);
          }
        }}
      >
        <p>“{deleting?.title}”将从历史中删除，已保存的训练记录和计划会保留。</p>
      </Modal>
      <Modal
        centered
        width={420}
        title="重命名对话"
        open={!!renaming}
        onCancel={() => setRenaming(null)}
        okText="保存"
        cancelText="取消"
        confirmLoading={managing}
        okButtonProps={{
          disabled: !renameTitle.trim() || renameTitle.trim().length > 100,
        }}
        onOk={async () => {
          if (!renaming || !renameTitle.trim()) return;
          setManaging(true);
          try {
            const result = await api<{ id: string; title: string }>(
              `/conversations/${renaming.id}`,
              "PATCH",
              { title: renameTitle.trim() },
            );
            setItems((rows) =>
              rows.map((row) =>
                row.id === result.id ? { ...row, title: result.title } : row,
              ),
            );
            setRenaming(null);
          } catch (e) {
            setError(getErrorMessage(e));
          } finally {
            setManaging(false);
          }
        }}
      >
        <Input
          aria-label="对话名称"
          value={renameTitle}
          maxLength={100}
          onChange={(e) => setRenameTitle(e.target.value)}
          autoFocus
        />
      </Modal>
    </Space>
  );
}
