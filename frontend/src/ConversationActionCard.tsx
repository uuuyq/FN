import { Alert, Button, Card, Space, Typography } from "antd";
import {
  actionDecided,
  operationName,
  statusName,
  type Action,
} from "./conversation-types";
import { TrainingSummary, type SummaryContent } from "./TrainingSummary";

const profileFieldNames: Record<string, string> = {
  goal: "训练目标",
  restrictions: "限制",
  days_per_week: "每周训练天数",
  minutes_per_session: "单次时长（分钟）",
  preferences: "个人偏好",
  training_principles: "训练指导原则",
  history_workout_count: "参考训练次数",
  timezone: "时区",
};

function profileRows(before: any, after: any) {
  return Object.entries(profileFieldNames)
    .filter(([key]) => before?.[key] !== after?.[key])
    .map(([key, label]) => ({
      key,
      label,
      before: before?.[key] === undefined || before?.[key] === null || before?.[key] === ""
        ? "未设置"
        : String(before[key]),
      after: after?.[key] === undefined || after?.[key] === null || after?.[key] === ""
        ? "未设置"
        : String(after[key]),
    }));
}

function Details({
  action,
  names,
}: {
  action: Action;
  names: Record<string, string>;
}) {
  const details = action.details || {};
  if (action.operation === "create_workout" || action.operation === "update_workout") {
    const creating: string[] = details.creating_custom || [];
    return (
      <>
        {creating.length > 0 && (
          <Alert
            type="warning"
            showIcon
            message={`确认后将创建自定义动作：${creating.join("、")}`}
            style={{ marginBottom: 8 }}
          />
        )}
        {action.operation === "update_workout" && (
          <p>
            <Typography.Text type="secondary">
              修改前 ↓（目标记录 {details.workout_id} · 依据版本 {details.expected_version}）
            </Typography.Text>
          </p>
        )}
        {action.operation === "update_workout" ? (
          <TrainingSummary content={details.before as SummaryContent} names={names} />
        ) : (
          <TrainingSummary content={details.content as SummaryContent} names={names} />
        )}
        {action.operation === "update_workout" && (
          <>
            <p>
              <Typography.Text type="secondary">修改后 ↓</Typography.Text>
            </p>
            <TrainingSummary content={details.after as SummaryContent} names={names} />
          </>
        )}
      </>
    );
  }
  if (action.operation === "delete_workout")
    return (
      <>
        <p>
          {details.actual_date} 的训练记录（
          {(details.exercises || []).join("、") || "无动作信息"}）将被删除。
        </p>
        <p>
          <Typography.Text type="secondary">
            目标记录 {details.workout_id} · 依据版本 {details.expected_version}
          </Typography.Text>
        </p>
      </>
    );
  if (action.operation === "update_profile") {
    const rows = profileRows(details.before, details.after);
    if (!rows.length) return <p>个人条件没有变化。</p>;
    return (
      <>
        {rows.map((row) => (
          <p key={row.key}>
            {row.label}：{row.before} → {row.after}
          </p>
        ))}
      </>
    );
  }
  if (action.operation === "update_preferences")
    return (
      <>
        {(details.items || []).map((item: any, index: number) => (
          <p key={item.exercise_id || index}>
            {names[item.exercise_id] || item.exercise_id}：
            {item.active ? "可选" : "未启用"}
          </p>
        ))}
      </>
    );
  if (action.operation === "add_exercise")
    return (
      <>
        <p>新增个人动作：{details.name}</p>
        {action.status === "pending" && <p>确认后加入选择动作。</p>}
        {action.status === "confirmed" && <p>已加入选择动作。</p>}
        {[
          ["aliases", "别名"], ["primary_muscles", "主要肌群"],
          ["secondary_muscles", "辅助肌群"], ["equipment", "器械"],
          ["description", "说明"],
        ].map(([key, label]) => (
          <p key={key}>{label}：{details[key] || "未填写"}</p>
        ))}
      </>
    );
  if (action.operation === "add_equipment")
    return <p>新增可用器械：{details.name}</p>;
  // Unknown operations keep the generic summary instead of undefined.
  return null;
}

export function ConversationActionCard({
  action,
  names,
  working,
  locked,
  onConfirm,
  onCancel,
}: {
  action: Action;
  names: Record<string, string>;
  working: { actionId: string; kind: "confirm" | "cancel" } | null;
  /** Confirm pauses while newer conversation content is still processing. */
  locked?: boolean;
  onConfirm: (action: Action) => void;
  onCancel: (action: Action) => void;
}) {
  const decided = actionDecided(action);
  const busyHere = working?.actionId === action.action_id;
  const busyAnywhere = !!working;
  const failed = action.status === "conflict" || action.status === "failed";
  return (
    <Card
      size="small"
      className="action-card"
      data-action-id={action.action_id}
      data-action-status={action.status}
      data-operation={action.operation}
      title={`${operationName(action.operation)} · ${statusName(action.status)}`}
      style={{ margin: "8px 0" }}
    >
      {action.summary && (
        <Typography.Paragraph style={{ whiteSpace: "pre-wrap" }}>
          {action.summary}
        </Typography.Paragraph>
      )}
      {(action.details?.missing_fields || []).length > 0 && (
        <Alert type="info" message={`未记录${action.details.missing_fields.map((field: string) => field === "reps" ? "次数" : "重量").join("、")}`} />
      )}
      {(action.details?.creating_custom || []).length > 0 && (
        <Alert type="warning" message={`将创建自定义动作：${action.details.creating_custom.join("、")}`} />
      )}
      {action.operation === "undo_operation" && <p>{action.details?.effect}</p>}
      {action.operation === "add_exercise" ? (
        <Details action={action} names={names} />
      ) : (
        <details><summary>查看详情</summary><Details action={action} names={names} /></details>
      )}
      {failed && action.result?.error?.message && (
        <Alert
          type="error"
          showIcon
          message={action.result.error.message}
          style={{ marginTop: 8 }}
        />
      )}
      {!decided && (
        <Space style={{ marginTop: 8 }}>
          {action.allowed_operations.includes("confirm") && (
            <Button
              type="primary"
              aria-label={`确认执行${operationName(action.operation)}`}
              loading={busyHere && working?.kind === "confirm"}
              disabled={busyAnywhere || locked}
              onClick={() => onConfirm(action)}
            >
              确认执行
            </Button>
          )}
          {action.allowed_operations.includes("cancel") && (
            <Button
              aria-label={`取消${operationName(action.operation)}`}
              loading={busyHere && working?.kind === "cancel"}
              disabled={busyAnywhere}
              onClick={() => onCancel(action)}
            >
              取消变更
            </Button>
          )}
        </Space>
      )}
    </Card>
  );
}
