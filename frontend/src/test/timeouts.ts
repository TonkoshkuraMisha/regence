// --- FILE: frontend/src/test/timeouts.ts ---
// Time limit of the heavy page-flow tests: a whole game with a bot, a walk through every page of the menu, a mate course
// lesson. On an idle machine they take 1-5 s, close to Vitest's default 5 s limit; under load (a full parallel run on a busy
// laptop, coverage measurement in CI) they ran out of time without any error in the code. Only such flow tests get it;
// ordinary tests keep the default limit, so a real hang still shows up quickly.

/** Per-test limit (ms) for heavy page-flow tests: it("...", fn, SLOW_FLOW_TIMEOUT_MS) or describe("...", {timeout}, fn). */
export const SLOW_FLOW_TIMEOUT_MS = 20_000;
