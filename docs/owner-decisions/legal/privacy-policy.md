# Privacy Policy — regence

> **DRAFT for legal review. Not in force until the `{{…}}` placeholders are filled in and a lawyer has reviewed it.**
> It describes what the platform really does as of 23.11.2026 (checked against the code; sources in
> `docs/owner-decisions/02-legal-and-licenses.md`). If the product changes, change this text in the same pull request
> (rule 6 in `CLAUDE.md`).
> Version date: `{{YYYY-MM-DD}}`.

## 1. Who is responsible

The controller of your personal data is **{{OPERATOR_NAME}}**, {{OPERATOR_ADDRESS}} (“we”). Contact for privacy
questions and for exercising your rights: **{{CONTACT_EMAIL}}**. {{EU_UK_REPRESENTATIVE_IF_REQUIRED}}

## 2. What we collect and why

| Data | Why | Legal basis | How long |
|---|---|---|---|
| Username, password (stored only as a hash), settings (language, theme, avatar) | create and run your account | contract | until you delete the account |
| E-mail (optional) | confirm the address, reset the password, notices you ask for | contract; your consent for optional mail | until you remove it or delete the account |
| Country (optional) | national standings and conferences | your consent | until you remove it or delete the account |
| Games, moves, ratings, lesson, puzzle and training progress, tournaments, imported games | provide the Service | contract | until you delete the account; your finished games stay in your opponents' history under an anonymous name |
| **Fair-play data**: move time, window focus, premoves, network delay | detect engine use and let you appeal | legitimate interest (fair games) | raw data **90 days** after the game; afterwards only a summary |
| **IP address** when you open a game connection | find several accounts on one address (fair play) | legitimate interest | **12 hours** |
| Sign-in cookie `regence_refresh` and its server record | keep you signed in | contract (strictly necessary) | 30 days since last use |
| Product events: the kind of event, the player and the day | understand which functions are used | legitimate interest | {{RETENTION_PRODUCT_EVENTS}} |
| Error reports: error text, page address, request numbers — no personal data, no screen recording | fix failures | legitimate interest | as set in our error-tracking account ({{SENTRY_RETENTION}}) |
| Your agreement to these documents: version and time | prove consent | legal obligation / legitimate interest | until you delete the account |
| Text you write (messages, posts, comments, reports) | provide the function; moderation | contract; legitimate interest | until deleted; held and flagged texts are visible to moderators |
| Payment data (only when paid plans exist) | handled by the payment provider, not by us; we receive the status of your subscription | contract | as required by tax law |

We do **not** sell data, show advertising, use third-party advertising or tracking cookies, fingerprint devices or
record screens.

## 3. Cookies and similar storage

We set **one cookie**: `regence_refresh` (HttpOnly, Secure, SameSite=Strict), which keeps you signed in. It is
strictly necessary, so no consent banner is needed. Your browser's local storage keeps settings you choose (language,
theme, board options) and, for bot games in progress, a local snapshot. We will not add analytics or advertising
cookies without asking for your consent first.

## 4. Who receives data (recipients and transfers)

| Recipient | What | Where |
|---|---|---|
| Hosting provider {{HOSTING_PROVIDER}} | all data of the Service (servers) | {{HOSTING_COUNTRY}} |
| Cloudflare, Inc. | traffic passes through its network (DNS, protection, caching); technical request data | worldwide; its safeguards: {{CLOUDFLARE_TRANSFER_BASIS}} |
| Sentry (error tracking), if enabled | error reports without personal data | {{SENTRY_REGION}} |
| E-mail provider {{EMAIL_PROVIDER}} | your e-mail address and the message, when we send you mail | {{EMAIL_COUNTRY}} |
| Payment provider {{PAYMENT_PROVIDER}} (when paid plans exist) | purchase data | as in its policy |
| Public endgame tables (Lichess) | only chess positions, never player data, and only to prepare puzzles | — |

Where data go outside the EU/EEA/UK, we rely on an adequacy decision, the EU–US Data Privacy Framework or standard
contractual clauses, as stated in the table. We do not give data to authorities unless the law obliges us.

## 5. Automated decisions

Our fair-play measures compute signals and may **flag** an account. **A flag alone never closes an account:** a person
reviews it, and you can appeal. Automatic text filters only hold or mark messages for a moderator.

## 6. Your rights

You may at any time: see and **download** your data and **delete** your account (Settings → My data); correct data in
your profile; ask us to restrict or stop processing based on legitimate interest; withdraw consent you gave
(for e-mail and country, in Settings); ask for a copy in a machine-readable form (portability). Write to
`{{CONTACT_EMAIL}}`; we answer within one month. You may complain to a supervisory authority: in the EU, the authority
of your country; in the UK, the ICO; in Ukraine, the Ombudsman. **Deletion** erases personal data (username becomes
anonymous, e-mail and country are removed); games stay in opponents' history under the anonymous name.

## 7. Children

The Service is for people **16 and older** (Terms, Section 3). We do not knowingly collect data from younger
children. If we learn that we have, we delete the account and its data. Parents who believe their child registered
should write to us.

## 8. Security

Passwords are stored as hashes; sign-in tokens in the server's memory store are kept as hashes; connections are
encrypted (HTTPS); access to servers is limited; the database is backed up regularly, with a copy at a second provider (backups are kept for {{BACKUP_RETENTION_DAYS}} days, so deleted data can remain in them until they expire). No system is
perfectly secure; if a breach puts you at risk, we will inform you and the authority as the law requires.

## 9. Changes

When we change this Policy in substance we publish a new version date and tell registered players at their next login.

## 10. Contact

{{OPERATOR_NAME}} · {{OPERATOR_ADDRESS}} · {{CONTACT_EMAIL}}
