import { expect } from "@playwright/test";
import { test, login, screenshots } from "./helpers";

test("login, real workflow editing, connection, validation, publish, run and inspect", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  await page.getByRole("link", { name: "Workflows", exact: true }).click();
  await page
    .getByRole("button", { name: "Create workflow", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Workflow name", exact: true })
    .fill("Order intake mapping");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Create workflow", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your workflow starts here." }),
  ).toBeVisible();
  const createdWorkflowId = new URL(page.url()).pathname.split("/").at(-1)!;
  await page.getByRole("button", { name: "Add your first node" }).click();
  await page
    .getByRole("button", { name: /Manual trigger Start when you need to/ })
    .click();
  await page.getByRole("button", { name: "Add node", exact: true }).click();
  await page.getByRole("button", { name: /Transform Map and shape/ }).click();
  const mapping = page.getByLabel("Field mapping", { exact: false });
  await mapping.fill("{");
  await expect(
    page.getByRole("button", { name: "Publish", exact: true }),
  ).toBeDisabled();
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Keep your unfinished edits?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Keep editing", exact: true }).click();
  await page.getByRole("group", { name: "Manual trigger" }).click();
  await page.getByRole("group", { name: "Transform" }).click();
  await expect(mapping).toHaveValue("{");
  await mapping.fill(
    '{"received": "{{ trigger.body.order_id }}", "amount": "{{ trigger.body.total }}"}',
  );
  // Connect actual canvas handles, rather than bypassing the editor with an API-created graph.
  const source = page.locator('[data-handleid="success"]').first();
  const target = page.locator(".react-flow__handle-top").first();
  await page.getByRole("button", { name: "Fit view" }).click();
  const from = await source.boundingBox(),
    to = await target.boundingBox();
  expect(from).not.toBeNull();
  expect(to).not.toBeNull();
  await page.mouse.move(from!.x + from!.width / 2, from!.y + from!.height / 2);
  await page.mouse.down();
  await page.mouse.move(to!.x + to!.width / 2, to!.y + to!.height / 2, {
    steps: 15,
  });
  await page.mouse.up();
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Validate", exact: true }).click();
  await expect(
    page.getByText(
      "Workflow is valid. All nodes are connected and configured.",
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "Publish", exact: true }).click();
  await expect(page.getByText(/Published version \d+\./)).toBeVisible();
  await page.getByRole("button", { name: "Test run", exact: true }).click();
  await page
    .getByRole("button", { name: "Start test run", exact: true })
    .click();
  await expect(page.locator(".console-heading .status")).toHaveText(
    "Succeeded",
  );
  await page
    .getByRole("link", { name: "Open execution", exact: false })
    .click();
  await expect(
    page.getByRole("heading", { name: /Order intake mapping/ }),
  ).toBeVisible();
  await expect(page.locator(".inspect-body")).toContainText("ORD-2041");
  await expect(page.locator(".inspect-body")).toContainText("749");
  await page.screenshot({
    path: screenshots + "/execution.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
  const csrf = await page.evaluate(
    () =>
      document.cookie
        .split("; ")
        .find((v) => v.startsWith("ob_csrf="))
        ?.split("=")[1] || "",
  );
  const archived = await page.request.delete(
    "/api/v1/workflows/" + createdWorkflowId,
    { headers: { "X-CSRF-Token": csrf } },
  );
  expect(archived.status()).toBe(200);
});

test("template builder, dashboard, responsive views and management screens render", async ({
  page,
}) => {
  await login(page);
  await page.screenshot({
    path: screenshots + "/dashboard.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "Workflows", exact: true }).click();
  await page
    .getByRole("heading", { name: "Order routing", exact: true })
    .click();
  await expect(page.locator(".react-flow__node")).toHaveCount(6);
  await page.getByRole("group", { name: /Order value > 500/ }).click();
  await expect(
    page.getByRole("combobox", { name: "Operator", exact: true }),
  ).toHaveValue("greater");
  await page.screenshot({ path: screenshots + "/builder.png", fullPage: true });
  await page.getByRole("link", { name: "Connections", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Connections", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Schedules", exact: true }).click();
  await expect(
    page.getByText(/Unattended schedules require the continuous scheduler/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Add schedule", exact: true }).click();
  await page
    .getByRole("button", { name: "Preview next five runs", exact: true })
    .click();
  await expect(page.locator(".schedule-preview > div")).toHaveCount(5);
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  await page.getByRole("link", { name: "Templates", exact: true }).click();
  await expect(page.locator(".template-card")).toHaveCount(3);
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "System", exact: true }).click();
  await expect(
    page.getByText("PostgreSQL durable outbox", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Everything is connected." }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Switch to dark theme", exact: true })
    .click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({
    path: screenshots + "/dashboard-dark.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Switch to light theme", exact: true })
    .click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "Everything is connected." }),
  ).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > innerWidth,
  );
  expect(overflow).toBe(false);
  await page.screenshot({ path: screenshots + "/mobile.png" });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Executions", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Executions", exact: true }),
  ).toBeVisible();
});
