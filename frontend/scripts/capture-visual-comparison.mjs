import { chromium } from "@playwright/test";
import { resolve } from "node:path";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1536, height: 1120 }, deviceScaleFactor: 1 });
await page.goto(new URL(`file:///${resolve("../docs/ui/visual-comparison.html").replaceAll("\\", "/")}`).toString());
await page.screenshot({ path: resolve("../docs/ui/assets/visual-comparison.png"), fullPage: true });
await browser.close();
