// --- FILE: frontend/vite.config.ts ---

/// <reference types="vitest/config" />

import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import {sentryVitePlugin} from '@sentry/vite-plugin'

// Source maps для Sentry (проект regence-web): включаются только при сборке с токеном SENTRY_AUTH_TOKEN (выкладка,
// см. DEPLOY.md, раздел 6). Карты загружаются в Sentry и удаляются из сборки — наружу сайт их не отдаёт; без токена
// (разработка, CI) сборка обычная, ничего не отправляется. Организация и проект — SENTRY_ORG / SENTRY_PROJECT.
const sentryToken = process.env.SENTRY_AUTH_TOKEN

export default defineConfig({
    plugins: [
        react(),
        tailwindcss(),
        ...(sentryToken ? [sentryVitePlugin({
            authToken: sentryToken,
            org: process.env.SENTRY_ORG ?? 'regence-club',
            project: process.env.SENTRY_PROJECT ?? 'regence-web',
            telemetry: false,
            sourcemaps: {filesToDeleteAfterUpload: ['./dist/**/*.map']},
        })] : []),
    ],
    // hidden: карты есть, но ссылки на них в файлах сборки нет; без токена карты не нужны вовсе.
    build: {sourcemap: sentryToken ? 'hidden' : false},
    server: {
        host: '127.0.0.1',
        port: 3000,
        strictPort: true,
    },
    test: {
        environment: 'jsdom',
        // storage.ts — первым: на Node 25+ подменяет собственный localStorage Node хранилищем jsdom.
        setupFiles: ['./src/test/storage.ts', './src/test/setup.ts'],
        // npm run test:coverage (в CI): покрытие считается по всему src/, а не только по файлам,
        // которые импортируют тесты, — иначе непокрытые компоненты не попали бы в отчёт вовсе.
        coverage: {
            provider: 'v8',
            include: ['src/**/*.{ts,tsx}'],
            exclude: ['src/**/__tests__/**', 'src/test/**', 'src/main.tsx', 'src/**/*.d.ts'],
            reporter: ['text-summary', 'text'],
            thresholds: {
                // Таск 17.6 (15.11.2026): покрытие 94/85/84/94 — пороги с запасом в 2–3 пункта, чтобы не сползало.
                statements: 92,
                branches: 82,
                functions: 80,
                lines: 92,
            },
        },
    },
})