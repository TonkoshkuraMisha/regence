// --- FILE: frontend/src/config/passwordRules.ts ---
// Password rules the client checks before the request, to show the error immediately. The server decides: min_length
// in the registration, change and reset password schemas - PASSWORD_MIN_LENGTH in src/schemas/user.py.
// Used by the settings page (Settings.tsx) and the password reset page opened from an email link (EmailLinkPages.tsx).

/** Minimum length of a new password; must match min_length on the server. */
export const MIN_PASSWORD_LENGTH = 8;
