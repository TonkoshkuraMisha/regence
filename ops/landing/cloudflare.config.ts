// Страница ожидания (Worker regence-landing): отдаёт заглушку на regence.club и www до запуска сайта.
// Домены те же, что были привязаны к Worker до появления этого файла; после запуска сайта Worker отвязать
// (DEPLOY.md, раздел о Cloudflare), иначе он будет перехватывать весь трафик.
import { defineConfig } from "cf/config";
import * as entrypoint from "./src/index.js" with { type: "cf-worker" };

export default defineConfig({
  accountId: "15c2fc433bfda78b7991dd059a98ed41",
  worker: {
    name: "regence-landing",
    compatibilityDate: "2026-11-01",
    entrypoint,
    domains: ["regence.club", "www.regence.club"],
  },
});
