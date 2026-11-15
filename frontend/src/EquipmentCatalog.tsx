import { useEffect, useRef, useState } from "react";
import { Alert, Button, Input, message, Spin, Typography } from "antd";
import { api } from "./api";
import { getErrorMessage } from "./errors";

type Equipment = {
  id: string;
  name: string;
  equipment_id?: string | null;
  version: number;
};
type EquipmentList = { items: Equipment[]; loading: boolean; error: string };
const initialList: EquipmentList = { items: [], loading: true, error: "" };

const categories = [
  {
    name: "自由重量",
    ids: ["barbell", "dumbbell", "kettlebell", "ez-bar", "trap-bar", "plates"],
  },
  {
    name: "固定器械",
    ids: [
      "smith",
      "cable",
      "lat-pulldown",
      "seated-row",
      "chest-press",
      "pec-deck",
      "shoulder-press",
      "leg-press",
      "hack-squat",
      "leg-extension",
      "leg-curl",
      "hip-thrust",
      "hip-abduction",
      "hip-adduction",
      "calf-raise",
      "assisted-pullup",
    ],
  },
  {
    name: "训练架与凳",
    ids: [
      "bench",
      "pullup",
      "rack",
      "dip-bars",
      "roman-chair",
      "preacher-bench",
    ],
  },
  {
    name: "有氧器械",
    ids: [
      "treadmill",
      "bike",
      "air-bike",
      "rower",
      "elliptical",
      "stair-climber",
      "ski-erg",
    ],
  },
  {
    name: "功能训练",
    ids: [
      "band",
      "mini-band",
      "trx",
      "gym-rings",
      "stability-ball",
      "medicine-ball",
      "slam-ball",
      "bosu",
      "ab-wheel",
      "box",
      "step",
      "rope",
      "battle-rope",
      "sled",
      "sandbag",
    ],
  },
  { name: "辅助与恢复", ids: ["mat", "foam-roller"] },
  { name: "其他", ids: [] },
];
const categoryFor = (id: string | null | undefined) =>
  categories.find((category) => category.ids.includes(id || ""))?.name ||
  "其他";

export function EquipmentCatalog({
  active,
  revision,
}: {
  active: boolean;
  revision: number;
}) {
  const [mine, setMine] = useState(initialList);
  const [presets, setPresets] = useState(initialList);
  const [names, setNames] = useState<Record<string, string>>({});
  const [name, setName] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const generation = useRef(0);
  const [messageApi, holder] = message.useMessage();

  const load = async () => {
    const current = ++generation.current;
    const fetchList = async (path: string, update: typeof setMine) => {
      update((old) => ({ ...old, loading: true, error: "" }));
      try {
        const result = await api<{ items: Equipment[] }>(path);
        if (current === generation.current)
          update({ items: result.items, loading: false, error: "" });
      } catch (error) {
        if (current === generation.current)
          update((old) => ({
            ...old,
            loading: false,
            error: getErrorMessage(error),
          }));
      }
    };
    await Promise.all([
      fetchList("/user-equipment", setMine),
      fetchList("/equipment", setPresets),
    ]);
  };
  useEffect(() => {
    if (active) void load();
    return () => {
      generation.current++;
    };
  }, [active, revision]);

  const mutate = async (action: () => Promise<void>, success: string) => {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    try {
      await action();
      void messageApi.success(success);
      await load();
    } catch (error) {
      void messageApi.error(getErrorMessage(error));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  };
  const status = (list: EquipmentList) => (
    <>
      {list.loading && <Spin size="small" aria-label="正在加载器械" />}
      {list.error && (
        <Alert
          type="error"
          message={list.error}
          action={
            <Button disabled={busy} onClick={() => void load()}>
              重试
            </Button>
          }
        />
      )}
    </>
  );
  const publicIds = new Set(presets.items.map((item) => item.id));
  const entries = [
    ...presets.items.map((item) => ({
      item,
      user: mine.items.find((user) => user.equipment_id === item.id),
      category: categoryFor(item.id),
    })),
    ...mine.items
      .filter((item) => !item.equipment_id || !publicIds.has(item.equipment_id))
      .map((item) => ({
        item,
        user: item,
        category: categoryFor(item.equipment_id),
      })),
  ];
  const search = query.trim().toLocaleLowerCase();
  const groups = categories
    .map((category) => ({
      name: category.name,
      items: entries.filter(
        (entry) =>
          entry.category === category.name &&
          [entry.item.name, entry.user?.name].some((name) =>
            name?.toLocaleLowerCase().includes(search),
          ),
      ),
    }))
    .filter((group) => group.items.length);
  return (
    <div className="equipment-catalog">
      {holder}
      <Input.Search
        aria-label="搜索器械"
        placeholder="搜索器械"
        allowClear
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <form
        className="equipment-row"
        onSubmit={(event) => {
          event.preventDefault();
          if (!name.trim()) return;
          void mutate(async () => {
            await api("/user-equipment", "POST", { name: name.trim() });
            setName("");
          }, "器械已添加");
        }}
      >
        <Input
          aria-label="自定义器械名称"
          placeholder="自定义器械名称"
          value={name}
          maxLength={200}
          disabled={busy}
          onChange={(event) => setName(event.target.value)}
        />
        <Button htmlType="submit" disabled={busy || !name.trim()}>
          新增器械
        </Button>
      </form>
      {status(mine)}
      {status(presets)}
      {groups.map((group) => (
        <section key={group.name} aria-label={group.name}>
          <Typography.Title level={4}>{group.name}</Typography.Title>
          <div className="equipment-presets">
            {group.items.map(({ item, user }) => {
              if (!user)
                return (
                  <div className="equipment-row" key={"public-" + item.id}>
                    <span>{item.name}</span>
                  </div>
                );
              item = user;
              const edited = names[item.id] ?? item.name;
              return (
                <div className="equipment-row" key={item.id}>
                  <Input
                    aria-label="器械名称"
                    value={edited}
                    disabled={busy}
                    onChange={(event) =>
                      setNames((old) => ({
                        ...old,
                        [item.id]: event.target.value,
                      }))
                    }
                  />
                  <Button
                    disabled={busy || !edited.trim() || edited === item.name}
                    onClick={() =>
                      void mutate(async () => {
                        const updated = await api<Equipment>(
                          "/user-equipment/" + item.id,
                          "PUT",
                          {
                            name: edited.trim(),
                            equipment_id: item.equipment_id,
                            version: item.version,
                          },
                        );
                        setMine((old) => ({
                          ...old,
                          items: old.items.map((row) =>
                            row.id === item.id ? updated : row,
                          ),
                        }));
                        setNames((old) => {
                          const next = { ...old };
                          delete next[item.id];
                          return next;
                        });
                      }, "器械名称已保存")
                    }
                  >
                    保存名称
                  </Button>
                  <Button
                    disabled={busy}
                    onClick={() =>
                      void mutate(async () => {
                        await api("/user-equipment/" + item.id, "DELETE", {
                          version: item.version,
                        });
                        setMine((old) => ({
                          ...old,
                          items: old.items.filter((row) => row.id !== item.id),
                        }));
                      }, "器械已移除")
                    }
                  >
                    移除
                  </Button>
                </div>
              );
            })}
          </div>
        </section>
      ))}
      {!mine.loading &&
        !presets.loading &&
        !mine.error &&
        !presets.error &&
        !groups.length && (
          <Typography.Paragraph type="secondary">
            {search ? "未找到匹配的器械" : "暂无器械，可自定义添加"}
          </Typography.Paragraph>
        )}
    </div>
  );
}
