import type { Content, Exercise } from "./api";

// Card contents from the agent carry the same shape as saved Content but may
// omit UI-only fields such as missing_information; names may need a fallback
// map when the catalog is not passed in.
export type SummaryContent = Omit<Content, "missing_information"> & {
  missing_information?: Record<string, string>;
};

const weightModeNames: Record<string, string> = {
  external: "外部重量",
  bodyweight: "自重",
  added: "附加重量",
  assisted: "辅助重量",
  unknown: "未知",
};
const weightScopeNames: Record<string, string> = {
  total: "总重量",
  per_side: "单侧重量",
  unknown: "未知",
};

export function TrainingSummary({
  content,
  catalog,
  names,
}: {
  content: SummaryContent;
  catalog?: Exercise[];
  names?: Record<string, string>;
}) {
  const exerciseName = (entry: SummaryContent["exercises"][number]) => {
    if (entry.name_snapshot) return entry.name_snapshot;
    const fromCatalog = catalog?.find((x) => x.id === entry.exercise_id)?.name;
    return fromCatalog || names?.[entry.exercise_id || ""] || entry.custom_name || "自定义动作";
  };
  return (
    <>
      <p>
        {content.actual_date} {content.actual_time}
      </p>
      {content.exercises.map((e, i) => (
        <section key={e.id || i}>
          <h3>
            {i + 1}. {exerciseName(e)}
          </h3>
          <p>
            计重：{weightModeNames[e.weight_mode] || e.weight_mode} /{" "}
            {weightScopeNames[e.weight_scope] || e.weight_scope}
          </p>
          {e.sets.map((s, j) => (
            <p key={s.id || j}>
              第 {j + 1} 组 · {s.kind === "warmup" ? "热身" : "正式"} ·{" "}
              {s.weight_kg ?? "未记录"} kg × {s.reps ?? "未记录"} 次 {s.notes}
            </p>
          ))}
        </section>
      ))}
      <p>{content.notes}</p>
    </>
  );
}
