// Resolve the existing frontend dependency without another node_modules tree.
import { createRequire } from "node:module";
const require = createRequire(new URL("../../frontend/package.json", import.meta.url));
export const { chromium, expect } = require("@playwright/test");
