import { getErrorMessage } from "./errors";
import { useEffect, useState } from "react";
import { Alert, Button, Card, Modal, Space } from "antd";
import { api, type Workout } from "./api";
export function TrainingCalendar({
  today,
  revision,
  edit,
  add,
}: {
  today: string;
  revision: number;
  edit: (w: Workout) => void;
  add: (date: string) => void;
}) {
  const [origin, setOrigin] = useState({ x: 0, y: 0 });
  const [loading, setLoading] = useState(false);
  const [month, setMonth] = useState(today.slice(0, 7));
  const [days, setDays] = useState<{ date: string; count: number }[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [records, setRecords] = useState<Workout[]>([]);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState<Workout | null>(null);
  const [deletingBusy, setDeletingBusy] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let live = true;
    setError("");
    void api(`/workouts/calendar?month=${month}`)
      .then((r) => {
        if (live) setDays(r.days);
      })
      .catch((e) => {
        if (live) setError(getErrorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [month, revision, reload]);
  useEffect(() => {
    let live = true;
    setRecords([]);
    if (selected)
      void (async () => {
        setLoading(true);
        try {
          let all: Workout[] = [];
          let offset = 0;
          while (true) {
            const r = await api(
              `/workouts?on=${selected}&limit=200&offset=${offset}`,
            );
            all.push(...r.items);
            if (all.length >= r.total) break;
            offset += 200;
          }
          if (live) setRecords(all);
        } catch (e) {
          if (live) setError(getErrorMessage(e));
        } finally {
          if (live) setLoading(false);
        }
      })();
    return () => {
      live = false;
    };
  }, [selected, revision, reload]);
  const [y, m] = month.split("-").map(Number);
  const offset = (new Date(y, m - 1, 1).getDay() + 6) % 7;
  const count = new Date(y, m, 0).getDate();
  const move = (delta: number) => {
    const d = new Date(y, m - 1 + delta, 1);
    setMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  };
  return (
    <section className="calendar-card" aria-label="训练日历">
      <div className="calendar-heading">
        <div>
          <h2>
            {y} 年 {m} 月
          </h2>
          <span>已记录 {days.length} 个训练日</span>
        </div>
        <Space>
          <Button aria-label="上月" onClick={() => move(-1)}>
            ‹
          </Button>
          <Button onClick={() => setMonth(today.slice(0, 7))}>今天</Button>
          <Button aria-label="下月" onClick={() => move(1)}>
            ›
          </Button>
        </Space>
      </div>
      {error && <Alert type="error" message={error} />}
      <div className="calendar-grid">
        {["一", "二", "三", "四", "五", "六", "日"].map((d) => (
          <div className="weekday" key={d}>
            {d}
          </div>
        ))}
        {Array.from({ length: offset }, (_, i) => (
          <div key={`blank${i}`} />
        ))}
        {Array.from({ length: count }, (_, i) => {
          const date = `${month}-${String(i + 1).padStart(2, "0")}`;
          const n = days.find((d) => d.date === date)?.count || 0;
          return (
            <button
              key={date}
              className={`calendar-day ${n ? "trained" : ""} ${date === today ? "today" : ""} ${date === selected ? "selected" : ""}`}
              aria-label={`${date} ${n ? `${n}条训练` : "没有记录"}`}
              onClick={(event) => {
                const rect = event.currentTarget.getBoundingClientRect();
                setOrigin({
                  x: rect.left + rect.width / 2,
                  y: rect.top + rect.height / 2,
                });
                setSelected(date);
              }}
            >
              <span>{i + 1}</span>
              {n > 0 && <small>● {n} 条</small>}
            </button>
          );
        })}
      </div>
      <p className="calendar-legend">● 已记录训练 · 点击日期查看或补录</p>
      <Modal
        title="删除这条训练记录？"
        open={!!deleting}
        okText="删除"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        confirmLoading={deletingBusy}
        closable={!deletingBusy}
        maskClosable={!deletingBusy}
        onCancel={() => { if (!deletingBusy) setDeleting(null); }}
        onOk={async () => {
          if (!deleting || deletingBusy) return;
          setDeletingBusy(true);
          setDeleteError("");
          try {
            await api(`/workouts/${deleting.id}`, "DELETE", { version: deleting.version });
            setRecords((rows) => rows.filter((row) => row.id !== deleting.id));
            setDeleting(null);
            setReload((v) => v + 1);
          } catch (e) {
            setDeleteError(getErrorMessage(e));
          } finally {
            setDeletingBusy(false);
          }
        }}
      >
        <p>{deleting?.content.actual_date} 的这条记录将从训练历史中删除，确认继续？</p>
        {deleteError && <Alert type="error" message={deleteError} />}
      </Modal>
      <Modal
        title={selected}
        open={!!selected}
        onCancel={() => setSelected(null)}
        footer={null}
        centered
        width={420}
        className="date-detail-modal"
        styles={{ body: { maxHeight: "min(440px, 65dvh)", overflowY: "auto" } }}
        modalRender={(node) => (
          <div
            style={{
              transformOrigin: `${origin.x - (window.innerWidth - Math.min(420, window.innerWidth - 32)) / 2}px ${origin.y - window.innerHeight / 2}px`,
            }}
            className="date-detail-emerge"
          >
            {node}
          </div>
        )}
      >
        <Button
          type="primary"
          onClick={() => {
            add(selected!);
            setSelected(null);
          }}
        >
          新增训练
        </Button>
        {loading && <p role="status">正在加载…</p>}
        {!loading && records.length === 0 && <p>这一天还没有训练记录。</p>}
        {records.map((w) => (
          <Card
            className="entry"
            key={w.id}
            title={w.content.actual_time || "训练记录"}
          >
            {w.content.exercises.map((entry, index) => (
              <div className="date-exercise" key={index}>
                <strong>
                  {entry.name || entry.custom_name || "动作"}
                </strong>
                <table className="set-table">
                  <thead>
                    <tr>
                      <th>组</th>
                      <th>类型</th>
                      <th>重量 (kg)</th>
                      <th>次数</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entry.sets.map((set, i) => (
                      <tr key={set.id || i}>
                        <td>{i + 1}</td>
                        <td>{set.kind === "warmup" ? "热身" : "正式"}</td>
                        <td>{set.weight_kg ?? ""}</td>
                        <td>{set.reps ?? ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
            {w.content.notes && <p>{w.content.notes}</p>}
            <Space>
              <Button
                onClick={() => {
                  edit(w);
                  setSelected(null);
                }}
              >
                编辑记录
              </Button>
              <Button
                danger
                onClick={() => { setDeleteError(""); setDeleting(w); }}
              >
                删除记录
              </Button>
            </Space>
          </Card>
        ))}
      </Modal>
    </section>
  );
}
