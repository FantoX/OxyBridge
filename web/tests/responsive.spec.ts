import { expect, type Page } from "@playwright/test";
import { test, login, screenshots } from "./helpers";

test.use({ hasTouch: true });

async function fits(page: Page, label: string) {
  await expect
    .poll(
      () =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      { message: `${label} must fit the viewport` },
    )
    .toBe(true);
}

for (const width of [320, 360, 390, 768, 1024, 1440]) {
  test(`all main screens and editor fit ${width}px`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (
        message.type() === "error" &&
        /Content.Security.Policy|violates|Refused|Uncaught/i.test(
          message.text(),
        )
      ) {
        errors.push(message.text());
      }
    });
    await page.setViewportSize({ width, height: width < 768 ? 844 : 1000 });
    await login(page);
    for (const [path, title] of [
      ["/", "Everything is connected."],
      ["/workflows", "Workflows"],
      ["/runs", "Executions"],
      ["/connections", "Connections"],
      ["/schedules", "Schedules"],
      ["/templates", "Workflow templates"],
      ["/failed", "Failed work"],
      ["/audit", "Audit log"],
      ["/settings", "Settings"],
    ]) {
      await page.goto(path);
      await expect(
        page.getByRole("heading", { name: title, exact: true }),
      ).toBeVisible();
      await fits(page, `${path} at ${width}px`);
    }
    const workflows = await (
      await page.request.get("/api/v1/workflows")
    ).json();
    const routing = workflows.find(
      (workflow: { name: string }) => workflow.name === "Order routing",
    );
    expect(routing).toBeTruthy();
    const runs = await (await page.request.get("/api/v1/workflow-runs")).json();
    if (runs.length) {
      await page.goto("/runs/" + runs[0].id);
      await expect(page.locator(".execution-detail h1")).toBeVisible();
      await expect(page.locator(".inspect-body")).toBeVisible();
      await fits(page, `execution detail at ${width}px`);
    }
    await page.goto("/workflows/" + routing.id);
    await expect(page.locator(".react-flow__node")).toHaveCount(6);
    await page.getByRole("group", { name: /Order value > 500/ }).tap();
    await expect(
      page.getByRole("combobox", { name: "Operator", exact: true }),
    ).toHaveValue("greater");
    await fits(page, `editor inspector at ${width}px`);
    if (width === 390 && info.project.name === "chromium") {
      await page.screenshot({
        path: screenshots + "/mobile-builder.png",
        fullPage: true,
      });
    }
    await page
      .getByRole("button", { name: "Close inspector", exact: true })
      .tap();
    const publish = await page
      .getByRole("button", { name: "Publish", exact: true })
      .boundingBox();
    expect(publish).not.toBeNull();
    expect(publish!.x + publish!.width).toBeLessThanOrEqual(width);
    await page.getByRole("button", { name: "Add node", exact: true }).tap();
    await expect(
      page.getByRole("button", { name: "Close node palette" }),
    ).toBeVisible();
    await fits(page, `node palette at ${width}px`);
    await page.getByRole("button", { name: "Close node palette" }).tap();
    await page.goto("/connections");
    await page
      .getByRole("button", { name: "Add connection", exact: true })
      .tap();
    await expect(page.getByRole("dialog")).toBeVisible();
    const dialog = await page.getByRole("dialog").boundingBox();
    expect(dialog!.x).toBeGreaterThanOrEqual(0);
    expect(dialog!.x + dialog!.width).toBeLessThanOrEqual(width);
    await fits(page, `connection dialog at ${width}px`);
    await page.getByRole("button", { name: "Close dialog" }).tap();
    if (width < 768) {
      await page.getByRole("button", { name: "Open navigation" }).tap();
      await page.getByRole("link", { name: "Overview", exact: true }).tap();
      await expect(page.locator(".sidebar.mobile-open")).toHaveCount(0);
      await expect(
        page.getByRole("heading", { name: "Everything is connected." }),
      ).toBeVisible();
    }
    expect(errors).toEqual([]);
  });
}
