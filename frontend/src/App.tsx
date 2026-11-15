import { getErrorMessage } from "./errors";
import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Form,
  Input,
  InputNumber,
  Modal,
  message,
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
  type Workout,
  type Exercise,
} from "./api";
import { TrainingSummary } from "./TrainingSummary";
import { Brand } from "./Brand";
import { useWorkoutEditor } from "./useWorkoutEditor";
import { Conversation } from "./Conversation";
import { TrainingCalendar } from "./TrainingCalendar";
import { EquipmentCatalog } from "./EquipmentCatalog";
import { ExerciseCatalog } from "./ExerciseCatalog";
const { Title, Text } = Typography;
const dateHere = (timeZone = "Asia/Shanghai") =>
  new Date().toLocaleDateString("sv-SE", { timeZone });
export function App() {
  const [messageApi, messageContextHolder] = message.useMessage();
  const settingsPending = useRef(false);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [modal, modalContextHolder] = Modal.useModal();
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
    content,
    original,
    pending,
    active,
    setContent: setDraftContent,
    replace,
    discard,
    save: saveRecord,
    saving,
    saveError,
  } = useWorkoutEditor(user?.id, emptyContent);
  const [remoteWorkout, setRemoteWorkout] = useState<Workout | null>(null);
  const [modelBusy, setModelBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const setContent = setDraftContent;
  const [preview, setPreview] = useState(false);
  const [profile, setProfile] = useState<any>({}),
    [aiConfig, setAiConfig] = useState<any>({});
  const [tab, setTab] = useState("home"),
    [custom, setCustom] = useState<Exercise | null | false>(false),
    [customForm] = Form.useForm(),
    [aiForm] = Form.useForm(),
    [accountForm] = Form.useForm();
  const [catalogSection, setCatalogSection] = useState("exercises");
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
  const runSettings = async (
    fn: () => Promise<void | string>,
    success?: string,
  ) => {
    if (settingsPending.current) return;
    settingsPending.current = true;
    setSettingsBusy(true);
    messageApi.destroy();
    try {
      const result = await fn();
      void messageApi.success(result || success!);
    } catch (e) {
      void messageApi.error(getErrorMessage(e));
    } finally {
      settingsPending.current = false;
      setSettingsBusy(false);
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
  const [settingsSection, setSettingsSection] = useState("profile");
  const bumpRevision = () => setRevision((v) => v + 1);
  const meaningful = content.exercises.length > 0;
  const closeRecord = async () => {
    if (saving) return;
    if (tab === "record") discard();
    setTab("home");
  };
  const finishSave = async () => {
    await saveRecord();
    setPreview(false);
    setNotice("记录已保存");
    bumpRevision();
    setTab("home");
    await loadCatalog();
  };
  const openEditor = (workout: Workout | null, date?: string) => {
    const open = () => {
      replace(
        workout,
        workout
          ? undefined
          : {
              ...emptyContent(),
              actual_date: date || dateHere(profile.timezone),
            },
      );
      setNotice("");
      setTab("record");
    };
    open();
  };
  const load = async () => {
    await loadCatalog();
    setProfile(await api("/profile"));
    setAiConfig(await api("/ai-config"));
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
          active: e.active,
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
        {messageContextHolder}
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
        disabled={busy || preview || saving || pending}
        style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
      >
        <div role="status" aria-live="polite" style={{ marginBottom: 16 }}>
          {saveError
            ? saveError.message
            : saving
              ? "保存中"
              : active
                ? "尚未保存"
                : "新记录，尚未保存"}
          {saveError && (
            <Button disabled={busy} onClick={() => void run(finishSave)}>
              重试保存
            </Button>
          )}
          {original && !pending && (
            <Button
              disabled={busy || saving}
              onClick={() =>
                void run(async () => {
                  setRemoteWorkout(
                    await api<Workout>("/workouts/" + original.id),
                  );
                })
              }
            >
              查看最新记录
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
        </Space>
        <p>
          <Text type="secondary">
            重量单位为
            kg，最多三位小数。未知重量或次数请留空，单侧重量、自重或辅助重量等说明填写在组备注中。
          </Text>
        </p>
        {content.exercises.map((entry, index) => (
          <Card
            key={index}
            className="entry"
            title={`${index + 1}. ${entry.name || catalog.find((e) => e.id === entry.exercise_id)?.name || entry.custom_name || "选择动作"}`}
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
                  ...catalog.map((e) => ({ value: e.id, label: e.name })),
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
                    exercise_id: (catalog.find((e) => e.active) ?? catalog[0])
                      ?.id,
                    sets: [blankSet()],
                  },
                ],
              })
            }
          >
            添加动作
          </Button>
          <Button
            aria-label="保存记录"
            type="primary"
            loading={busy || saving}
            disabled={!meaningful}
            onClick={() => void run(finishSave)}
          >
            保存记录
          </Button>
          <Button
            aria-label="完整预览"
            disabled={!meaningful}
            onClick={() => setPreview(true)}
          >
            完整预览
          </Button>
          <Button
            danger
            disabled={!active || busy}
            onClick={() => {
              modal.confirm({
                title: "放弃未保存的修改？",
                okText: "放弃修改",
                cancelText: "继续编辑",
                onOk: () => {
                  replace(null);
                  setTab("home");
                  setNotice("");
                },
              });
            }}
          >
            放弃修改
          </Button>
        </Space>
        <Input.TextArea
          aria-label="训练备注"
          placeholder="训练备注"
          value={content.notes}
          onChange={(e) => setContent({ ...content, notes: e.target.value })}
        />
      </fieldset>
      {pending && !saving && (
        <Button
          type="primary"
          loading={busy}
          onClick={() => void run(finishSave)}
        >
          重试保存并核实结果
        </Button>
      )}
    </>
  );
  const catalogPage = (
    <Tabs
      activeKey={catalogSection}
      onChange={setCatalogSection}
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
                    active: !e.active,
                  }),
                )
              }
              edit={(e) => {
                setCustom(e);
                customForm.setFieldsValue({
                  ...e,
                  aliases: e.aliases,
                  primary_muscles: e.primary_muscles,
                  secondary_muscles: e.secondary_muscles,
                  equipment: e.equipment,
                });
              }}
            />
          ),
        },
        {
          key: "equipment",
          label: "器械",
          children: (
            <EquipmentCatalog
              active={tab === "catalog" && catalogSection === "equipment"}
              revision={revision}
            />
          ),
        },
      ]}
    />
  );
  const profileForm = (
    <Form
      layout="vertical"
      key={profile.version}
      initialValues={profile}
      onFinish={(v) =>
        void runSettings(async () => {
          setProfile(
            await api("/profile", "PUT", { ...v, version: profile.version }),
          );
        }, "个人条件已保存")
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
      <Button htmlType="submit" loading={settingsBusy}>
        保存个人条件
      </Button>
    </Form>
  );
  const aiSettings = (
    <>
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
          void runSettings(async () => {
            setAiConfig(
              await api("/ai-config", "PUT", {
                ...v,
                version: aiConfig.version ?? 1,
              }),
            );
          }, "AI 模型配置已保存")
        }
      >
        <Form.Item name="vendor" label="模型厂商">
          <Select
            allowClear
            placeholder="选择厂商自动填入接口地址"
            options={[
              { value: "https://api.deepseek.com", label: "DeepSeek" },
              {
                value: "https://api.moonshot.cn/v1",
                label: "Kimi（月之暗面）",
              },
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
            disabled={settingsBusy}
            onClick={() =>
              void runSettings(async () => {
                await api(
                  "/ai-config/test",
                  "POST",
                  await aiForm.validateFields(),
                );
              }, "连接测试通过")
            }
          >
            测试连接
          </Button>
          <Button htmlType="submit" loading={settingsBusy}>
            保存
          </Button>
        </Space>
      </Form>
    </>
  );
  const settingsPage = (
    <div className="settings-layout">
      <nav aria-label="设置类别">
        {[
          ["profile", "个人条件"],
          ["ai", "AI 模型"],
          ["security", "安全"],
        ].map(([key, label]) => (
          <button
            key={key}
            aria-current={settingsSection === key ? "location" : undefined}
            onClick={() =>
              document
                .getElementById("settings-" + key)
                ?.scrollIntoView({ block: "start", behavior: "smooth" })
            }
          >
            {label}
          </button>
        ))}
      </nav>
      <div
        className="settings-content"
        onScroll={(event) => {
          const container = event.currentTarget;
          const sections = Array.from(
            container.querySelectorAll<HTMLElement>("section"),
          );
          const current = sections
            .filter(
              (section) =>
                section.getBoundingClientRect().top <=
                container.getBoundingClientRect().top + 60,
            )
            .slice(-1)[0];
          setSettingsSection(
            container.scrollTop + container.clientHeight >=
              container.scrollHeight - 2
              ? "security"
              : current?.id.replace("settings-", "") || "profile",
          );
        }}
      >
        <section id="settings-profile">{profileForm}</section>
        <section id="settings-ai">{aiSettings}</section>
        <section id="settings-security">
          <Form
            form={accountForm}
            layout="vertical"
            onFinish={(values) =>
              void runSettings(async () => {
                const r = await api(
                  "/auth/account",
                  "PUT",
                  Object.fromEntries(
                    Object.entries(values).filter(
                      ([, v]) => v !== undefined && v !== "",
                    ),
                  ),
                );
                accountForm.resetFields();
                if (r.login_required) {
                  setUser(null);
                  setCSRF("");
                } else setUser({ ...user, username: r.username });
                return r.login_required
                  ? "账号信息已更新，请重新登录"
                  : "账号信息已保存";
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
            <Button htmlType="submit" type="primary" loading={settingsBusy}>
              保存账号信息
            </Button>
          </Form>
        </section>
      </div>
    </div>
  );
  return (
    <main>
      {modalContextHolder}
      {messageContextHolder}
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
                { type: "divider" },
                {
                  key: "logout",
                  label: "退出登录",
                  danger: true,
                  disabled: modelBusy || saving,
                },
              ],
              onClick: ({ key }) => {
                if (key === "logout")
                  void run(async () => {
                    await api("/auth/logout", "POST");
                    setUser(null);
                    setCSRF("");
                    setNotice("");
                  });
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
      <Button
        className="back-to-top"
        aria-label="返回顶部"
        title="返回顶部"
        onClick={() =>
          window.scrollTo({
            top: 0,
            behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
              ? "instant"
              : "smooth",
          })
        }
      >
        ⌃
      </Button>
      <section className="workspace">
        <div>
          {notice && (
            <Alert
              closable
              onClose={() => setNotice("")}
              type="success"
              message={notice}
              style={{ marginBottom: 12 }}
            />
          )}
          <TrainingCalendar
            today={dateHere(profile.timezone)}
            revision={revision}
            edit={(w) => openEditor(w)}
            add={(date) => openEditor(null, date)}
          />
        </div>
        <hr className="workspace-divider" />
        <div className="conversation-workspace">
          {" "}
          <Conversation
            owner={user.id}
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
        onCancel={() => void closeRecord()}
        width={720}
      >
        {tab === "record" && record}
        {tab === "catalog" && catalogPage}
        {tab === "settings" && settingsPage}
      </Modal>
      <Modal
        title="最新训练记录"
        open={!!remoteWorkout}
        onCancel={() => setRemoteWorkout(null)}
        okText="采用最新内容"
        onOk={() => {
          replace(remoteWorkout);
          setRemoteWorkout(null);
        }}
      >
        <p>采用最新内容会替换此浏览器中尚未保存的修改。</p>
        {remoteWorkout && (
          <TrainingSummary content={remoteWorkout.content} catalog={catalog} />
        )}
      </Modal>
      <Modal
        title="完整训练预览"
        open={preview}
        width={800}
        onCancel={() => setPreview(false)}
        confirmLoading={busy || saving}
        cancelText="取消"
        okText="保存记录"
        onOk={() => void run(finishSave)}
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
            ["primary_muscles", "主要肌群"],
            ["secondary_muscles", "辅助肌群"],
            ["equipment", "器械"],
            ["description", "动作说明"],
          ].map(([name, label]) => (
            <Form.Item
              key={name}
              name={name}
              label={
                label +
                (["name", "description"].includes(name) ? "" : "（顿号分隔）")
              }
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
