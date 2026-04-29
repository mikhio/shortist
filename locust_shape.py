"""Step-up профиль нагрузки для locust.

Подключается к `locustfile.py` через `--shape StepLoadShape` (или просто
лежит рядом — locust подхватывает классы LoadTestShape автоматически из
`-f` файла).

Логика: в течение 2.5 минут плавно поднимаем число юзеров с 50 до 800
ступеньками по 30 секунд. На каждой ступени смотрим в web-UI / CSV, как
ведут себя p95 и fail rate.

Критерии деградации фиксируем заранее (см. README → раздел
«Нагрузочное тестирование»):

* p95 latency > 2× от baseline (50 юзеров);
* fail rate > 1%;
* RPS перестаёт расти при увеличении users (saturation).

Источник: https://docs.locust.io/en/stable/custom-load-shape.html
"""
from __future__ import annotations

from locust import LoadTestShape


class StepLoadShape(LoadTestShape):
    stages = [
        {"duration": 30, "users": 50, "spawn_rate": 10},
        {"duration": 60, "users": 100, "spawn_rate": 10},
        {"duration": 90, "users": 200, "spawn_rate": 10},
        {"duration": 120, "users": 400, "spawn_rate": 20},
        {"duration": 150, "users": 800, "spawn_rate": 40},
    ]

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return stage["users"], stage["spawn_rate"]
        return None
