// --- FILE: frontend/vite.config.ts ---

/// <reference types="vitest/config" />

import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import {sentryVitePlugin} from '@sentry/vite-plugin'

// Source maps for Sentry (project regence-web): enabled only when built with the SENTRY_AUTH_TOKEN token (deployment,
// see DEPLOY.md, section 6). Maps are uploaded to Sentry and removed from the build - the site does not serve them; without the token
// (development, CI) the build is normal, nothing is sent. Organization and project - SENTRY_ORG / SENTRY_PROJECT.
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
    // hidden: maps exist, but the build files have no references to them; without the token the maps are not needed at all.
    build: {sourcemap: sentryToken ? 'hidden' : false},
    server: {
        host: '127.0.0.1',
        port: 3000,
        strictPort: true,
    },
    test: {
        environment: 'jsdom',
        // storage.ts - first: on Node 25+ replaces Node's own localStorage with the jsdom storage.
        setupFiles: ['./src/test/storage.ts', './src/test/setup.ts'],
        // npm run test:coverage (in CI): coverage is computed over all of src/, not only over the files
        // imported by tests - otherwise uncovered components would not get into the report at all.
        coverage: {
            provider: 'v8',
            include: ['src/**/*.{ts,tsx}'],
            exclude: ['src/**/__tests__/**', 'src/test/**', 'src/main.tsx', 'src/**/*.d.ts'],
            reporter: ['text-summary', 'text'],
            thresholds: {
                // Measured 22.11.2026: lines and statements ~98.8%, branches ~90.6%, functions ~92.6% - thresholds with a margin of 2-5 points.
                statements: 96,
                branches: 87,
                functions: 89,
                lines: 96,
            },
        },
    },
})