# 1.13. Вход через Google и Apple: что делаете вы и что делаю я

Дата проверки: 23.11.2026 (официальные страницы Google и Apple; названия кнопок в консолях меняются — если
пункта нет на месте, ищите по названию в строке поиска консоли).

## Коротко

- **Google — делаем.** Бесплатно, ~30 минут вашей работы, без проверки приложения (для базовых данных: имя, e-mail).
- **Apple — откладываем до тех пор, пока не нужен.** Для сайта (не приложения iOS) вход через Apple **не обязателен**
  (правило Apple 4.8 относится к приложениям в App Store). Стоит 99 $/год и требует подтверждения личности. Делаем,
  если появятся ваши iOS-приложение или запросы игроков.
- Я могу написать весь код (сервер и клиент, тесты) **до** того, как у вас появятся ключи: он включается настройкой
  и без ключей ничего не показывает. Ключи нужны только для проверки «вживую».

## Что вы делаете сами, а что можно поручить мне

| Шаг | Кто | Почему |
|---|---|---|
| Создать аккаунт Google Cloud, принять условия | **вы** | юридическое согласие и ваша личность |
| Создать проект и «OAuth client» | **вы** (инструкция ниже, 10 мин) или я по команде «создай Google-клиент» — только если вы войдёте в браузер и разрешите | это ваш аккаунт |
| Подтвердить домен `regence.club` в Google Search Console | **вы нажимаете «Подтвердить»**; DNS-запись добавляю **я** (`cf`), когда скажете «добавь запись для Google» | Google привязывает домен к вашему аккаунту |
| Вставить Client ID и Client Secret в `.env` | **вы** (секрет в чат не отправляйте) | секреты только в `.env` |
| Код входа (сервер, клиент, тесты, тексты на 3 языках) | **я** | |
| Страницы `/privacy` и `/terms` на домене и главная с описанием | **я** (после проверки юристом) | требование Google для публикации |
| Apple: аккаунт, оплата 99 $, документы | **вы** | платёж и личность |
| Apple: Services ID, ключ `.p8`, Team ID | **вы** (инструкция ниже); подпись JWT — **я** | |

**Договорённость:** когда вы напишете «сделай Google-часть» — я сам делаю всё, что можно сделать без ваших секретов и
без входа в ваши аккаунты. Когда нужен ваш вход или платёж — я остановлюсь и напишу, что нужно сделать, одним шагом.

---

## Часть A. Google (делаем)

### A.0. Что нужно до начала
1. Аккаунт Google (можно рабочий gmail владельца проекта).
2. Для режима **«Testing»** (до 100 тестовых пользователей, без проверки) **ничего больше не нужно** — можно
   проверить вход уже на `localhost`. Для режима **«In production»** (вход для всех) Google требует:
   - публичную **главную страницу** на `regence.club` с описанием сервиса и ссылкой на политику конфиденциальности;
   - страницу **политики конфиденциальности** на том же домене (`https://regence.club/privacy`);
   - **подтверждённый в Search Console домен**.
   Пока сайт не выложен, ставьте «Testing»; к запуску переключите на «In production».

### A.1. Проект
1. Откройте https://console.cloud.google.com и войдите.
2. Сверху — выбор проекта → **New project** → имя `regence` → **Create**.

### A.2. Экран согласия («Google Auth Platform» → Branding / Audience)
1. В меню слева: **APIs & Services → OAuth consent screen** (в новом интерфейсе — **Google Auth Platform**) → **Get started**.
2. **App name:** `regence`. **User support email:** ваш e-mail.
3. **Audience:** **External**.
4. **Contact information:** ваш e-mail. Согласитесь с политикой пользовательских данных Google API → **Create**.
5. **Branding:** (в режиме Testing можно позже)
   - Application home page: `https://regence.club`
   - Privacy policy: `https://regence.club/privacy`
   - Terms of service: `https://regence.club/terms`
   - Authorized domains: `regence.club`
6. **Data Access (scopes):** оставьте только `openid`, `email`, `profile` (они «не чувствительные» — проверка Google не нужна).
7. **Audience → Publishing status:** оставьте **Testing**; добавьте себя и тестеров в **Test users**.

### A.3. Клиент
1. **Google Auth Platform → Clients → Create client** (или **APIs & Services → Credentials → Create credentials → OAuth client ID**).
2. **Application type:** `Web application`; имя `regence web`.
3. **Authorized JavaScript origins:**
   - `https://regence.club`
   - `http://localhost:5173` (разработка)
4. **Authorized redirect URIs** (точное совпадение, без `/` на конце):
   - `https://regence.club/api/v1/auth/oauth/google/callback`
   - `http://localhost:8000/api/v1/auth/oauth/google/callback`
5. **Create**. Покажутся **Client ID** и **Client secret**. **Секрет показывается один раз** — сохраните в менеджере паролей.

### A.4. Передать мне
В локальный файл `.env` (в корне проекта) добавьте две строки (имена я зафиксирую в `.env.example` вместе с кодом):

    GOOGLE_OAUTH_CLIENT_ID=...
    GOOGLE_OAUTH_CLIENT_SECRET=...

Client ID можно писать мне в чат (он не секрет). **Client Secret в чат не вставляйте.**
На боевом сервере те же две строки — в `.env` сервера.

### A.5. Домен в Search Console (только для режима «In production»)
1. https://search.google.com/search-console → **Add property** → **Domain** → `regence.club`.
2. Google покажет TXT-запись (`google-site-verification=...`). Скопируйте её значение и напишите мне
   «добавь запись для Google: <значение>» — **я добавлю TXT в DNS Cloudflare** (`cf`), и вы нажмёте **Verify**.
3. Затем в **Audience** нажмите **Publish app → In production**. Для базовых данных (имя, e-mail) отдельной проверки
   Google не требуется; если запросит «Brand verification» (логотип и название) — следуйте экрану: проверка идёт минуты,
   а «Publish branding» нужно нажать в течение 7 дней после успешной проверки.

### A.6. Что я сделаю в коде (после вашей команды «сделай Google-часть»)
- `GET /api/v1/auth/oauth/google/start` и `/callback` (код авторизации с PKCE, проверка `state` и `nonce`, проверка
  ID-токена: подпись, `aud`, `iss`, `exp`, `email_verified`).
- Правила аккаунта: если e-mail подтверждён Google и такой e-mail уже **подтверждён** у существующего игрока — входит в
  него (привязка); иначе создаётся новый игрок: имя игрока предлагается из имени Google и **выбирается игроком** (уникальное);
  пароль не нужен; согласие с Условиями и возраст 16+ запрашиваются **до** создания аккаунта.
- Таблица связей `oauth_identities` (провайдер, `sub`, игрок) — миграция; отвязка и «войти иначе» в настройках.
- Кнопка «Войти через Google» (дизайн по требованиям Google), тексты на трёх языках, тесты на подменённом провайдере.
- Удаление аккаунта стирает связь (`src/services/account.py`); в политике — раздел о данных от Google (имя, e-mail, фото не сохраняются).

---

## Часть B. Apple (откладываем; когда понадобится)

### B.0. Что это
Сайт может принимать «Sign in with Apple», но **не обязан**. Обязателен он только для iOS-приложения, которое
предлагает вход через другие соцсети. Для веба нужны: платная программа Apple Developer (99 $/год), Services ID,
ключ и домен с HTTPS (**на `localhost` вход через Apple не проверить** — только на боевом или тестовом домене).

### B.1. Аккаунт (вы)
1. https://developer.apple.com/programs/enroll/ — вход по Apple ID с двухфакторной защитой.
2. **Individual** (физлицо): юридическое имя, адрес (не абонентский ящик), совершеннолетие. **Organization:**
   юрлицо, номер D-U-N-S, сайт, почта на домене организации (дольше, до нескольких недель).
3. Оплата 99 $/год.

### B.2. Настройка (вы; Certificates, Identifiers & Profiles)
1. **Identifiers → App IDs → Register** → тип `App`; Bundle ID `club.regence.app`; включите **Sign in with Apple**.
2. **Identifiers → Services IDs → Register**: Description `regence web`; Identifier `club.regence.web`; включите
   **Sign in with Apple → Configure**: Primary App ID — созданный в п. 1; Domains: `regence.club`; Return URLs:
   `https://regence.club/api/v1/auth/oauth/apple/callback`. (Файла подтверждения домена не требуется.)
3. **Keys → Register**: имя `regence sign in`; включите **Sign in with Apple** → Configure → Primary App ID; **Download**
   файл `AuthKey_XXXX.p8` — **скачивается один раз**. Запишите **Key ID**.
4. **Team ID** — в правом верхнем углу или в Membership.

### B.3. Передать мне
В `.env` на сервере (секреты — только туда, не в чат):

    APPLE_OAUTH_CLIENT_ID=club.regence.web       # Services ID
    APPLE_OAUTH_TEAM_ID=...
    APPLE_OAUTH_KEY_ID=...
    APPLE_OAUTH_PRIVATE_KEY_PATH=/run/secrets/apple_key.p8   # путь к файлу ключа

Файл `.p8` положите на сервер (не в репозиторий). Client secret для Apple — это JWT (ES256), срок ≤ 6 месяцев; **я генерирую его
в коде по ключу и обновляю автоматически**, ничего вручную менять не придётся.

### B.4. Особенности Apple (учтены в коде)
- Имя и e-mail Apple отдаёт **только при первом входе** — мы сохраняем их сразу.
- Пользователь может скрыть e-mail (приватный адрес Apple); письма на такой адрес доходят лишь после регистрации
  вашего почтового домена в Apple; для входа адрес не нужен.
- Эти пункты **[из моих знаний, не подтверждены страницей Apple в этой сессии]**; проверим при подключении.

---

## Что делать прямо сейчас

1. Решить: **делаем Google? (да)** Apple — позже.
2. Пройти разделы A.1–A.4 (~30 минут): получите Client ID и Secret, положите в `.env`.
3. Написать мне «сделай Google-часть» — я пишу код, тесты и тексты, открываю PR.
4. К публичному запуску — A.5 (домен в Search Console, «In production») и страницы `/privacy`, `/terms`.
