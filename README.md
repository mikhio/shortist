# shortist

[![tests](https://github.com/mikhio/shortist/actions/workflows/tests.yml/badge.svg)](https://github.com/mikhio/shortist/actions/workflows/tests.yml)
[![coverage](https://img.shields.io/badge/coverage-97%25-brightgreen)](htmlcov/index.html)
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

## Найденные дефекты (PR #1)

| № | Где | Что не так | Тест | Статус в PR #1 |
|---|-----|------------|------|----------------|
| 1 | `src/links/routers.py:redirect_link` | `expire_at` сохраняется, но при редиректе не проверяется. Просроченные ссылки продолжают редиректить вечно, несмотря на готовый `LinkExpiredError` (410). | `tests/functional/test_expire.py::test_expired_link_returns_410` | xfail → зелёный в PR #2 |
| 2 | `src/main.py` | Ручка `GET /health` отсутствует, хотя `docker-compose.yaml` ссылается на неё в healthcheck контейнера `app` → контейнер всегда `unhealthy`. | `tests/functional/test_health.py::test_health_endpoint_returns_200` | xfail → зелёный в PR #2 |
| 3 | `src/links/exceptions.py` | `AliasLengthError` и `LinkExpiredError` объявлены, но не используются (мёртвый код). | покрытие в `tests/unit/test_exceptions.py` | будут активированы в PR #2 |
| 4 | `src/links/crud.py:create_link` | `custom_alias` не сохраняется в модель — пишется только `short_id`. Из-за этого в ответе `custom_alias=null` и проверка уникальности по полю `custom_alias` всегда возвращает «свободно». Повторное создание с тем же alias валит UNIQUE constraint на `short_id` и FastAPI отдаёт 500 вместо 400. | `tests/functional/test_links_crud.py::test_create_link_with_custom_alias`, `test_duplicate_alias_returns_400` | xfail → зелёный в PR #2 |
| 5 | `requirements.txt` + код | `fastapi_cache`, `aioredis`, `redis` объявлены в зависимостях, но `FastAPICache.init` нигде не вызывается → кэш фактически не работает. | покрыто нагрузочным профилем | подключим в PR #2 |

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

Локальный прогон даёт **97% покрытия**. 5 непокрытых строк — это ветки,
заблокированные багами (раз они недостижимы → не покрыты). После фикса
в PR #2 покрытие должно вырасти.

```
src/auth/auth.py              7      0      0      0   100%
src/auth/manager.py          18      0      0      0   100%
src/auth/models.py           14      0      0      0   100%
src/auth/schemas.py          11      0      0      0   100%
src/config.py                10      0      0      0   100%
src/database.py               9      2      0      0    78%   (get_db override'ится в тестах)
src/links/crud.py            38      1      4      1    95%   (NotUniqueAliasError — заблокирован багом 4)
src/links/exceptions.py      20      0      0      0   100%
src/links/models.py          15      0      0      0   100%
src/links/routers.py         42      1      8      0    98%   (catch NotUniqueAliasError — баг 4)
src/links/schemas.py         29      1      4      1    94%
src/main.py                  14      0      0      0   100%
TOTAL                       227      5     16      2    97%
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

### Результаты прогона PR #1 (без кэша)

См. `reports/baseline/` — `locust.html` (общий отчёт Locust),
`latency-vs-users.png` (график p95/RPS по времени), `docker-stats.log`
(нагрузка на контейнеры).

Главная гипотеза, которую проверяем: на горячем редиректе каждый запрос
идёт в Postgres, поэтому уже на средних ступенях ожидается рост p95 и
saturation. В PR #2, где подключим Redis-кэш через `fastapi-cache2`,
повторим прогон и сравним.

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
