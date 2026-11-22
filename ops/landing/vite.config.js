// Сборка Worker страницы ожидания (нужна cf deploy): плагин Cloudflare берёт настройки из cloudflare.config.ts.
import { defineConfig } from "vite";
import { cloudflare } from "@cloudflare/vite-plugin";

export default defineConfig({ plugins: [cloudflare()] });
