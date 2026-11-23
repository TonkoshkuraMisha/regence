// Build of the waiting-page Worker (needed by cf deploy): the Cloudflare plugin takes its settings from cloudflare.config.ts.
import { defineConfig } from "vite";
import { cloudflare } from "@cloudflare/vite-plugin";

export default defineConfig({ plugins: [cloudflare()] });
