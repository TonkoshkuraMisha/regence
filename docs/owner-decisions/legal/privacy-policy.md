# Privacy Policy — regence

> **DRAFT for legal review. Not in force until the `{{…}}` placeholders are filled in and a lawyer has reviewed it.**
> It describes what the platform really does as of 28.11.2026 (checked against the code; sources in
> `docs/owner-decisions/02-legal-and-licenses.md` and `README.md` in this folder). If the product changes, change this
> text in the same pull request (rule 6 in `CLAUDE.md`). The Ukrainian version is `privacy-policy.uk.md`.
> Version date: `{{YYYY-MM-DD}}`.

## 1. Who is responsible

The controller of your personal data is **{{OPERATOR_NAME}}**, {{OPERATOR_ADDRESS}} (“we”). Contact for privacy
questions and for exercising your rights: **{{CONTACT_EMAIL}}**. {{EU_UK_REPRESENTATIVE_IF_REQUIRED}}

## 2. What we collect and why

| Data | Why | Legal basis | How long |
|---|---|---|---|
| Username, password (stored only as a hash), settings (language, theme, avatar) | create and run your account | contract | until you delete the account |
| Kid mode: an account registered as “under 16” is created in kid mode, with the guardian code stored only as a hash; the age itself and the date of birth are not stored. The guardian's consent is recorded together with the consent to these documents (version and time) | apply the age rules and kid mode | legal obligation; consent of the guardian | until you delete the account |
| E-mail (optional, only after you confirm it) | confirm the address, reset the password, notices you ask for | contract; your consent for optional mail | until you remove it or delete the account |
| Country (optional) | national standings and conferences | your consent | until you remove it or delete the account |
| Invitation code you registered with (if any) | show a partner club or blogger how many invited people started to play — as a number, without names | legitimate interest | until you delete the account |
| Games, moves, ratings, lesson, puzzle and training progress, tournaments, achievements, repertoires, your bot settings | provide the Service | contract | until you delete the account; your finished games stay in your opponents' history under an anonymous name |
| **Imported games** and, if you switch the daily import on, your **username on lichess or chess.com** with the time and outcome of the last import | bring your own games for analysis and personal puzzles | contract (you ask for it) | until you delete the game, switch the import off or delete the account |
| **Fair-play data**: move time, window focus, premoves, network delay | detect engine use and let you appeal | legitimate interest (fair games) | raw data **90 days** after the game; afterwards only a summary |
| **IP address** when you open a game connection | find several accounts on one address (fair play) | legitimate interest | **12 hours** |
| Sign-in cookie `regence_refresh` and its server record | keep you signed in | contract (strictly necessary) | 30 days since last use |
| Server logs: time, request number, your account number, the action and its result (no passwords, no message texts) | keep the Service working, investigate failures and abuse | legitimate interest | {{LOG_RETENTION}} |
| Product events: the kind of event, the player and the day | understand which functions are used | legitimate interest | {{RETENTION_PRODUCT_EVENTS}} |
| Error reports from the page: error text, page address, request numbers — no screen recording | fix failures | legitimate interest | in the server logs (as above) and, if enabled, in our error-tracking account ({{SENTRY_RETENTION}}) |
| Your agreement to these documents: version and time | prove consent | legal obligation / legitimate interest | until you delete the account |
| Text you write (messages, posts, comments, reports) | provide the function; moderation | contract; legitimate interest | until deleted; held and flagged texts are visible to moderators |
| **Sponsor status** (only if you link a donation): the badge, since when, and the reference that links the donation to your account (member identity at the platform or the transaction reference) | show the sponsor badge | your consent | until you unlink it or delete the account; {{DONATION_RECORDS_RETENTION}} |

We do **not** sell data, show advertising, use third-party advertising or tracking cookies, fingerprint devices or
record screens. Donations are processed by the platform or network you choose; we never receive card or bank details.

## 3. Cookies and similar storage

We set **one cookie**: `regence_refresh` (HttpOnly, Secure, SameSite=Strict), which keeps you signed in. It is
strictly necessary, so no consent banner is needed. Your browser's local storage keeps settings you choose (language,
theme, board options), the usernames you typed for game import and, for bot games in progress, a local snapshot. We
will not add analytics or advertising cookies without asking for your consent first.

## 4. Who receives data (recipients and transfers)

| Recipient | What | Where |
|---|---|---|
| Hosting provider {{HOSTING_PROVIDER}} | all data of the Service (servers) | {{HOSTING_COUNTRY}} |
| Backup storage {{BACKUP_PROVIDER}} | copies of the database | {{BACKUP_COUNTRY}} |
| Cloudflare, Inc. | traffic passes through its network (DNS, protection, caching); technical request data | worldwide; its safeguards: {{CLOUDFLARE_TRANSFER_BASIS}} |
| Sentry (error tracking), if enabled | error reports | {{SENTRY_REGION}} |
| E-mail provider {{EMAIL_PROVIDER}} | your e-mail address and the message, when we send you mail | {{EMAIL_COUNTRY}} |
| lichess.org and chess.com (only when you import games) | **only the username you typed**, to fetch your public games through their open interfaces; no password, no token, no other data | their servers, under their own policies |
| Public endgame tables (Lichess) | only chess positions, never player data | — |
| Donation platform {{DONATION_PLATFORM}} (only if you donate there) | what you give the platform yourself; we receive only what is needed to link the badge | as in its policy |

Where data go outside the EU/EEA/UK, we rely on an adequacy decision, the EU–US Data Privacy Framework or standard
contractual clauses, as stated in the table. We do not give data to authorities unless the law obliges us.
Cryptocurrency transfers are recorded on a public blockchain by their nature; we do not publish who sent which
transfer.

## 5. Automated decisions

Our fair-play measures compute signals and may **flag** an account. **A flag alone never closes an account:** a person
reviews it, and you can appeal. Automatic text filters only hold or mark messages for a moderator.

## 6. Your rights

You may at any time: see and **download** your data and **delete** your account (Settings → My data); correct data in
your profile; ask us to restrict or stop processing based on legitimate interest; withdraw consent you gave (for
e-mail, country, daily import and the sponsor link, in Settings or by writing to us); ask for a copy in a
machine-readable form (portability). Write to `{{CONTACT_EMAIL}}`; we answer within one month. You may complain to a
supervisory authority: in the EU, the authority of your country; in the UK, the ICO; in Ukraine, the Ukrainian
Parliament Commissioner for Human Rights.

**Deletion.** The account closes at once (you are signed out everywhere and others no longer see it). For **10 days**
you can restore it by signing in; then the personal data are erased: the username becomes anonymous
(`deleted_<number>`), the password stops working, e-mail, country, messages, posts, follows, team membership, imported
games, import subscriptions, repertoires, achievements and progress are removed; games stay in opponents' history under
the anonymous name. Copies in backups disappear when the backups expire ({{BACKUP_RETENTION_DAYS}} days).

## 7. Children

You must be **16 or older** to register on your own. A child under 16 may use the Service only if a parent or legal
guardian registers the account and gives consent; such an account works in **kid mode** (no free-text chat, no private
messages, no feed, no room chat), and only the guardian code turns it off. We collect from a child no more than from
any player (no date of birth and no photo are asked). If we learn that a child registered without a guardian, we switch
the account to kid mode or delete it. Guardians may ask for the child's data or its deletion at `{{CONTACT_EMAIL}}`.

## 8. Security

Passwords and guardian codes are stored as hashes; sign-in tokens in the server's memory store are kept as hashes;
connections are encrypted (HTTPS); access to servers is limited; the database is backed up regularly, with a copy at a
second provider (backups are kept for {{BACKUP_RETENTION_DAYS}} days, so deleted data can remain in them until they
expire). No system is perfectly secure; if a breach puts you at risk, we will inform you and the authority as the law
requires.

## 9. Changes

When we change this Policy in substance we publish a new version date and tell registered players at their next login.

## 10. Contact

{{OPERATOR_NAME}} · {{OPERATOR_ADDRESS}} · {{CONTACT_EMAIL}}
