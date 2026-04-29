"""Сценарии нагрузочного тестирования shortist.

Два юзер-профиля:

* `LinkCreator` — POST /links/shorten со случайным URL. Проверяет, что
  ручка создания не разваливается под нагрузкой.
* `LinkVisitor` — GET /links/{short_id} по горячему пулу заранее
  созданных ссылок. Это та ручка, которую имеет смысл кэшировать —
  она и используется для сравнения «без кэша vs с кэшем».

Запуск с web-UI:

    locust -f locustfile.py --host http://localhost:8000

Запуск headless со step-up формой и сохранением метрик:

    locust -f locustfile.py --host http://localhost:8000 \\
           --headless --csv reports/baseline/run \\
           --html reports/baseline/locust.html

Источник: https://docs.locust.io
"""
from __future__ import annotations

import logging
import random
import string

import requests
from locust import HttpUser, between, events, task

logger = logging.getLogger(__name__)

# Пул заранее созданных short_id, общий для всех визитёров.
_HOT_LINKS: list[str] = []
_HOT_TARGET = 100


def _random_url() -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"https://example.com/page-{suffix}"


@events.test_start.add_listener
def warmup_hot_links(environment, **_kwargs):
    """Перед стартом теста создаём `_HOT_TARGET` ссылок, чтобы LinkVisitor
    дёргал реальные short_id, а не получал бесконечные 404.
    """
    host = environment.host or "http://localhost:8000"
    logger.info("warming up: creating %d hot links against %s", _HOT_TARGET, host)
    created = 0
    for _ in range(_HOT_TARGET):
        try:
            resp = requests.post(
                f"{host}/links/shorten",
                json={"original_url": _random_url(), "expire_at": None},
                timeout=5,
            )
            if resp.status_code == 200:
                _HOT_LINKS.append(resp.json()["short_id"])
                created += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("warmup failed for one link: %s", e)
    logger.info("warmup complete: %d/%d", created, _HOT_TARGET)


class LinkCreator(HttpUser):
    """Создаёт ссылки. Низкий вес — основная нагрузка идёт на чтение."""

    weight = 1
    wait_time = between(0.5, 1.5)

    @task
    def create_link(self):
        self.client.post(
            "/links/shorten",
            json={"original_url": _random_url(), "expire_at": None},
            name="POST /links/shorten",
        )


class LinkVisitor(HttpUser):
    """Дёргает GET по горячему пулу — это профиль для оценки кэша."""

    weight = 9
    wait_time = between(0.1, 0.5)

    @task
    def visit_link(self):
        if not _HOT_LINKS:
            # warmup ещё не заполнил пул — пропускаем
            return
        short_id = random.choice(_HOT_LINKS)
        # follow_redirects=False, чтобы Locust не ходил на example.com
        self.client.get(
            f"/links/{short_id}",
            name="GET /links/{short_id}",
            allow_redirects=False,
        )
