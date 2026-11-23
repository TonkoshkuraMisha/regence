# 1.13. Вхід через Google та Apple: що робите ви і що роблю я

Дата перевірки: 23.11.2026 (офіційні сторінки Google та Apple; назви кнопок у консолях змінюються — якщо
пункту немає на місці, шукайте за назвою в рядку пошуку консолі).

## Коротко

- **Google — робимо.** Безкоштовно, ~30 хвилин вашої роботи, без перевірки застосунку (для базових даних: ім'я, e-mail).
- **Apple — відкладаємо, доки не знадобиться.** Для сайту (не застосунку iOS) вхід через Apple **не обов'язковий**
  (правило Apple 4.8 стосується застосунків в App Store). Коштує 99 $/рік і вимагає підтвердження особи. Робимо,
  якщо з'являться ваш iOS-застосунок або запити гравців.
- Я можу написати весь код (сервер і клієнт, тести) **до** того, як у вас з'являться ключі: він вмикається налаштуванням
  і без ключів нічого не показує. Ключі потрібні лише для перевірки «наживо».

## Що ви робите самі, а що можна доручити мені

| Крок | Хто | Чому |
|---|---|---|
| Створити акаунт Google Cloud, прийняти умови | **ви** | юридична згода і ваша особа |
| Створити проєкт і «OAuth client» | **ви** (інструкція нижче, 10 хв) або я за командою «створи Google-клієнт» — лише якщо ви увійдете в браузер і дозволите | це ваш акаунт |
| Підтвердити домен `regence.club` у Google Search Console | **ви натискаєте «Підтвердити»**; DNS-запис додаю **я** (`cf`), коли скажете «додай запис для Google» | Google прив'язує домен до вашого акаунта |
| Вставити Client ID і Client Secret у `.env` | **ви** (секрет у чат не надсилайте) | секрети лише в `.env` |
| Код входу (сервер, клієнт, тести, тексти двома мовами) | **я** | |
| Сторінки `/privacy` і `/terms` на домені та головна з описом | **я** (після перевірки юристом) | вимога Google для публікації |
| Apple: акаунт, оплата 99 $, документи | **ви** | платіж і особа |
| Apple: Services ID, ключ `.p8`, Team ID | **ви** (інструкція нижче); підпис JWT — **я** | |

**Домовленість:** коли ви напишете «зроби Google-частину» — я сам роблю все, що можна зробити без ваших секретів і
без входу у ваші акаунти. Коли потрібен ваш вхід або платіж — я зупинюся й напишу, що потрібно зробити, одним кроком.

---

## Частина A. Google (робимо)

### A.0. Що потрібно до початку
1. Акаунт Google (можна робочий gmail власника проєкту).
2. Для режиму **«Testing»** (до 100 тестових користувачів, без перевірки) **нічого більше не потрібно** — можна
   перевірити вхід уже на `localhost`. Для режиму **«In production»** (вхід для всіх) Google вимагає:
   - публічну **головну сторінку** на `regence.club` з описом сервісу та посиланням на політику конфіденційності;
   - сторінку **політики конфіденційності** на тому самому домені (`https://regence.club/privacy`);
   - **підтверджений у Search Console домен**.
   Поки сайт не виставлено, ставте «Testing»; до запуску перемкніть на «In production».

### A.1. Проєкт
1. Відкрийте https://console.cloud.google.com і увійдіть.
2. Угорі — вибір проєкту → **New project** → назва `regence` → **Create**.

### A.2. Екран згоди («Google Auth Platform» → Branding / Audience)
1. У меню ліворуч: **APIs & Services → OAuth consent screen** (у новому інтерфейсі — **Google Auth Platform**) → **Get started**.
2. **App name:** `regence`. **User support email:** ваш e-mail.
3. **Audience:** **External**.
4. **Contact information:** ваш e-mail. Погодьтеся з політикою щодо даних користувачів Google API → **Create**.
5. **Branding:** (у режимі Testing можна пізніше)
   - Application home page: `https://regence.club`
   - Privacy policy: `https://regence.club/privacy`
   - Terms of service: `https://regence.club/terms`
   - Authorized domains: `regence.club`
6. **Data Access (scopes):** залиште лише `openid`, `email`, `profile` (вони «не чутливі» — перевірка Google не потрібна).
7. **Audience → Publishing status:** залиште **Testing**; додайте себе й тестерів у **Test users**.

### A.3. Клієнт
1. **Google Auth Platform → Clients → Create client** (або **APIs & Services → Credentials → Create credentials → OAuth client ID**).
2. **Application type:** `Web application`; назва `regence web`.
3. **Authorized JavaScript origins:**
   - `https://regence.club`
   - `http://localhost:5173` (розробка)
4. **Authorized redirect URIs** (точний збіг, без `/` наприкінці):
   - `https://regence.club/api/v1/auth/oauth/google/callback`
   - `http://localhost:8000/api/v1/auth/oauth/google/callback`
5. **Create**. З'являться **Client ID** і **Client secret**. **Секрет показується один раз** — збережіть у менеджері паролів.

### A.4. Передати мені
У локальний файл `.env` (у корені проєкту) додайте два рядки (імена я зафіксую в `.env.example` разом з кодом):

    GOOGLE_OAUTH_CLIENT_ID=...
    GOOGLE_OAUTH_CLIENT_SECRET=...

Client ID можна писати мені в чат (він не секрет). **Client Secret у чат не вставляйте.**
На бойовому сервері ті самі два рядки — в `.env` сервера.

### A.5. Домен у Search Console (лише для режиму «In production»)
1. https://search.google.com/search-console → **Add property** → **Domain** → `regence.club`.
2. Google покаже TXT-запис (`google-site-verification=...`). Скопіюйте його значення і напишіть мені
   «додай запис для Google: <значення>» — **я додам TXT у DNS Cloudflare** (`cf`), а ви натиснете **Verify**.
3. Потім в **Audience** натисніть **Publish app → In production**. Для базових даних (ім'я, e-mail) окремої перевірки
   Google не потрібно; якщо запитає «Brand verification» (логотип і назва) — дійте за екраном: перевірка триває хвилини,
   а «Publish branding» потрібно натиснути протягом 7 днів після успішної перевірки.

### A.6. Що я зроблю в коді (після вашої команди «зроби Google-частину»)
- `GET /api/v1/auth/oauth/google/start` і `/callback` (код авторизації з PKCE, перевірка `state` і `nonce`, перевірка
  ID-токена: підпис, `aud`, `iss`, `exp`, `email_verified`).
- Правила акаунта: якщо e-mail підтверджено Google і такий e-mail уже **підтверджено** в наявного гравця — входить до
  нього (прив'язка); інакше створюється новий гравець: ім'я гравця пропонується з імені Google і **обирається гравцем** (унікальне);
  пароль не потрібен; згода з Умовами та вік 16+ запитуються **до** створення акаунта.
- Таблиця зв'язків `oauth_identities` (провайдер, `sub`, гравець) — міграція; відв'язування та «увійти інакше» в налаштуваннях.
- Кнопка «Увійти через Google» (дизайн за вимогами Google), тексти двома мовами, тести на підміненому провайдері.
- Видалення акаунта стирає зв'язок (`src/services/account.py`); у політиці — розділ про дані від Google (ім'я, e-mail, фото не зберігаються).

---

## Частина B. Apple (відкладаємо; коли знадобиться)

### B.0. Що це
Сайт може приймати «Sign in with Apple», але **не зобов'язаний**. Обов'язковий він лише для iOS-застосунку, який
пропонує вхід через інші соцмережі. Для вебу потрібні: платна програма Apple Developer (99 $/рік), Services ID,
ключ і домен із HTTPS (**на `localhost` вхід через Apple не перевірити** — лише на бойовому або тестовому домені).

### B.1. Акаунт (ви)
1. https://developer.apple.com/programs/enroll/ — вхід за Apple ID з двофакторним захистом.
2. **Individual** (фізособа): юридичне ім'я, адреса (не абонентська скринька), повноліття. **Organization:**
   юрособа, номер D-U-N-S, сайт, пошта на домені організації (довше, до кількох тижнів).
3. Оплата 99 $/рік.

### B.2. Налаштування (ви; Certificates, Identifiers & Profiles)
1. **Identifiers → App IDs → Register** → тип `App`; Bundle ID `club.regence.app`; увімкніть **Sign in with Apple**.
2. **Identifiers → Services IDs → Register**: Description `regence web`; Identifier `club.regence.web`; увімкніть
   **Sign in with Apple → Configure**: Primary App ID — створений у п. 1; Domains: `regence.club`; Return URLs:
   `https://regence.club/api/v1/auth/oauth/apple/callback`. (Файла підтвердження домену не потрібно.)
3. **Keys → Register**: назва `regence sign in`; увімкніть **Sign in with Apple** → Configure → Primary App ID; **Download**
   файл `AuthKey_XXXX.p8` — **завантажується один раз**. Запишіть **Key ID**.
4. **Team ID** — у правому верхньому куті або в Membership.

### B.3. Передати мені
В `.env` на сервері (секрети — лише туди, не в чат):

    APPLE_OAUTH_CLIENT_ID=club.regence.web       # Services ID
    APPLE_OAUTH_TEAM_ID=...
    APPLE_OAUTH_KEY_ID=...
    APPLE_OAUTH_PRIVATE_KEY_PATH=/run/secrets/apple_key.p8   # шлях до файла ключа

Файл `.p8` покладіть на сервер (не в репозиторій). Client secret для Apple — це JWT (ES256), строк ≤ 6 місяців; **я генерую його
в коді за ключем і оновлюю автоматично**, нічого вручну змінювати не доведеться.

### B.4. Особливості Apple (враховано в коді)
- Ім'я та e-mail Apple віддає **лише під час першого входу** — ми зберігаємо їх одразу.
- Користувач може приховати e-mail (приватна адреса Apple); листи на таку адресу доходять лише після реєстрації
  вашого поштового домену в Apple; для входу адреса не потрібна.
- Ці пункти **[з моїх знань, не підтверджені сторінкою Apple в цій сесії]**; перевіримо під час підключення.

---

## Що робити просто зараз

1. Вирішити: **робимо Google? (так)** Apple — пізніше.
2. Пройти розділи A.1–A.4 (~30 хвилин): отримаєте Client ID і Secret, покладете в `.env`.
3. Написати мені «зроби Google-частину» — я пишу код, тести й тексти, відкриваю PR.
4. До публічного запуску — A.5 (домен у Search Console, «In production») і сторінки `/privacy`, `/terms`.
