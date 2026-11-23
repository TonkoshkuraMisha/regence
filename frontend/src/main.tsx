// --- FILE: frontend/src/main.tsx ---
// Client entry point: loads styles, sets the page background before the first paint, registers phone installation
// and renders the app (App) inside the router.

// First: migrate settings from the old platform name (michess_… → regence_…) before the modules that read settings.
import './migrateStorage'
import { initSentry } from './services/sentry'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { applyPageBackground } from './config/pageBackground'
import { initPwa } from './services/pwa'
import { installClientErrorReporting } from './services/clientErrors'

// Page background (task 18.1) — before the first paint so it does not flicker.
applyPageBackground()
// Sentry (project regence-web) — only when VITE_SENTRY_DSN is set; before the first paint so it catches its failures.
initSentry()
// Page error reports and the event trail for diagnosing «the page suddenly refreshed» (clientErrors.ts).
installClientErrorReporting()
// Add-to-home-screen installation and the offline page (task 24.2); the service worker only in the production build.
initPwa()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)