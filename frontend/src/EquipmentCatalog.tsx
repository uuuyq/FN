import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Dropdown,
  Form,
  Input,
  Modal,
  Select,
  message,
  Spin,
  Typography,
} from "antd";
import { api } from "./api";
import { getErrorMessage } from "./errors";

type Equipment = {
  id: string;
  name: string;
  equipment_id?: string | null;
  version: number;
  category: string;
};
type EquipmentList = { items: Equipment[]; loading: boolean; error: string };
const initialList: EquipmentList = { items: [], loading: true, error: "" };

const categories = ["自由重量", "固定器械", "训练架与凳", "有氧器械", "功能训练", "辅助与恢复", "其他"];

export function EquipmentCatalog({
  active,
  revision,
}: {
  active: boolean;
  revision: number;
}) {
  const [mine, setMine] = useState(initialList);
  const [presets, setPresets] = useState(initialList);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Equipment | null>(null);
  const [form] = Form.useForm();
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState("全部");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const generation = useRef(0);
  const [messageApi, messageHolder] = message.useMessage();
  const [modalApi, modalHolder] = Modal.useModal();

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
  const openAdd = () => {
    form.resetFields();
    setEditing(null);
    setAdding(true);
  };
  const openEdit = (item: Equipment) => {
    form.setFieldsValue({ name: item.name, category: item.category });
    setEditing(item);
  };
  const confirmRemove = (item: Equipment) => {
    modalApi.confirm({
      title: `删除器械「${item.name}」？`,
      okText: "删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: () =>
        mutate(async () => {
          await api("/user-equipment/" + item.id, "DELETE", {
            version: item.version,
          });
        }, "器械已删除"),
    });
  };
  const publicIds = new Set(presets.items.map((item) => item.id));
  const entries = [
    ...presets.items.map((item) => ({
      item,
      user: mine.items.find((user) => user.equipment_id === item.id),
      category: mine.items.find(user => user.equipment_id === item.id)?.category ?? item.category,
    })),
    ...mine.items
      .filter((item) => !item.equipment_id || !publicIds.has(item.equipment_id))
      .map((item) => ({
        item,
        user: item,
        category: item.category,
      })),
  ];
  const search = query.trim().toLocaleLowerCase();
  const groups = categories
    .filter((name) => group === "全部" || group === name)
    .map((category) => ({
      name: category,
      items: entries.filter(
        (entry) =>
          entry.category === category &&
          [entry.item.name, entry.user?.name].some((name) =>
            name?.toLocaleLowerCase().includes(search),
          ),
      ),
    }))
    .filter((entry) => entry.items.length);
  return (
    <div className="equipment-catalog">
      {messageHolder}
      {modalHolder}
      <div className="catalog-toolbar">
        <Input.Search
          aria-label="搜索器械"
          placeholder="搜索器械"
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Button type="primary" onClick={openAdd}>
          新增器械
        </Button>
      </div>
      <div className="catalog-categories" aria-label="器械分类">
        {[
          "全部",
          ...categories.filter((name) =>
            entries.some((entry) => entry.category === name),
          ),
        ].map((name) => (
          <Button
            key={name}
            type={group === name ? "primary" : "text"}
            onClick={() => setGroup(name)}
          >
            {name}
          </Button>
        ))}
      </div>
      {status(mine)}
      {status(presets)}
      {groups.map((group) => (
        <section key={group.name} className="catalog-section" aria-label={group.name}>
          <h3>
            {group.name} <small>{group.items.length}</small>
          </h3>
          <div className="exercise-grid">
            {group.items.map(({ item, user }) => {
              if (!user)
                return (
                  <div className="exercise-tile" key={"public-" + item.id}>
                    <button type="button" aria-label={item.name} disabled>
                      <strong>{item.name}</strong>
                      <span>{item.category}</span>
                    </button>
                  </div>
                );
              return (
                <div className="exercise-tile selectable" key={item.id}>
                  <button
                    type="button"
                    aria-label={item.name}
                    disabled={busy}
                    onClick={() => openEdit(item)}
                  >
                    <strong>{item.name}</strong>
                    <span>{item.category}</span>
                  </button>
                  <Dropdown
                    trigger={["click"]}
                    menu={{
                      items: [
                        { key: "edit", label: "编辑" },
                        { key: "delete", label: "删除", danger: true },
                      ],
                      onClick: ({ key }) =>
                        key === "edit" ? openEdit(item) : confirmRemove(item),
                    }}
                  >
                    <Button
                      className="exercise-manage"
                      type="text"
                      aria-label={`管理器械 ${item.name}`}
                      disabled={busy}
                    >
                      ···
                    </Button>
                  </Dropdown>
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
      <Modal
        title={editing ? "编辑器械" : "新增器械"}
        open={adding || !!editing}
        okText={editing ? "保存" : "添加"}
        cancelText="取消"
        confirmLoading={busy}
        onOk={() => form.submit()}
        onCancel={() => {
          setAdding(false);
          setEditing(null);
        }}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(v) =>
            void mutate(async () => {
              const values = {
                name: (v.name as string).trim(),
                category: v.category as string,
              };
              if (editing) {
                await api("/user-equipment/" + editing.id, "PUT", {
                  ...values,
                  equipment_id: editing.equipment_id,
                  version: editing.version,
                });
              } else {
                await api("/user-equipment", "POST", values);
              }
              setAdding(false);
              setEditing(null);
            }, editing ? "器械已保存" : "器械已添加")
          }
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, whitespace: true, message: "请输入器械名称" }]}
          >
            <Input aria-label="自定义器械名称" maxLength={100} autoFocus />
          </Form.Item>
          <Form.Item name="category" label="分类" initialValue="其他">
            <Select
              aria-label="器械分类"
              options={categories.map((value) => ({ value, label: value }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
