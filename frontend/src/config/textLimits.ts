// --- FILE: frontend/src/config/textLimits.ts ---
// Maximum length of player-written texts and the correspondence page size. The server decides: the numbers here repeat its
// checks so that the input field does not accept too much and the player does not get a rejection after sending. If changed on the server -
// change them here too. Used by the social input fields (components/social/*).

/** Feed post - src/services/feed.py, BODY_MAX. */
export const FEED_POST_MAX = 2000;
/** Post comment - src/services/feed.py, COMMENT_MAX. */
export const FEED_COMMENT_MAX = 500;
/** Direct message - src/services/direct_messages.py, BODY_MAX. */
export const DIRECT_MESSAGE_MAX = 1000;
/**
 * Messages per correspondence page - src/services/direct_messages.py, PAGE: a full page means there are earlier
 * messages (the "Show earlier" button).
 */
export const DIRECT_MESSAGES_PAGE = 50;
/** Report comment, appeal text and suggested translation - max_length=300 in src/api/moderation.py. */
export const MODERATION_TEXT_MAX = 300;
/** Team name - src/services/league.py, NAME_MAX. */
export const TEAM_NAME_MAX = 30;
/** Player search string - max_length=30 in GET /social/search (src/api/social.py). */
export const PLAYER_SEARCH_MAX = 30;
