import {
  test as base,
  expect,
  type Page,
  type BrowserContext,
} from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

export const credentials =
  process.env.E2E_EMAIL && process.env.E2E_PASSWORD
    ? { email: process.env.E2E_EMAIL, password: process.env.E2E_PASSWORD }
    : JSON.parse(readFileSync(resolve("../.local/login.json"), "utf8"));
export const screenshots = resolve("../docs/screenshots");
mkdirSync(screenshots, { recursive: true });

async function signIn(page: Page) {
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Email address" })
    .fill(credentials.email);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Everything is connected." }),
  ).toBeVisible();
}

type SessionState = Awaited<ReturnType<BrowserContext["storageState"]>>;
export const test = base.extend<object, { session: SessionState }>({
  session: [
    async ({ browser }, use) => {
      const context = await browser.newContext({
        baseURL: process.env.E2E_BASE_URL || "http://localhost:5174",
      });
      await signIn(await context.newPage());
      await use(await context.storageState());
      await context.close();
    },
    { scope: "worker" },
  ],
  storageState: async ({ session }, use) => use(session),
});

export async function login(page: Page) {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Everything is connected." }),
  ).toBeVisible();
}
