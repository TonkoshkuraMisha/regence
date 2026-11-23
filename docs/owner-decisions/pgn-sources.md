# 1.8. Джерела PGN: що можна використовувати

Перевірено 23.11.2026 за офіційними сторінками; частина сторінок недоступна для автоматичного читання (позначено).
Не юридична консультація.

## Що в нас використовується

| Що | Звідки | Де в проєкті | У репозиторії? |
|---|---|---|---|
| PGN-файли гравців XIX–XX століть (Морфі, Андерссен, Цукерторт, Стаунтон, Паульсен, Чигорін, Тарраш, Пілсбері, Маршалл, Німцович, Реті, Тартаковер, Ботвинник, Таль, Петросян) | pgnmentor.com (`src/db/seed.py`, `scripts/import_library.py`) | бібліотека «Партії майстрів», архів партій, дебютні книги | **ні** (`git ls-files data/pgns` порожньо, 18 МБ локально) |
| Партії з сайту chessgames.com | `scripts/chessgames_downloader.py` | — | ні |
| Дебютні книги ботів (`src/services/bots/books/*.json`, 22 файли) | статистика ходів, побудована з тих самих партій | боти | **так** (похідна статистика, не самі партії) |
| Таблиця дебютів | lichess-org/chess-openings | `src/services/data/openings.tsv` | так, CC0 |

## Що сказано на джерелах

**pgnmentor.com** (сторінки «/» і «/files.html»):
- «The files below are available for download, completely free. Enjoy!»
- «Multiple file downloads are available with the registered version of PGN Mentor.» (тобто масове завантаження — частина платного продукту).
- Єдиний правовий текст: «Copyright © 2025 64 Squares». Умов використання, ліцензії, застережень про
  перерозподіл не знайдено.
- **Висновок:** безкоштовне завантаження не дає права копіювати, зберігати для публічної роздачі та будувати на цьому продукт;
  без ліцензії діє режим «усі права захищено».

**chessgames.com**: сторінки умов (`/terms.html`, `/perl/terms`) повернули відмову в доступі, дослівно прочитати не
вдалося. Відомо: підвал «Copyright 2001-2025, Chessgames Services LLC.»; реєстрація означає згоду «abide by all
Chessgames policies». Вважати закритим. **Не запускати `scripts/chessgames_downloader.py`**; не використовувати
коментарі користувачів сайту взагалі.

**TWIC (theweekinchess.com):** «free for personal use only. All rights are reserved» — для поширення не годиться.

**Lichess open database (database.lichess.org):** «Database exports are released under the Creative Commons CC0
license» — підходить без обмежень, **але це лише онлайн-партії з 2013 року, майстрів до 1950 року там немає.**
Трансляції Lichess зазвичай також CC0 (**не перевірено**: сторінка повернула відмову).

**Caissabase, KingBase:** текст ліцензії не знайдено; KingBase закрито 2019 року, доступний лише в архіві. Не використовувати.

## Що каже право (коротко, **не перевірено за текстами законів**)

- Послідовність ходів — факт, авторського права на неї немає. Авторським правом захищені коментарі, примітки та
  оригінальні тексти.
- В ЄС виробник бази даних має особливе право (Директива 96/9/EC): заборона вилучення та повторного використання
  суттєвої частини бази або багаторазового вилучення несуттєвих частин; строк 15 років з продовженням за нових
  суттєвих вкладень. У США такого права немає, але умови сайту зв'язують договором.
- Наслідок: самі партії XIX століття вільні, але **масове вивантаження чужої добірки** (з її відбором, виправленнями,
  заголовками) — ризик, доки власник не дозволив.

## План заміни (рекомендація)

1. **До запуску публічно — лист власникам pgnmentor.com** (шаблон нижче). У разі згоди — записати дозвіл
   (лист) і умови в `ATTRIBUTION.md`.
2. **Власний корпус:** партії до 1925 р. з першоджерел у суспільному надбанні (турнірні збірники та
   журнали старші за 100 років; Wikisource; Wikimedia Commons). Брати лише ходи й заголовки (гравці, подія, місце, рік,
   підсумок) і вносити в базу із зазначенням джерела. Коментарі — свої.
3. **Сучасні партії:** Lichess CC0 (онлайн) і CC0-трансляції турнірів.
4. **До відповіді та заміни:** бібліотеку «Партії майстрів» і архів **у публічній версії не показувати**; дебютні книги
   (статистика) і ботів — можна.
5. В `ATTRIBUTION.md` для кожного джерела: адреса, дата отримання, ліцензія/дозвіл.
6. В Умовах — контакт для скарг на порушення прав (розділ 13).

## Шаблон листа (англійською)

> Subject: Permission to use game scores from PGN Mentor in a chess learning platform
>
> Hello,
>
> I am building regence (regence.club), a chess learning and playing platform. I would like to show the move
> scores and basic headers (players, event, year, result) of historical master games from your PGN files for the
> following players: Chigorin, Tarrasch, Pillsbury, Marshall, Nimzowitsch, Reti, Tartakower, Botvinnik, Tal and
> Petrosian. I would not copy your annotations, page design or software, I would credit PGN Mentor as the source
> on the page, and I would remove any game at your request.
>
> May I have your written permission to do this, and under what conditions?
>
> Thank you,
> {{YOUR_NAME}} · {{CONTACT_EMAIL}}

**Що потрібно від вас:** надіслати лист (або сказати мені «надішли лист до 64 Squares» — підготую чернетку у
вашій пошті; надсилання — лише за вашою окремою командою) і вирішити п. 4.
