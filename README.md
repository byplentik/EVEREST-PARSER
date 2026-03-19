# Everest Parser

## Описание проекта

`Everest Parser` это Docker-приложение для пакетной обработки входных `.xlsx` файлов и получения данных с двух источников:

- `fedresurs.ru`
- `kad.arbitr.ru`

Результаты сохраняются в PostgreSQL.  
Приложение ориентировано на batch-режим: пользователь передает `.xlsx`, система ставит задачи в очередь, выполняет парсинг и пишет результат в базу данных.

## Какие задачи решает программа

### 1. Парсинг `fedresurs.ru`

На вход подается список ИНН.  
Для каждого ИНН программа:

1. ищет запись через `GET /backend/persons/fast`
2. получает `guid`
3. запрашивает `GET /backend/persons/{guid}/bankruptcy`
4. выбирает номер дела и последнюю дату публикации
5. сохраняет результат в БД

Итоговые поля:

- `inn`
- `case_number`
- `last_publication_date`

### 2. Парсинг `kad.arbitr.ru`

На вход подается список номеров дел.  
Для каждого номера дела программа:

1. получает рабочую браузерную сессию через `undetected-chromedriver`
2. использует эту сессию для HTTP-запросов
3. вызывает `POST /Kad/SearchInstances`
4. извлекает `uid` и ссылку на карточку дела
5. загружает `GET /Card/{uid}`
6. извлекает дату последнего документа и его наименование
7. сохраняет результат в БД

Итоговые поля:

- `case_number`
- `document_date`
- `document_name`

## Почему были выбраны именно такие решения

### `undetected-chromedriver` только для `kad`

Это принципиальное архитектурное решение.

Для `fedresurs` браузер не нужен, потому что нужные данные доступны через HTTP endpoint и корректно работают без браузерной сессии.

Для `kad` браузер нужен, потому что:

- сайт защищен антибот-механизмами
- прямой HTTP без предварительного browser bootstrap часто блокируется
- рабочая схема состоит из двух этапов:
  - сначала поднять браузер и получить валидную сессию
  - затем выполнять основную работу уже через HTTP

Итог:

- `fedresurs` реализован максимально просто через HTTP
- `kad` реализован как hybrid-сценарий: browser bootstrap + HTTP parsing

## Как работает программа

Полный цикл работы одной команды `parse`:

1. Пользователь кладет входной `.xlsx` в папку `input`
2. Команда `parse` читает файл
3. На основе файла создается `parse_job`
4. Из строк файла создаются `parse_tasks`
5. Для каждой задачи запускается соответствующий парсер
6. Результат сохраняется в таблицу результатов
7. Статусы задач и job обновляются
8. В консоль выводятся логи по каждой задаче
9. В конце команда печатает итоговый JSON-результат запуска

## Архитектура проекта

### CLI

Файл: [main.py](src/everest_parser/main.py)

CLI поддерживает две основные команды:

- `everest-parser db init`
- `everest-parser parse --parser ... --input ...`

### Слой импорта входного файла

Файл: [job_import.py](src/everest_parser/services/job_import.py)

Отвечает за:

- чтение `.xlsx`
- поиск нужной колонки
- нормализацию значений
- отбрасывание пустых, невалидных и дублирующихся строк
- создание `parse_jobs` и `parse_tasks`

### Парсеры

Файлы:

- [fedresurs.py](src/everest_parser/parsers/fedresurs.py)
- [kad.py](src/everest_parser/parsers/kad.py)

В этих файлах находится логика получения и разбора данных с сайтов.

### Runner-слой

Файлы:

- [fedresurs_runner.py](src/everest_parser/services/fedresurs_runner.py)
- [kad_runner.py](src/everest_parser/services/kad_runner.py)

Runner отвечает за:

- выбор `pending` задач
- запуск парсера по каждой задаче
- сохранение статусов `success / not_found / blocked / error`
- пересчет итогового статуса job

### Transport layer

Файл: [transports.py](src/everest_parser/clients/transports.py)

Отвечает за:

- HTTP-запросы
- retry-логику
- timeout
- proxy
- проверку ответов на признаки блокировки

### Browser bootstrap для `kad`

Файлы:

- [kad_bootstrap.py](src/everest_parser/browser/kad_bootstrap.py)
- [session_manager.py](src/everest_parser/clients/session_manager.py)

Отвечают за:

- запуск Chrome внутри контейнера
- получение рабочей браузерной сессии
- перенос cookies в HTTP-клиент
- повторное поднятие сессии при блокировке

### Слой БД

Файлы:

- [models.py](src/everest_parser/db/models.py)
- [session.py](src/everest_parser/db/session.py)
- [schema.py](src/everest_parser/db/schema.py)

## Структура БД

### `parse_jobs`

Хранит один запуск batch-обработки:

- тип парсера
- исходный файл
- общий статус
- счетчики обработанных, успешных и ошибочных задач

### `parse_tasks`

Хранит отдельные элементы очереди:

- исходное значение
- нормализованное значение
- статус
- число попыток
- текст последней ошибки

### `fedresurs_results`

Хранит результат по ИНН:

- `inn`
- `case_number`
- `last_publication_date`
- `raw_payload`

### `kad_results`

Хранит результат по номеру дела:

- `case_number`
- `document_date`
- `document_name`
- `raw_payload`

## Формат входных файлов

Читается только первый лист `.xlsx`.

### Для `kad`

Поддерживаемые названия колонки:

- `case_number`
- `номер дела`
- `дело`

Пример:

| case_number |
| --- |
| А32-28873/2024 |
| А40-12345/2025 |

### Для `fedresurs`

Поддерживаемые названия колонки:

- `inn`
- `инн`

Пример:

| inn |
| --- |
| 231138771115 |
| 7707083893 |

## Порядок запуска проекта

### 1. Подготовка

Создать `.env` на основе `.env.example`:

```bash
copy .env.example .env
```

Добавить входной `.xlsx` файл в папку `input`.

### 2. Запуск PostgreSQL

Запустить PostgreSQL:

```bash
docker compose up -d db
```

### 3. Инициализация таблиц

Инициализировать таблицы:

```bash
docker compose run --rm app everest-parser db init
```

### 4. Запуск `kad`

Запустить парсер `kad`:

```bash
docker compose run --rm app everest-parser parse --parser kad --input /app/input/file.xlsx
```

### 5. Запуск `fedresurs`

Запустить парсер `fedresurs`:

```bash
docker compose run --rm app everest-parser parse --parser fedresurs --input /app/input/file.xlsx
```

## Как читать логи

Во время работы программа пишет информативные логи в консоль:

- старт job
- старт обработки задачи
- успешный результат
- `NOT_FOUND`
- `BLOCKED`
- `ERROR`
- итог завершения job

Пример:

```text
[2026-03-19 15:55:33] [fedresurs] Старт job 23. Выбрано pending-задач: 2.
[2026-03-19 15:55:34] [fedresurs] job=23 task=230 inn=231138771115 Старт обработки.
[2026-03-19 15:55:35] [fedresurs] job=23 task=230 inn=231138771115 SUCCESS: дело=А32-28873/2024, дата=2025-10-03T15:21:16.250000+00:00
```

После завершения команда возвращает JSON-результат, который можно использовать как итог сводки выполнения.

## Настройки

Файл: [.env.example](.env.example)

Основные параметры:

- `DATABASE_URL` — строка подключения к PostgreSQL
- `HTTP_TIMEOUT_SECONDS` — timeout HTTP-запросов
- `HTTP_VERIFY_SSL` — проверка SSL
- `HTTP_PROXY_URL` — proxy для HTTP-запросов
- `BROWSER_PROXY_URL` — proxy для браузера `kad`
- `REQUEST_DELAY_SECONDS` — пауза между повторами
- `MAX_RETRIES` — число попыток повторного HTTP-запроса

## Инфраструктура Docker

Файл: [docker-compose.yml](docker-compose.yml)

Состав:

- сервис `db` — PostgreSQL
- сервис `app` — приложение парсера

Файл: [Dockerfile](Dockerfile)

Контейнер приложения включает:

- Python 3.11
- Google Chrome
- `xvfb`
- зависимости Python из `pyproject.toml`

Файл: [docker-entrypoint.sh](docker/docker-entrypoint.sh)

Используется только для запуска виртуального экрана `Xvfb`, который нужен `kad` для browser bootstrap внутри контейнера.

## Ключевые принципы реализации

### Простота

Код намеренно упрощен до минимально рабочего сценария:

- без лишних CLI-команд
- без декоративного логирования
- без лишней инфраструктуры поверх Docker

### Разделение ответственности

Логика разделена на отдельные уровни:

- импорт входных данных
- транспорт
- парсеры
- runner
- БД

Это упрощает сопровождение и отладку.

### Устойчивость

В проекте предусмотрены:

- retry HTTP-запросов
- классификация ошибок по статусам задач
- сохранение прогресса в БД

## Ограничения проекта

### `kad.arbitr.ru`

Сайт чувствителен к:

- антибот-защите
- сетевому окружению
- VPN/proxy
- качеству браузерной сессии


### `fedresurs.ru`

Реализация опирается на текущие HTTP endpoint сайта.  
Если структура endpoint или JSON изменится, потребуется адаптация парсера.

## Итог

Проект реализует рабочий batch-процесс:

- принимает входной `.xlsx`
- создает очередь задач
- запускает нужный парсер
- получает данные с `fedresurs.ru` и `kad.arbitr.ru`
- сохраняет результаты в PostgreSQL
- выводит понятные логи и итоговую сводку
