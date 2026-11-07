import { expect, test } from "@playwright/test";

test("protected pages require a real PIN session", async ({ page, context, baseURL }) => {
  await page.goto("/paper");
  await expect(page).toHaveURL(/\/login\?next=/);
  const rejected = await context.request.post(`${baseURL}/api/auth/login`, {
    data: { user: "operator", pin: "000000" }, // pragma: allowlist secret; deliberately incorrect PIN
  });
  expect(rejected.status()).toBe(401);
  const accepted = await context.request.post(`${baseURL}/api/auth/login`, {
    data: { user: "operator", pin: "908172" }, // pragma: allowlist secret; disposable E2E PIN
  });
  expect(accepted.status()).toBe(200);
  const cookie = (await context.cookies()).find(value => value.name === "pa_session");
  expect(cookie).toMatchObject({ httpOnly: true, secure: true, sameSite: "Lax" });
  await page.route("**/api/market-data/paper/accounts", route => route.fulfill({ json: [] }));
  await page.goto("/paper");
  await expect(page.getByRole("heading", { name: "PAPER — simulated execution", exact: true })).toBeVisible();
});
