// Waiting page (Worker regence-landing): serves a placeholder on regence.club and www until the site launches.
// The domains are the same ones that were bound to the Worker before this file existed; after the site launches unbind the Worker
// (DEPLOY.md, the Cloudflare section), otherwise it will intercept all traffic.
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
