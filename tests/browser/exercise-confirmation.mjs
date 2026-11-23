import { runE2E, expect } from "./e2e-harness.mjs";

await runE2E("exercise-confirmation", async ({ login, scenario }) => {
  for (const status of ["pending", "confirmed"]) {
    await scenario(`exercise fields visible before and after confirmation: ${status}`, async () => {
      const { page } = await login();
      const action = {
        action_id: "exercise-action", operation: "add_exercise", tool_name: "add_exercise",
        status, version: 1, summary: "新增个人动作T杠划船并加入选择动作",
        details: { name: "T杠划船", aliases: "T Bar Row", primary_muscles: "背阔肌、菱形肌",
          secondary_muscles: "", equipment: "T杠", description: "保持躯干稳定" },
        result: null, allowed_operations: status === "pending" ? ["confirm", "cancel"] : [],
      };
      await page.route("**/api/conversations/exercise-preview", route => route.fulfill({ json: {
        id: "exercise-preview", title: "动作确认预览", messages: [
          { id: "input", role: "user", content: "新增T杠划船动作", sequence: 1, turn_id: "turn" },
        ], actions: [action], turns: [{ id: "turn", status: "succeeded", mode: "edit",
          result: { type: "confirmation_required", action_id: action.action_id } }],
      } }));
      await page.route("**/api/conversations?limit=200", route => route.fulfill({ json: {
        items: [{ id: "exercise-preview", title: "动作确认预览" }],
      } }));
      await page.getByLabel("展开历史对话").click();
      await page.getByText("动作确认预览", { exact: true }).click();
      const card = page.locator('[data-operation="add_exercise"]');
      for (const width of [1280, 390]) {
        await page.setViewportSize({ width, height: 844 });
        await expect(card.getByText("别名：T Bar Row", { exact: true })).toBeVisible();
        await expect(card.getByText("主要肌群：背阔肌、菱形肌", { exact: true })).toBeVisible();
        await expect(card.getByText("辅助肌群：未填写", { exact: true })).toBeVisible();
        await expect(card.getByText("器械：T杠", { exact: true })).toBeVisible();
        await expect(card.getByText("说明：保持躯干稳定", { exact: true })).toBeVisible();
        await expect(card.locator("details")).toHaveCount(0);
      }
      await expect(card.getByText(status === "pending" ? "确认后加入选择动作。" : "已加入选择动作。", { exact: true })).toBeVisible();
      await expect(card.getByRole("button", { name: "确认执行新增动作", exact: true })).toHaveCount(status === "pending" ? 1 : 0);
    });
  }
});
