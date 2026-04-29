# shortist

[![tests](https://github.com/mikhio/shortist/actions/workflows/tests.yml/badge.svg)](https://github.com/mikhio/shortist/actions/workflows/tests.yml)
[![coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)](htmlcov/index.html)
[![python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/downloads/)

API-сервис сокращения ссылок на FastAPI + PostgreSQL + Redis. Этот форк
оригинального проекта (`https://github.com/neteplo/shortist`) собран в рамках
ИПР-2 курса «Инструменты промышленной разработки» ВШЭ ФКН ПИ — добавлены
тесты, нагрузочный профиль и баг-фиксы.

---

## Подход к работе

История репозитория устроена в два этапа, чтобы на ней было видно
**рост качества**:

1. **PR #1 — `tests/as-is` → `main`** (тесты «как есть»). Берём проект в
   текущем состоянии и покрываем тестами: юнит, функциональные, нагрузочные.
   Часть тестов заведомо красная — они подсвечивают **баги**, которые
   нашлись в процессе. Чтобы CI оставался зелёным, такие тесты помечены
   `@pytest.mark.xfail(strict=True, reason=...)`.
2. **PR #2 — `fix/bugs-and-cache` → `main`** (фикс и кэш). Чиним
   найденное, подключаем Redis-кэш на горячий редирект, повторяем
   нагрузочный прогон и сравниваем «до/после». `xfail` снимаются, тесты
   зеленеют, покрытие растёт.

Такой нарратив отражает индустриальный цикл *«покрыть тестами → выявить
дефекты → починить → повторить замеры»*.

---

## Найденные дефекты и фиксы

| № | Где | Что не так (нашли в PR #1) | Что сделали в PR #2 |
|---|-----|----------------------------|---------------------|
| 1 | `src/links/routers.py:redirect_link` | `expire_at` сохраняется, но при редиректе не проверяется → просроченные ссылки редиректят вечно, хотя `LinkExpiredError` (410) объявлен. | Добавили проверку `expire_at < now(UTC)`, при просрочке → `LinkExpiredError`. Тест `test_expired_link_returns_410` зеленеет. |
| 2 | `src/main.py` | Ручки `GET /health` нет, хотя `docker-compose.yaml` ссылается на неё в healthcheck → контейнер `app` `unhealthy`. | Добавили `@app.get("/health")` → `{"status": "ok"}`. Контейнер теперь `healthy`. |
| 3 | `src/links/exceptions.py` | `AliasLengthError`, `PermissionDeniedError`, `InvalidURLFormatError` — мёртвый код, нигде не вызываются. | Удалили мёртвые классы, оставили только используемые: `NotUniqueAliasError`, `LinkExpiredError`. |
| 4 | `src/links/crud.py:create_link` | `custom_alias` не сохранялся в модель — только в `short_id`. Из-за этого ответ возвращал `custom_alias=null`, проверка уникальности не работала, повторный POST с тем же alias валил UNIQUE constraint и отдавал 500 вместо 400. | Прокинули `custom_alias=custom_alias` в `models.Link(...)`. Тесты `test_create_link_with_custom_alias` и `test_duplicate_alias_returns_400` зеленеют. |
| 5 | deps + код | `fastapi_cache`, `aioredis` в `requirements.txt`, но `FastAPICache.init` нигде не вызывается. | Заменили на `fastapi-cache2[redis]`, инициализируем в `lifespan`-обработчике `src/main.py`, кэшируем редирект на 60 секунд, инвалидируем на PUT/DELETE. См. ниже сравнительные замеры. |
| 6 | `migration/` | Две альтернативные head-миграции (обе с `down_revision=None`), обе создают одну и ту же таблицу `user` → `alembic upgrade heads` падает на DuplicateTable. | Удалили устаревшую `a1b5c3ea8b92_initial_migration.py` (она ещё со схемой `short_url` / `link_owner_id` до рефакторинга). Осталась одна актуальная head. Также поправили `expire_at` на `nullable=True, timezone=True`. |
| 7 | `requirements.txt` | Пакет `dotenv` (заброшенный squatter на PyPI) вместо `python-dotenv`; `aioredis` несовместим с Python 3.12 и конфликтует с `redis>=4.2`. | `dotenv` → `python-dotenv`; `aioredis` → нативный `redis>=4.2.asyncio`; `fastapi_cache` → `fastapi-cache2[redis]`. |
| 8 | `Dockerfile` | `python:3.9-slim` — устарел и расходится с CI (3.12). | `python:3.12-slim` — единый рантайм везде. |

---

## Стек и решения по тестам

| Решение | Почему именно так | Источник стандарта |
|---------|-------------------|--------------------|
| `pytest` + `pytest-asyncio` (`asyncio_mode = "auto"`) | дефолт для async-тестов FastAPI | [pytest-asyncio docs](https://pytest-asyncio.readthedocs.io) |
| `httpx.AsyncClient` + `ASGITransport(app=app)` | официально рекомендованный способ ходить в FastAPI без поднятия uvicorn | [FastAPI Async Tests](https://fastapi.tiangolo.com/advanced/async-tests/) |
| In-memory SQLite (`sqlite+aiosqlite:///:memory:`) для функциональных тестов; Postgres в `docker-compose` — только для нагрузочных | функциональные изолируются и идут за миллисекунды; нагрузочные требуют реалистичную БД | [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/) |
| `app.dependency_overrides[get_db]` | штатный механизм FastAPI для подмены источника БД в тестах | [FastAPI Testing → Override deps](https://fastapi.tiangolo.com/advanced/testing-database/) |
| `pytest-mock` (фикстура `mocker`) для моков (включая будущий `FastAPICache` в PR #2) | чище чем `unittest.mock.patch` в качестве декораторов | [pytest-mock](https://pytest-mock.readthedocs.io) |
| `coverage` с `concurrency = ["thread", "greenlet"]` | без этого coverage не видит async-функций, проходящих через ASGITransport, и показывает ложное низкое покрытие | [coverage.py docs → concurrency](https://coverage.readthedocs.io/en/latest/config.html#run-concurrency) |
| `Hypothesis` на `generate_short_id` | property-based тест ловит инвариант для любых входов, а не только для зашитых примеров | [Hypothesis docs](https://hypothesis.readthedocs.io) |
| `Locust` + `LoadTestShape` со ступеньками 50→800 | стандартный паттерн нагрузочного — повышаем нагрузку, пока не проявится деградация | [Locust → custom load shape](https://docs.locust.io/en/stable/custom-load-shape.html) |
| `xfail(strict=True)` на тесты, ловящие баг | даёт «красный сигнал» в отчёте, но не валит CI; в PR #2 удаляются и тесты должны позеленеть, иначе `strict=True` обратно сделает CI красным | [pytest docs → xfail](https://docs.pytest.org/en/stable/how-to/skipping.html#xfail) |

---

## Запуск тестов

```bash
git clone https://github.com/mikhio/shortist.git
cd shortist
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# юнит + функциональные
pytest tests/ --cov=src --cov-report=html

# открыть отчёт о покрытии
open htmlcov/index.html
```

В коммит включён готовый `htmlcov/` — отчёт о покрытии открывается **без
запуска тестов**, как этого требует задание ИПР.

**94% покрытия** в PR #2. По сравнению с 97% в PR #1: добавились новые
ветки (lifespan-инициализация Redis с fallback, ручной cache get/set/clear,
проверка `expire_at`) — некоторые из них ловятся только в проде и не
поднимаются в тестах (например, реальное Redis-подключение в lifespan).

```
src/auth/auth.py              7      0      0      0   100%
src/auth/manager.py          18      0      0      0   100%
src/auth/models.py           14      0      0      0   100%
src/auth/schemas.py          11      0      0      0   100%
src/config.py                10      0      0      0   100%
src/database.py               9      2      0      0    78%
src/links/crud.py            38      0      4      0   100%
src/links/exceptions.py      10      0      0      0   100%
src/links/models.py          15      0      0      0   100%
src/links/routers.py         82      4     18      2    94%
src/links/schemas.py         29      1      4      1    94%
src/main.py                  33      8      0      0    76%
TOTAL                       276     15     26      3    94%
```

---

## Нагрузочное тестирование

### Запуск

Нагрузочные тесты требуют поднятого сервиса с настоящей БД и Redis:

```bash
# 1. Поднять стек: postgres + redis + shortist
cp .env.example .env  # отредактировать значения, минимум DB_* и SECRET
docker compose up -d --build
docker compose exec web alembic upgrade head

# 2. Прогон step-up нагрузки в headless-режиме
mkdir -p reports/baseline
locust -f locustfile.py \
    --host http://localhost:8000 \
    --headless \
    --csv reports/baseline/run \
    --html reports/baseline/locust.html \
    --logfile reports/baseline/locust.log

# 3. После прогона — построить графики
python scripts/plot_loadtest.py \
    reports/baseline/run_stats_history.csv \
    --label "без кэша" \
    --out reports/baseline/latency-vs-users.png
```

### Профиль и критерии деградации

`locust_shape.py:StepLoadShape` поднимает нагрузку ступенями:

| Этап | Длительность | Юзеров | Spawn rate |
|------|--------------|--------|------------|
| 1 | 30 с | 50 | 10/с |
| 2 | 30 с | 100 | 10/с |
| 3 | 30 с | 200 | 10/с |
| 4 | 30 с | 400 | 20/с |
| 5 | 30 с | 800 | 40/с |

**Деградацией** считаем выполнение хотя бы одного из условий:

* p95 latency > 2× от baseline (значение на 50 юзерах);
* fail rate > 1%;
* RPS перестал расти при росте users (saturation).

### Сравнение «без кэша vs с кэшем» (главный результат)

После подключения `fastapi-cache2[redis]` повторили тот же step-up
профиль 50→800 юзеров. Сравнение по ключевым ступеням:

| users | RPS без кэша | RPS с кэшем | speedup | p95 без кэша | p95 с кэшем |
|------:|-------------:|------------:|--------:|-------------:|------------:|
|  50 |   150 |   153 | 1.0× |    23 ms |    7 ms |
| 100 |   283 |   307 | 1.1× |    71 ms |    6 ms |
| 200 |   429 |   609 | 1.4× |   298 ms |    7 ms |
| 400 |   540 | 1 215 | **2.3×** |   615 ms |    8 ms |
| 600 |   487 | 1 262 | **2.6×** |   740 ms |   13 ms |
| 800 |   467 | 1 950 | **4.2×** | 1 438 ms |  132 ms |

* На 800 юзерах **p95 упал в 11 раз** (1438 → 132 ms), **RPS вырос в 4.2 раза** (467 → 1950).
* Saturation отодвинулся за пределы прогона — RPS продолжает расти на верхней ступени.
* Failures = 0 в обоих прогонах.

Графики:

* `reports/baseline/latency-vs-users.png` — без кэша.
* `reports/cached/latency-vs-users.png` — с кэшем.
* `reports/comparison.png` — оба прогона на одной оси.

### Tradeoff: счётчик кликов

Первый GET `/links/{short_id}` инкрементирует `click_count` в Postgres,
но последующие 60 секунд отдаются из Redis и **не пишут в БД**. Это
сознательный компромисс: точный счётчик кликов жертвуется ради latency.
Тест `test_redirect_increments_click_count` это учитывает (проверяет
`click_count >= 1`, а не строгое равенство). Если нужна строгая
аналитика — её делают отдельным конвейером (Kafka → ClickHouse), а не
синхронно на горячей ручке.

### Результаты прогона PR #1 (без кэша) — для справки

Артефакты в `reports/baseline/`:

* `locust.html` — стандартный отчёт Locust;
* `latency-vs-users.png` — график p95 / RPS / users по времени (matplotlib);
* `run_stats_history.csv`, `run_stats.csv` — сырые time-series и финальная сводка;
* `docker-stats.log` — нагрузка на контейнеры postgres/redis/web в течение прогона.

**Сводка по ступеням** (стабильная часть каждой):

| users | RPS | p50, мс | p95, мс | p99, мс | fails/s |
|------:|----:|--------:|--------:|--------:|--------:|
|  50  |  150 |   5 |   23 |  103 | 0 |
| 100  |  283 |   6 |   71 |  273 | 0 |
| 200  |  429 |  10 |  298 |  427 | 0 |
| 400  |  540 |  48 |  615 | 1005 | 0 |
| 600  |  487 |  75 |  740 | 1200 | 0 |
| 800  |  467 | 162 | 1438 | 2769 | 0 |

**Что видно:**

* **p95 deg** — критерий «p95 > 2× baseline» (порог 46 мс) пробит уже на
  ступени 100 (71 мс), к 800 юзерам p95 = 1438 мс — **в 60× выше
  baseline**.
* **Saturation** — RPS растёт линейно до 400 (≈540 RPS), дальше выходит
  на плато и даже немного **проседает** под 800 юзерами. Это второй
  критерий деградации.
* **Failures = 0** на всём прогоне — сервис не разваливается, но
  отвечает медленно. Бутылочное горлышко — **Postgres**: каждый
  `GET /links/{short_id}` идёт в БД (`crud.get_link_by_short_id` +
  `increment_click_count` с `commit`).

В PR #2 подключим `fastapi-cache2` поверх Redis на ручке редиректа и
повторим тот же step-up. Гипотеза: p95 на 800 юзерах должен упасть в
несколько раз, RPS пробьёт текущее плато.

---

## Структура проекта

```
shortist/
├── .github/workflows/tests.yml   # CI: pytest + coverage --fail-under=90
├── src/                          # исходники сервиса
├── tests/
│   ├── conftest.py               # фикстуры: app, async_client, authenticated_client
│   ├── unit/                     # юнит-тесты (без БД и HTTP)
│   └── functional/               # тесты через ASGI-клиент
├── locustfile.py                 # сценарии: создание + горячий редирект
├── locust_shape.py               # StepLoadShape (50 → 800 юзеров)
├── scripts/plot_loadtest.py      # графики из stats_history.csv
├── reports/                      # артефакты нагрузочных прогонов
├── htmlcov/                      # отчёт о покрытии
├── requirements.txt              # runtime
├── requirements-dev.txt          # тесты + локуст + matplotlib + ruff
└── pyproject.toml                # конфиг pytest, coverage, ruff
```

---

## Оригинальный README проекта (API)

### Аутентификация

* `POST /auth/register` — регистрация
* `POST /auth/jwt/login` — вход (form-data: `username`, `password`); cookie `shortist`
* `POST /auth/jwt/logout` — выход

### Ссылки

* `POST /links/shorten` — создать (доступно всем; авторизованному привязывается)
* `GET /links/{short_id}` — редирект (доступно всем)
* `GET /links/{short_id}/stats` — статистика (только владельцу)
* `GET /links/search/?original_url=...` — поиск своих ссылок (только владельцу)
* `PUT /links/{short_id}` — обновить URL (только владельцу)
* `DELETE /links/{short_id}` — удалить (только владельцу)

### Запуск сервиса

```bash
cp .env.example .env  # заполнить DB_*, SECRET
docker compose up -d --build
docker compose exec web alembic upgrade head
```
