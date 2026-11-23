# 1.8. Источники PGN: что можно использовать

Проверено 23.11.2026 по официальным страницам; часть страниц недоступна для автоматического чтения (помечено).
Не юридическая консультация.

## Что у нас используется

| Что | Откуда | Где в проекте | В репозитории? |
|---|---|---|---|
| PGN-файлы игроков XIX–XX веков (Морфи, Андерссен, Цукерторт, Стаунтон, Паульсен, Чигорин, Тарраш, Пильсбери, Маршалл, Нимцович, Рети, Тартаковер, Ботвинник, Таль, Петросян) | pgnmentor.com (`src/db/seed.py`, `scripts/import_library.py`) | библиотека «Партии мастеров», архив партий, дебютные книги | **нет** (`git ls-files data/pgns` пусто, 18 МБ локально) |
| Партии с сайта chessgames.com | `scripts/chessgames_downloader.py` | — | нет |
| Дебютные книги ботов (`src/services/bots/books/*.json`, 22 файла) | статистика ходов, построенная из тех же партий | боты | **да** (производная статистика, не сами партии) |
| Таблица дебютов | lichess-org/chess-openings | `src/services/data/openings.tsv` | да, CC0 |

## Что сказано на источниках

**pgnmentor.com** (страницы «/» и «/files.html»):
- «The files below are available for download, completely free. Enjoy!»
- «Multiple file downloads are available with the registered version of PGN Mentor.» (то есть массовая загрузка — часть платного продукта).
- Единственный правовой текст: «Copyright © 2025 64 Squares». Условий использования, лицензии, оговорок о
  перераспределении не найдено.
- **Вывод:** бесплатное скачивание не даёт права копировать, хранить для публичной раздачи и строить на этом продукт;
  без лицензии действует режим «все права защищены».

**chessgames.com**: страницы условий (`/terms.html`, `/perl/terms`) вернули отказ в доступе, дословно прочесть не
удалось. Известно: подвал «Copyright 2001-2025, Chessgames Services LLC.»; регистрация означает согласие «abide by all
Chessgames policies». Считать закрытым. **Не запускать `scripts/chessgames_downloader.py`**; не использовать
комментарии пользователей сайта вообще.

**TWIC (theweekinchess.com):** «free for personal use only. All rights are reserved» — для распространения не годится.

**Lichess open database (database.lichess.org):** «Database exports are released under the Creative Commons CC0
license» — подходит без ограничений, **но это только онлайн-партии с 2013 года, мастеров до 1950 года там нет.**
Трансляции Lichess обычно тоже CC0 (**не проверено**: страница вернула отказ).

**Caissabase, KingBase:** текст лицензии не найден; KingBase закрыт в 2019, доступен лишь в архиве. Не использовать.

## Что говорит право (кратко, **не проверено по текстам законов**)

- Последовательность ходов — факт, авторского права на неё нет. Авторским правом защищены комментарии, примечания и
  оригинальные тексты.
- В ЕС изготовитель базы данных имеет особое право (Директива 96/9/EC): запрет изъятия и повторного использования
  существенной части базы или многократного изъятия несущественных частей; срок 15 лет с продлением при новых
  существенных вложениях. В США такого права нет, но условия сайта связывают договором.
- Следствие: сами партии XIX века свободны, но **массовая выгрузка чужой подборки** (с её отбором, исправлениями,
  заголовками) — риск, пока владелец не разрешил.

## План замены (рекомендация)

1. **До запуска публично — письмо владельцам pgnmentor.com** (шаблон ниже). При согласии — записать разрешение
   (письмо) и условия в `ATTRIBUTION.md`.
2. **Собственный корпус:** партии до 1925 г. из первоисточников в общественном достоянии (турнирные сборники и
   журналы старше 100 лет; Wikisource; Wikimedia Commons). Брать только ходы и заголовки (игроки, событие, место, год,
   итог) и вносить в базу с указанием источника. Комментарии — свои.
3. **Современные партии:** Lichess CC0 (онлайн) и CC0-трансляции турниров.
4. **До ответа и замены:** библиотеку «Партии мастеров» и архив **в публичной версии не показывать**; дебютные книги
   (статистика) и ботов — можно.
5. В `ATTRIBUTION.md` для каждого источника: адрес, дата получения, лицензия/разрешение.
6. В Условиях — контакт для жалоб на нарушение прав (раздел 13).

## Шаблон письма (английский)

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

**Что нужно от вас:** отправить письмо (или сказать мне «отправь письмо в 64 Squares» — подготовлю черновик в
вашей почте; отправка — только по вашей отдельной команде) и решить п. 4.
