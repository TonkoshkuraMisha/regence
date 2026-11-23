// --- FILE: frontend/src/migrateStorage.ts ---
// Imported first in src/main.tsx: the settings modules (language, board, sound) read storage already at import time, so
// the key migration michess_… → regence_… (services/storageMigration.ts) must happen before they load.

import {migrateLegacyStorage} from './services/storageMigration';

migrateLegacyStorage();
