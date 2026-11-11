import { getErrorMessage } from "./errors";
import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Tabs,
  Dropdown,
  Typography,
} from "antd";
import {
  api,
  ApiError,
  setCSRF,
  blankSet,
  type Content,
  type Draft,
  type Exercise,
} from "./api";
import { TrainingSummary } from "./TrainingSummary";
import { Brand } from "./Brand";
import { useWorkoutDraft } from "./useWorkoutDraft";
import { Conversation } from "./Conversation";
import { TrainingCalendar } from "./TrainingCalendar";
import { ExerciseCatalog } from "./ExerciseCatalog";
const { Title, Text } = Typography;
const dateHere = (timeZone = "Asia/Shanghai") =>
  new Date().toLocaleDateString("sv-SE", { timeZone });
export function App() {
  const [registering, setRegistering] = useState(false);
  const [user, setUser] = useState<any>(null),
    [ready, setReady] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [catalog, setCatalog] = useState<Exercise[]>([]);
  const emptyContent = (): Content => ({
    actual_date: dateHere(),
    actual_time: null,
    notes: "",
    exercises: [],
    missing_information: {},
  });
  const {
    draft,
    content,
    setContent: setDraftContent,
    replace,
    flush: saveDraft,
    settle,
    restoring,
    dirty,
    saving,
    saveError,
  } = useWorkoutDraft(user?.id, emptyContent);
  const [remoteDraft, setRemoteDraft] = useState<Draft | null>(null);
  const [modelBusy, setModelBusy] = useState(false);
  const setContent = setDraftContent;
  const [preview, setPreview] = useState(false);
  const [profile, setProfile] = useState<any>({}),
    [aiConfig, setAiConfig] = useState<any>({}),
    [equipment, setEquipment] = useState<any[]>([]),
    [sharedEquipment, setSharedEquipment] = useState<any[]>([]);
  const [tab, setTab] = useState("home"),
    [custom, setCustom] = useState<Exercise | null | false>(false),
    [customForm] = Form.useForm(),
    [aiForm] = Form.useForm(),
    [aiTestOk, setAiTestOk] = useState(false),
    [equipmentName, setEquipmentName] = useState("");
  const run = async (fn: () => Promise<void>) => {
    setError("");
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const loadCatalog = async () => {
    let rows: Exercise[] = [];
    let offset = 0;
    while (true) {
      const r = await api<{ items: Exercise[]; total: number }>(
        `/exercises?limit=200&offset=${offset}`,
      );
      rows.push(...r.items);
      if (rows.length >= r.total) break;
      offset += 200;
    }
    setCatalog(rows);
  };
  const [revision, setRevision] = useState(0);
  const [selectedDate, setSelectedDate] = useState<string | undefined>();
  const [chatActive, setChatActive] = useState(false);
  const [newChatCount, setNewChatCount] = useState(0);
  const [accountOpen, setAccountOpen] = useState(false);
  const bumpRevision = () => setRevision((v) => v + 1);
  const load = async () => {
    await loadCatalog();
    setProfile(await api("/profile"));
    setAiConfig(await api("/ai-config"));
    setEquipment((await api("/user-equipment")).items);
    setSharedEquipment((await api("/equipment")).items);
  };
  useEffect(() => {
    api("/auth/me")
      .then((u) => {
        setUser(u);
        setCSRF(u.csrf_token);
        return load();
      })
      .catch((e) => {
        if (!(e instanceof ApiError && e.status === 401))
          setError(getErrorMessage(e));
      })
      .finally(() => setReady(true));
  }, []);
  useEffect(() => {
    if (
      profile.timezone &&
      !saveError &&
      !restoring &&
      !draft &&
      !dirty &&
      content.exercises.length === 0
    ) {
      replace(null, { ...content, actual_date: dateHere(profile.timezone) });
    }
  }, [profile.timezone]);
  const updateEntry = (index: number, change: any) =>
    setContent({
      ...content,
      exercises: content.exercises.map((e, i) =>
        i === index ? { ...e, ...change } : e,
      ),
    });
  const preference = async (e: Exercise, change: object) => {
    await api("/exercise-preferences", "PUT", {
      items: [
        {
          exercise_id: e.id,
          version: e.preference_version,
          available: e.available,
          ...change,
        },
      ],
    });
    await loadCatalog();
  };
  if (!ready) return <main>正在载入…</main>;
  if (!user)
    return (
      <main className="login">
        <Brand />
        {error && <Alert type="error" message={error} />}
        <Form
          key={registering ? "register" : "login"}
          onFinish={(v) =>
            void run(async () => {
              const u = await api(
                registering ? "/auth/register" : "/auth/login",
                "POST",
                v,
              );
              setCSRF(u.csrf_token);
              setUser(u);
              await load();
            })
          }
        >
          <Form.Item
            name="username"
            label="账号"
            rules={[{ required: true, whitespace: true }, { max: 100 }]}
          >
            <Input autoComplete="username" maxLength={100} />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[
              {
                validator(_, value: string | undefined) {
                  const length = Array.from(value || "").length;
                  if (!length) return Promise.reject(Error("请输入密码"));
                  if (registering && length < 12)
                    return Promise.reject(
                      Error(`密码至少需要12个字符（当前${length}个）`),
                    );
                  if (length > 1024)
                    return Promise.reject(
                      Error(`密码最多允许1024个字符（当前${length}个）`),
                    );
                  return Promise.resolve();
                },
              },
            ]}
          >
            <Input.Password
              autoComplete={registering ? "new-password" : "current-password"}
            />
          </Form.Item>
          {registering && (
            <Form.Item
              noStyle
              shouldUpdate={(previous, current) =>
                previous.password !== current.password
              }
            >
              {({ getFieldValue }) => (
                <Text type="secondary" aria-label="密码字符数">
                  至少12个字符；当前已输入{" "}
                  {Array.from(getFieldValue("password") || "").length} 个字符
                </Text>
              )}
            </Form.Item>
          )}
          {registering && (
            <Form.Item
              name="password_confirmation"
              label="确认密码"
              dependencies={["password"]}
              rules={[
                { required: true, message: "请再次输入密码" },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    return value === getFieldValue("password")
                      ? Promise.resolve()
                      : Promise.reject(Error("两次密码不一致"));
                  },
                }),
              ]}
            >
              <Input.Password autoComplete="new-password" />
            </Form.Item>
          )}
          <Button htmlType="submit" type="primary" loading={busy}>
            {registering ? "创建账号并登录" : "登录"}
          </Button>
          <Button
            type="link"
            disabled={busy}
            onClick={() => {
              setRegistering(!registering);
              setError("");
            }}
          >
            {registering ? "已有账号，返回登录" : "创建账号"}
          </Button>
        </Form>
      </main>
    );
  const record = (
    <>
      <fieldset
        disabled={
          restoring ||
          busy ||
          preview ||
          modelBusy ||

          (draft?.status !== undefined && draft.status !== "editable")
        }
        style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
      >
        <div role="status" aria-live="polite" style={{ marginBottom: 16 }}>
          {restoring
            ? "正在恢复待确认内容"
            : saveError
              ? "保存失败：" + saveError.message
              : saving
                ? "保存中"
                : dirty
                  ? "有未保存修改"
                  : draft
                    ? `已保存 · 版本 ${draft.version}`
                    : "尚未创建待确认内容"}
          {saveError && (
            <Button
              disabled={busy || restoring}
              onClick={() =>
                void run(async () => {
                  await saveDraft();
                })
              }
            >
              重试保存
            </Button>
          )}
          {draft && (
            <Button
              disabled={busy || saving || restoring}
              onClick={() =>
                void run(async () => {
                  setRemoteDraft(
                    await api<Draft>("/workout-drafts/" + draft.id),
                  );
                })
              }
            >
              查看服务端版本
            </Button>
          )}
        </div>
        <Space wrap>
          <Input
            aria-label="训练日期"
            type="date"
            value={content.actual_date}
            onChange={(e) =>
              setContent({ ...content, actual_date: e.target.value })
            }
          />
          <Input
            aria-label="训练时间"
            type="time"
            value={content.actual_time || ""}
            onChange={(e) =>
              setContent({ ...content, actual_time: e.target.value || null })
            }
          />
          <Button
            disabled={busy}
            onClick={() =>
              void run(async () => {
                if (dirty)
                  throw Error("存在本地未保存修改，请先保存或查看服务端版本");
                const id = localStorage.getItem("fitplan-draft-" + user.id);
                if (!id) throw Error("没有已保存待确认内容");
                const d = await api<Draft>("/workout-drafts/" + id);
                if (d.status !== "editable") throw Error("待确认内容已结束");
                replace(d);
              })
            }
          >
            恢复已保存待确认内容
          </Button>
        </Space>
        <p>
          <Text type="secondary">
            重量单位为
            kg，最多三位小数。未知重量或次数请留空，计重口径可保留“未知”。
          </Text>
        </p>
        {content.exercises.map((entry, index) => (
          <Card
            key={entry.id || index}
            className="entry"
            title={`${index + 1}. ${entry.name_snapshot || catalog.find((e) => e.id === entry.exercise_id)?.name || entry.custom_name || "选择动作"}`}
            extra={
              <Space>
                <Button
                  disabled={index === 0 || busy}
                  onClick={() => {
                    const es = [...content.exercises];
                    [es[index - 1], es[index]] = [es[index], es[index - 1]];
                    setContent({ ...content, exercises: es });
                  }}
                >
                  上移
                </Button>
                <Button
                  danger
                  disabled={busy}
                  onClick={() =>
                    setContent({
                      ...content,
                      exercises: content.exercises.filter(
                        (_, i) => i !== index,
                      ),
                    })
                  }
                >
                  删除动作
                </Button>
              </Space>
            }
          >
            <Space wrap>
              <Select
                aria-label="动作"
                style={{ width: 200 }}
                showSearch
                optionFilterProp="label"
                value={entry.exercise_id || "custom"}
                options={[
                  ...catalog
                    .filter((e) => !e.archived || e.id === entry.exercise_id)
                    .map((e) => ({ value: e.id, label: e.name })),
                  { value: "custom", label: "未知动作（确认时创建）" },
                ]}
                onChange={(v) =>
                  updateEntry(index, {
                    exercise_id: v === "custom" ? null : v,
                    custom_name: v === "custom" ? "" : null,
                    confirm_create: false,
                  })
                }
              />
              {!entry.exercise_id && (
                <>
                  <Input
                    aria-label="自定义动作名称"
                    value={entry.custom_name || ""}
                    onChange={(e) =>
                      updateEntry(index, { custom_name: e.target.value })
                    }
                  />
                  <Checkbox
                    checked={entry.confirm_create}
                    onChange={(e) =>
                      updateEntry(index, { confirm_create: e.target.checked })
                    }
                  >
                    确认创建自定义动作
                  </Checkbox>
                </>
              )}
              <Select
                aria-label="计重方式"
                value={entry.weight_mode}
                style={{ width: 150 }}
                options={Object.entries({
                  unknown: "计重方式未知",
                  external: "外部重量",
                  bodyweight: "自重",
                  added: "附加重量",
                  assisted: "辅助重量",
                }).map(([value, label]) => ({ value, label }))}
                onChange={(v) => updateEntry(index, { weight_mode: v })}
              />
              <Select
                aria-label="重量口径"
                value={entry.weight_scope}
                style={{ width: 150 }}
                options={[
                  { value: "unknown", label: "重量口径未知" },
                  { value: "total", label: "总重量" },
                  { value: "per_side", label: "单侧重量" },
                ]}
                onChange={(v) => updateEntry(index, { weight_scope: v })}
              />
            </Space>
            {entry.sets.map((s, j) => (
              <div className="group" key={s.id || j}>
                <Text>第 {j + 1} 组</Text>
                <Select
                  aria-label={`第${j + 1}组类型`}
                  value={s.kind}
                  options={[
                    { value: "working", label: "正式组" },
                    { value: "warmup", label: "热身组" },
                  ]}
                  onChange={(v) =>
                    updateEntry(index, {
                      sets: entry.sets.map((g, k) =>
                        k === j ? { ...g, kind: v } : g,
                      ),
                    })
                  }
                />
                <InputNumber
                  aria-label={`第${j + 1}组重量`}
                  placeholder="重量 kg"
                  min="0"
                  precision={3}
                  stringMode
                  value={s.weight_kg}
                  onChange={(v) =>
                    updateEntry(index, {
                      sets: entry.sets.map((g, k) =>
                        k === j ? { ...g, weight_kg: v } : g,
                      ),
                    })
                  }
                />
                <InputNumber
                  aria-label={`第${j + 1}组次数`}
                  placeholder="次数"
                  min={0}
                  precision={0}
                  value={s.reps}
                  onChange={(v) =>
                    updateEntry(index, {
                      sets: entry.sets.map((g, k) =>
                        k === j ? { ...g, reps: v } : g,
                      ),
                    })
                  }
                />
                <Input
                  aria-label={`第${j + 1}组备注`}
                  placeholder="组备注"
                  value={s.notes}
                  onChange={(e) =>
                    updateEntry(index, {
                      sets: entry.sets.map((g, k) =>
                        k === j ? { ...g, notes: e.target.value } : g,
                      ),
                    })
                  }
                />
                <Button
                  disabled={busy}
                  onClick={() =>
                    updateEntry(index, {
                      sets: entry.sets.filter((_, k) => k !== j),
                    })
                  }
                >
                  删除组
                </Button>
                <Button
                  disabled={j === 0 || busy}
                  onClick={() => {
                    const sets = [...entry.sets];
                    [sets[j - 1], sets[j]] = [sets[j], sets[j - 1]];
                    updateEntry(index, { sets });
                  }}
                >
                  上移
                </Button>
              </div>
            ))}
            <Button
              disabled={modelBusy}
              onClick={() =>
                updateEntry(index, { sets: [...entry.sets, blankSet()] })
              }
            >
              添加组
            </Button>
          </Card>
        ))}
        <Space wrap>
          <Button
            onClick={() =>
              setContent({
                ...content,
                exercises: [
                  ...content.exercises,
                  {
                    exercise_id: catalog.find((e) => !e.archived)?.id,
                    weight_mode: "unknown",
                    weight_scope: "unknown",
                    sets: [blankSet()],
                  },
                ],
              })
            }
          >
            添加动作
          </Button>
          <Button
            loading={busy}
            onClick={() =>
              void run(async () => {
                await saveDraft();
              })
            }
          >
            保存待确认内容
          </Button>
          <Button
            aria-label="完整预览并确认"
            type="primary"
            loading={busy}
            onClick={() =>
              void run(async () => {
                const latest = await saveDraft();
                if (!latest) throw Error("请先添加动作及训练组");
                setPreview(true);
              })
            }
          >
            完整预览并确认
          </Button>
          <Button
            danger
            disabled={(!draft && !dirty) || busy}
            onClick={() =>
              void run(async () => {
                const latest = await settle();
                if (latest)
                  await api(`/workout-drafts/${latest.id}/cancel`, "POST", {
                    version: latest.version,
                  });
                replace(null);
                localStorage.removeItem("fitplan-draft-" + user.id);
              })
            }
          >
            取消待确认内容
          </Button>
        </Space>
        <Input.TextArea
          aria-label="训练备注"
          placeholder="训练备注"
          value={content.notes}
          onChange={(e) => setContent({ ...content, notes: e.target.value })}
        />
      </fieldset>
    </>
  );
  const catalogEquipment = (
    <>
      <Title level={3}>实际可用器械</Title>
      <Space wrap>
        <Select
          placeholder="选择预置器械"
          style={{ width: 180 }}
          options={sharedEquipment.map((e) => ({ value: e.id, label: e.name }))}
          onChange={(id) =>
            void run(async () => {
              await api("/user-equipment", "POST", {
                equipment_id: id,
                name: sharedEquipment.find((e) => e.id === id).name,
              });
              await load();
            })
          }
        />
        <Input
          placeholder="自定义器械名称"
          value={equipmentName}
          onChange={(e) => setEquipmentName(e.target.value)}
        />
        <Button
          disabled={!equipmentName || busy}
          onClick={() =>
            void run(async () => {
              await api("/user-equipment", "POST", { name: equipmentName });
              setEquipmentName("");
              await load();
            })
          }
        >
          添加器械
        </Button>
      </Space>
      {equipment.map((e) => (
        <div className="group" key={e.id}>
          <Input
            aria-label="器械名称"
            defaultValue={e.name}
            onBlur={(ev) => {
              if (ev.target.value !== e.name)
                void run(async () => {
                  await api("/user-equipment/" + e.id, "PUT", {
                    name: ev.target.value,
                    equipment_id: e.equipment_id,
                    version: e.version,
                  });
                  await load();
                });
            }}
          />
          <Button
            disabled={busy}
            onClick={() =>
              void run(async () => {
                await api("/user-equipment/" + e.id, "DELETE", {
                  version: e.version,
                });
                await load();
              })
            }
          >
            移除
          </Button>
        </div>
      ))}
    </>
  );
  const catalogPage = (
    <Tabs
      items={[
        {
          key: "exercises",
          label: "动作",
          children: (
            <ExerciseCatalog
              items={catalog}
              busy={busy}
              create={() => {
                setCustom(null);
                customForm.resetFields();
              }}
              toggle={(e) =>
                void run(() =>
                  preference(e, {
                    available: !e.available,
                  }),
                )
              }
              edit={(e) => {
                setCustom(e);
                customForm.setFieldsValue({
                  ...e,
                  aliases: e.aliases.join("、"),
                  muscles: e.muscles.join("、"),
                  secondary_muscles: e.secondary_muscles.join("、"),
                  equipment: e.equipment.join("、"),
                });
              }}
              archive={(e) =>
                void run(async () => {
                  await api(`/exercises/${e.id}/archive`, "POST", {
                    version: e.version,
                  });
                  await loadCatalog();
                })
              }
            />
          ),
        },
        { key: "equipment", label: "器械", children: catalogEquipment },
      ]}
    />
  );
  const profileForm = (
    <Form
      layout="vertical"
      key={profile.version}
      initialValues={profile}
      onFinish={(v) =>
        void run(async () => {
          setProfile(
            await api("/profile", "PUT", { ...v, version: profile.version }),
          );
        })
      }
    >
      {[
        ["goal", "训练目标"],
        ["preferences", "偏好"],
        ["restrictions", "限制"],
        ["timezone", "时区"],
      ].map(([name, label]) => (
        <Form.Item key={name} name={name} label={label}>
          <Input />
        </Form.Item>
      ))}
      <Form.Item name="days_per_week" label="每周训练天数">
        <InputNumber min={1} max={7} />
      </Form.Item>
      <Form.Item name="minutes_per_session" label="单次时间（分钟）">
        <InputNumber min={1} max={1440} />
      </Form.Item>
      <Button htmlType="submit" loading={busy}>
        保存个人条件
      </Button>
    </Form>
  );
  const aiSettings = (
    <>
      <Title level={3}>AI 模型连接</Title>
      {aiConfig.configured ? (
        <Text>
          当前：{aiConfig.model} · {aiConfig.base_url}
          {aiConfig.has_api_key ? " · 已保存 API Key" : ""}
        </Text>
      ) : (
        <Text>未单独配置，对话使用服务端默认模型。</Text>
      )}
      <Form
        form={aiForm}
        layout="vertical"
        key={String(aiConfig.version)}
        initialValues={{
          base_url: aiConfig.base_url,
          model: aiConfig.model,
        }}
        onFinish={(v) =>
          void run(async () => {
            setAiTestOk(false);
            setAiConfig(
              await api("/ai-config", "PUT", {
                ...v,
                version: aiConfig.version ?? 1,
              }),
            );
            setAiTestOk(true);
          })
        }
      >
        <Form.Item name="vendor" label="模型厂商">
          <Select
            allowClear
            placeholder="选择厂商自动填入接口地址"
            options={[
              { value: "https://api.deepseek.com", label: "DeepSeek" },
              { value: "https://api.moonshot.cn/v1", label: "Kimi（月之暗面）" },
              {
                value: "https://dashscope.aliyuncs.com/compatible-mode/v1",
                label: "阿里云百炼",
              },
              { value: "https://api.openai.com/v1", label: "OpenAI" },
            ]}
            onChange={(v) => v && aiForm.setFieldsValue({ base_url: v })}
          />
        </Form.Item>
        <Form.Item
          name="base_url"
          label="接口地址"
          rules={[{ required: true, message: "请填写接口地址" }]}
        >
          <Input placeholder="https://api.deepseek.com" />
        </Form.Item>
        <Form.Item
          name="model"
          label="模型名称"
          rules={[{ required: true, message: "请填写模型名称" }]}
        >
          <Input placeholder="deepseek-chat" />
        </Form.Item>
        <Form.Item name="api_key" label="API Key">
          <Input.Password
            placeholder="留空沿用已保存的 Key"
            autoComplete="new-password"
          />
        </Form.Item>
        <Space wrap>
          <Button
            disabled={busy}
            onClick={() =>
              void run(async () => {
                setAiTestOk(false);
                await api("/ai-config/test", "POST", await aiForm.validateFields());
                setAiTestOk(true);
              })
            }
          >
            测试连接
          </Button>
          <Button htmlType="submit" loading={busy}>
            保存
          </Button>
        </Space>
        {aiTestOk && (
          <div>
            <Text type="success">测试通过，配置已可用。</Text>
          </div>
        )}
      </Form>
    </>
  );
  const settingsPage = (
    <Tabs
      className="settings-tabs"
      tabPosition="left"
      items={[
        { key: "profile", label: "个人条件", children: profileForm },
        { key: "ai", label: "AI 模型", children: aiSettings },
      ]}
    />
  );
  return (
    <main>
      <header>
        <div>
          <Brand />
        </div>
        <Space wrap>
          <Button onClick={() => setTab("catalog")}>动作与器械</Button>
          <Dropdown
            menu={{
              items: [
                { key: "settings", label: "设置" },
                { key: "account", label: "账号" },
                { type: "divider" },
                {
                  key: "logout",
                  label: "退出登录",
                  danger: true,
                  disabled: modelBusy,
                },
              ],
              onClick: ({ key }) => {
                if (key === "logout")
                  void run(async () => {
                    if (dirty || saving) await saveDraft();
                    await api("/auth/logout", "POST");
                    setUser(null);
                    setCSRF("");
                    replace(null);
                  });
                else if (key === "account") setAccountOpen(true);
                else setTab(key);
              },
            }}
          >
            <Button>{user.username}</Button>
          </Dropdown>
        </Space>
      </header>
      {error && (
        <Alert
          closable
          onClose={() => setError("")}
          type="error"
          message={error}
        />
      )}
      <section className={chatActive ? "workspace chatting" : "workspace"}>
        {chatActive && (
          <Button
            className="return-calendar"
            onClick={() => {
              setChatActive(false);
              setNewChatCount((v) => v + 1);
            }}
          >
            返回
          </Button>
        )}
        <div hidden={chatActive}>
          <TrainingCalendar
            onSelect={setSelectedDate}
            today={dateHere(profile.timezone)}
            revision={revision}
            edit={(w) => {
              void run(async () => {
                if (draft || dirty || saving || restoring)
                  throw Error("请先确认或取消当前待确认内容");
                const d = await api<Draft>("/workout-drafts", "POST", {
                  original_id: w.id,
                });
                replace(d);
                setTab("record");
              });
            }}
            add={(date) => {
              if (draft || dirty) {
                setError("请先确认或取消当前待确认内容");
                return;
              }
              replace(null, { ...emptyContent(), actual_date: date });
              setTab("record");
            }}
          />
        </div>
        <hr className="workspace-divider" hidden={chatActive} />
        <div className="conversation-workspace">
          {" "}
          <Conversation
            owner={user.id}
            onSend={() => setChatActive(true)}
            newChatSignal={newChatCount}
            selectedDate={selectedDate}
            onLock={setModelBusy}
            refresh={async () => {
              await load();
              bumpRevision();
            }}
            names={Object.fromEntries(catalog.map((e) => [e.id, e.name]))}
          />
        </div>
      </section>
      <Modal
        footer={null}
        centered
        styles={{ body: { maxHeight: "70dvh", overflowY: "auto" } }}
        title={
          {
            record: "记录训练",
            catalog: "动作与器械",
            settings: "设置",
          }[tab]
        }
        open={tab !== "home"}
        onCancel={() => setTab("home")}
        width={720}
      >
        {tab === "record" && record}
        {tab === "catalog" && catalogPage}
        {tab === "settings" && settingsPage}
      </Modal>
      <Modal
        title="账号"
        open={accountOpen}
        footer={null}
        onCancel={() => setAccountOpen(false)}
        destroyOnHidden
      >
        <Form
          layout="vertical"
          onFinish={(values) =>
            void run(async () => {
              const r = await api(
                "/auth/account",
                "PUT",
                Object.fromEntries(
                  Object.entries(values).filter(
                    ([, v]) => v !== undefined && v !== "",
                  ),
                ),
              );
              if (r.login_required) {
                setUser(null);
                setCSRF("");
              } else setUser({ ...user, username: r.username });
              setAccountOpen(false);
            })
          }
        >
          <Form.Item
            name="current_password"
            label="当前密码"
            rules={[{ required: true }]}
          >
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Form.Item name="username" label="新用户名">
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item
            name="password"
            label="新密码（至少12个字符，修改后重新登录）"
            rules={[{ min: 12 }]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Button htmlType="submit" type="primary" loading={busy}>
            保存账号信息
          </Button>
        </Form>
      </Modal>
      <Modal
        title="服务端当前待确认内容"
        open={!!remoteDraft}
        onCancel={() => setRemoteDraft(null)}
        okText="采用服务端内容（放弃本地修改）"
        onOk={() => {
          replace(remoteDraft?.status === "editable" ? remoteDraft : null);
          setRemoteDraft(null);
        }}
      >
        <p>本地编辑在关闭此窗口时仍会保留。采用服务端内容会放弃本地修改。</p>
        {remoteDraft && (
          <>
            <p>
              状态：{remoteDraft.status} · 版本 {remoteDraft.version}
            </p>
            <TrainingSummary content={remoteDraft.content} catalog={catalog} />
          </>
        )}
      </Modal>
      <Modal
        title="完整训练预览"
        open={preview}
        width={800}
        onCancel={() => setPreview(false)}
        confirmLoading={busy}
        okButtonProps={{ disabled: modelBusy }}
        okText="确认保存整次训练"
        onOk={() =>
          void run(async () => {
            if (modelBusy)
              throw Error("模型正在处理待确认内容，请等待本轮结束");
            const latest = await saveDraft();
            if (!latest) throw Error("没有可确认的待确认内容");
            await api(`/workout-drafts/${latest.id}/confirm`, "POST", {
              version: latest.version,
            });
            setPreview(false);
            replace(null, {
              ...emptyContent(),
              actual_date: dateHere(profile.timezone),
            });
            localStorage.removeItem("fitplan-draft-" + user.id);
            await loadCatalog();
            bumpRevision();
            setTab("home");
          })
        }
      >
        <TrainingSummary content={content} catalog={catalog} />
      </Modal>
      <Modal
        title={custom ? "编辑自定义动作" : "创建自定义动作"}
        open={custom !== false}
        onCancel={() => setCustom(false)}
        confirmLoading={busy}
        onOk={() => customForm.submit()}
      >
        <Form
          form={customForm}
          layout="vertical"
          onFinish={(v) =>
            void run(async () => {
              const body = { ...v };
              for (const key of [
                "aliases",
                "muscles",
                "secondary_muscles",
                "equipment",
              ])
                body[key] = (body[key] || "")
                  .split(/[、,，]/)
                  .map((s: string) => s.trim())
                  .filter(Boolean);
              await api(
                custom ? "/exercises/" + custom.id : "/exercises",
                custom ? "PUT" : "POST",
                custom ? { ...body, version: custom.version } : body,
              );
              setCustom(false);
              await loadCatalog();
            })
          }
        >
          {[
            ["name", "名称"],
            ["aliases", "别名"],
            ["muscles", "主要肌群"],
            ["secondary_muscles", "辅助肌群"],
            ["equipment", "器械"],
          ].map(([name, label]) => (
            <Form.Item
              key={name}
              name={name}
              label={label + (name === "name" ? "" : "（顿号分隔）")}
              rules={name === "name" ? [{ required: true }] : []}
            >
              <Input />
            </Form.Item>
          ))}
        </Form>
      </Modal>
    </main>
  );
}
