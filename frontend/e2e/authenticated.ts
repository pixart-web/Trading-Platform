import { test as base, expect } from "@playwright/test";

export const test = base.extend<{ authenticated: void }>({
  authenticated: [async ({ context, baseURL }, use) => {
    const response = await context.request.post(`${baseURL}/api/auth/login`, {
      data: { user: "operator", pin: "908172" }, // pragma: allowlist secret; disposable E2E PIN
    });
    expect(response.status()).toBe(200);
    await use();
  }, { auto: true }],
});
export { expect } from "@playwright/test";
