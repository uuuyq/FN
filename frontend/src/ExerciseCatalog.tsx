import { useState } from "react";
import { Button, Dropdown, Empty, Input, Select } from "antd";
import type { Exercise } from "./api";
export const categories = [
  "胸部",
  "背部",
  "肩部",
  "手臂",
  "腿臀",
  "核心",
  "有氧与全身",
  "其他",
];
function category(e: Exercise) {
  const m = e.primary_muscles || "";
  if (/胸/.test(m)) return "胸部";
  if (/背|斜方|竖脊/.test(m)) return "背部";
  if (/三角|肩/.test(m)) return "肩部";
  if (/肱|前臂|腕/.test(m)) return "手臂";
  if (/股|臀|腘|小腿|腓肠|比目鱼|髋|胫|内收/.test(m)) return "腿臀";
  if (/腹|核心/.test(m)) return "核心";
  if (/全身|心肺|心血管/.test(m)) return "有氧与全身";
  return "其他";
}
function groupOf(e: Exercise) {
  return e.category || category(e);
}
export function ExerciseCatalog({
  items,
  busy,
  toggle,
  create,
  edit,
  remove,
}: {
  items: Exercise[];
  busy: boolean;
  toggle: (e: Exercise) => void;
  create: () => void;
  edit: (e: Exercise) => void;
  remove: (e: Exercise) => void;
}) {
  const [search, setSearch] = useState("");
  const [group, setGroup] = useState("全部");
  const [equipment, setEquipment] = useState<string>();
  const visible = items.filter(
    (e) =>
      e.name.toLowerCase().includes(search.trim().toLowerCase()) &&
      (group === "全部" || groupOf(e) === group) &&
      (!equipment ||
        (equipment === "徒手"
          ? e.equipment.length === 0
          : e.equipment.split(/[、,，]/).map((value) => value.trim()).includes(equipment))),
  );
  return (
    <section aria-label="动作目录">
      <div className="catalog-toolbar">
        <Input.Search
          aria-label="搜索动作"
          placeholder="搜索动作名称"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          allowClear
        />
        <Select
          aria-label="按器械筛选"
          placeholder="全部器械"
          value={equipment}
          allowClear
          onChange={setEquipment}
          options={["徒手", ...new Set(items.flatMap((e) => e.equipment.split(/[、,，]/).map((value) => value.trim()).filter(Boolean)))].map(
            (value) => ({ value, label: value }),
          )}
        />
        <Button type="primary" onClick={create}>新增动作</Button>
      </div>
      <div className="catalog-categories" aria-label="动作分类">
        {[
          "全部",
          ...categories.filter((c) => items.some((e) => groupOf(e) === c)),
        ].map((c) => (
          <Button
            key={c}
            type={group === c ? "primary" : "text"}
            onClick={() => setGroup(c)}
          >
            {c}
          </Button>
        ))}
      </div>
      <p className="catalog-legend">
        蓝色表示可训练，点击卡片切换 · {visible.length} 个动作
      </p>
      {!visible.length && <Empty description="没有符合条件的动作" />}
      {categories.map((c) => {
        const rows = visible.filter((e) => groupOf(e) === c);
        return (
          rows.length > 0 && (
            <section key={c} className="catalog-section">
              <h3>
                {c} <small>{rows.length}</small>
              </h3>
              <div className="exercise-grid">
                {rows.map((e) => (
                  <div
                    className={`exercise-tile ${e.active ? "selectable" : ""}`}
                    key={e.id}
                  >
                    <button
                      type="button"
                      aria-label={e.name}
                      aria-pressed={e.active}
                      disabled={busy}
                      onClick={() => toggle(e)}
                    >
                      <strong>{e.name}</strong>
                      <span>{e.primary_muscles || "肌群未设置"}</span>
                      <span>{e.equipment || "徒手"}</span>
                    </button>
                    {e.owner_id && (
                      <Dropdown
                        trigger={["click"]}
                        menu={{
                          items: [
                            { key: "edit", label: "编辑" },
                            { key: "delete", label: "删除", danger: true },
                          ],
                          onClick: ({ key }) =>
                            key === "edit" ? edit(e) : remove(e),
                        }}
                      >
                        <Button
                          className="exercise-manage"
                          type="text"
                          aria-label={`管理动作 ${e.name}`}
                          disabled={busy}
                        >
                          ···
                        </Button>
                      </Dropdown>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )
        );
      })}
    </section>
  );
}
