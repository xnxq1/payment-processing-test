# payment-processing

Асинхронный сервис процессинга платежей. Принимает заявки по REST, обрабатывает через эмулируемый шлюз и доставляет результат через webhook.

> **Брокер.** RabbitMQ через **FastStream** (`faststream[rabbit]`). Ретраи в consumer'е — через отдельную retry-очередь с per-message TTL: упавшее сообщение republish'ится в `payments.new.retry`, по истечении TTL RabbitMQ возвращает его обратно в `payments.new` через DLX. Backoff растёт с каждой попыткой. Outbox-publisher имеет собственный механизм ретраев через `available_at` — только на случай сбоя при публикации в RabbitMQ.

## Стек

- Python 3.12
- FastAPI + Pydantic v2
- **dishka** (DI-контейнер)
- SQLAlchemy 2.0 Core (async, asyncpg)
- PostgreSQL 16
- **RabbitMQ 3.13 + FastStream** (`faststream[rabbit]`, topic exchange, durable queues, manual ack)
- Redis 7 (distributed lock на обработке платежа)
- Alembic
- structlog (JSON логи)
- pytest + testcontainers
- ruff + mypy

## Архитектура

```
app/
├── di.py              # dishka providers + container (точка сборки)
├── main.py            # AppBuilder — собирает FastAPI из списка routers
├── api/               # классы-роутеры (PaymentsRouter)
├── consumers/         # FastStream PaymentConsumer + ConsumerApp (один consumer по ТЗ)
├── workers/           # OutboxPublisher (poll + FOR UPDATE SKIP LOCKED + publish)
├── logic/
│   ├── handlers/      # классы-handler'ы (execute), инжектятся в роутеры/consumer'ы
│   ├── middlewares/   # RetryMiddleware (FastStream BaseMiddleware) для retry-цикла
│   ├── payments/      # PaymentsService + DTO + exceptions
│   ├── webhooks/      # WebhookService (HMAC) + exceptions
│   └── utils.py
├── domain/            # @dataclass сущности (Payment, OutboxEvent)
└── infra/
    ├── config.py      # Pydantic Settings
    ├── logging.py     # structlog + json
    ├── broker/        # FastStream: RabbitBroker factory + RabbitExchange/RabbitQueue
    ├── db/
    │   ├── connection.py
    │   ├── utils.py
    │   ├── models/    # SQLAlchemy Table (payments, outbox)
    │   ├── repos/     # BaseRepo (ContextVar) + EntityRepo + специализированные
    │   └── alembic/
    └── redis/         # redis connection + lock
```

### Слои

```
[ HTTP / RabbitMQ вход ]
        │
        ▼
[ Router/Consumer класс ]   ── описывает endpoint/subscriber, дёргает handler
        │
        ▼
[ Handler класс с .execute() ] ── 1 use-case, инжектится сервис(ы)/repo
        │
        ▼
[ Service ]               ── оркестрация и бизнес-логика (atomic tx)
        │
        ▼
[ Repo (BaseRepo) ]       ── SQLAlchemy Core + ContextVar транзакции
```

### DI (dishka)

`app/di.py` — несколько `Provider`-классов, каждый отвечает за свою область:

- `SettingsProvider` — `Settings` (+ инициализация логирования)
- `DBProvider` — `AsyncEngine`, `PaymentsRepo`, `OutboxRepo`
- `RedisProvider` — `Redis`, `RedisLocks`
- `BrokerProvider` — `RabbitBroker` (FastStream) + `RabbitExchange` + `RabbitQueue`
- `LogicProvider` — сервисы и **все handlers** (`CreatePaymentHandler`, `GetPaymentHandler`, `ListPaymentsHandler`, `ProcessPaymentHandler`, `PaymentGatewayEmulator`)
- `AppProvider` — роутер-классы + `AppBuilder`
- `ConsumerProvider` — `PaymentConsumer`, `ConsumerApp`
- `WorkerProvider` — `OutboxPublisher`

Контейнер собирается в `app/di.py:container = make_async_container(*build_providers())`. CLI берёт то, что нужно: `start-api` → `AppBuilder`, `start-consumer` → `ConsumerApp`, `start-outbox-publisher` → `OutboxPublisher`.

В тестах — отдельный контейнер той же сборки, репо/handler'ы доступны через фикстуры (`payments_repo`, `outbox_repo`, `process_payment_handler`, `deliver_webhook_handler`, `settings_obj`, `client`).

### Транзакции (ContextVar)

`BaseRepo` получает `AsyncEngine` через `__init__`, а активное соединение хранит в `contextvars.ContextVar`. Все репо, вызванные внутри блока `async with repo.transaction():`, автоматически попадают в одну транзакцию — без явной передачи `conn` параметром. Благодаря этому `INSERT payments` и `INSERT outbox` в `PaymentsService.create()` записываются атомарно.

### Класс-роутеры

Каждый ресурс — это класс с `__init__(handlers)`, `self.router = APIRouter(prefix=...)` и `register_routes()`, привязывающим методы класса к роутам. Методы класса делегируют вызов `await self.<handler>.execute(...)`. Между API и репо есть слой **handlers** (`app/logic/handlers/`): по одному классу на use-case с одним методом `execute(...)`.

### Outbox pattern

При создании платежа в БД пишется и запись в `outbox`. Отдельный процесс `outbox-publisher`:

1. В транзакции выбирает пачку `pending`-событий с `available_at <= now()` через `SELECT … FOR UPDATE SKIP LOCKED` — несколько воркеров безопасно работают параллельно.
2. Публикует в нужный RabbitMQ routing key (`topic` хранится в строке outbox; routing key = имя очереди) через topic-exchange `payments`. Используются publisher confirms и `delivery_mode=PERSISTENT`.
3. Помечает строку как `published`. При ошибке публикации — `retry_count++`, новый `available_at = now + backoff`. После N попыток — `status=failed`.

### Поток событий

Consumer один и решает что делать **по состоянию платежа в БД**, не по полям сообщения:

1. `status=PENDING` → вызывает `gateway.charge()`. Возвращает `bool`:
   - `True` → `mark_succeeded`
   - `False` → `mark_failed("gateway returned error")` сразу, без ретраев (gateway-эмулятор не бросает исключений).
2. После шага 1: если `webhook_url IS NOT NULL` и `webhook_delivered_at IS NULL` → шлёт webhook. При успехе — `mark_webhook_delivered`. При сбое доставки (`HttpRetryableError` / `HttpPermanentError`) — обрабатывает `RetryMiddleware`.

Сообщение в очереди — это просто триггер «обработай платёж X». Единственное поле — `id`. Никаких `phase`/`type`/`attempt`.

#### Retry middleware

`RetryMiddleware` (`app/logic/middlewares/retry.py`) перехватывает исключения subscriber'а:

- **Ретраябельное** (`HttpRetryableError` — 5xx/408/425/429/сеть; `HttpPermanentError` — 4xx) и попытки не исчерпаны → republish в `payments.new.retry` с per-message TTL и инкрементом счётчика в headers (`x-retry-count`). Оригинал ACK'нут. По истечении TTL RabbitMQ возвращает сообщение в `payments.new` через DLX.
- **Ретраябельное, исчерпано** (`x-retry-count >= PAYMENT_MAX_RETRIES`) → exception пробрасывается → `AckPolicy.REJECT_ON_ERROR` → reject(no requeue) → DLX очереди `payments.new` → `payments.new.dlq`.
- **Неожиданное исключение** → не ловится, reject → DLQ.

```
POST /api/v1/payments
   └─► tx: INSERT payments(status=pending) + INSERT outbox(topic=payments.new, payload={id})
                                                              │
                              outbox-publisher  ◄─────────────┘
                                      │  FastStream broker.publish (persist=True)
                                      ▼
                              queue: payments.new
                                      │
                                consumer (один)
                                      │
                          fetch payment by id
                                      │
              ┌───────────────────────┼────────────────────────┐
              │                       │                        │
       status=PENDING         status in (SUCCEEDED,         иначе
              │               FAILED) и webhook_url             nothing
       gateway.charge         и webhook_delivered_at IS NULL
              │                       │
   ┌──────────┴──────────┐    POST webhook
   ok                  err    ┌──────┴──────┐
   │                    │    2xx          5xx/timeout/429       4xx
   mark_succeeded   mark_failed  ↓             ↓                  ↓
   ├─► далее        ├─► далее   mark_webhook_  RetryMiddleware    RetryMiddleware
   webhook ↓        webhook ↓   delivered      → retry queue      → retry queue
                                               (TTL) → payments.   (TTL) → payments.
                                               new                  new
                                               ...                  ...
                                               retry == MAX → DLQ   retry == MAX → DLQ
```

Backoff: 1s, 5s, 25s (см. `app/logic/utils.py:exponential_backoff_seconds`). TTL передаётся в `expiration` сообщения при publish'е в retry-очередь.

### Идемпотентность

- На уровне БД: unique-индекс `payments_idempotency_key_uq`.
- На уровне API: повтор с тем же ключом и идентичным payload возвращает существующий платёж (`200 OK`); с тем же ключом и другим payload → `409 Conflict`.
- Все три INSERT (payments + outbox) под одной транзакцией с предварительным `SELECT` по ключу — двойного outbox-события не будет.

### Безопасность webhook

- HMAC SHA-256 по телу запроса, секрет в `WEBHOOK_SECRET`. Подпись в заголовке `X-Signature`.
- В получателе верифицировать через `WebhookService.verify(body, secret, signature)`.

### Аутентификация API

Все эндпоинты под префиксом `/api/v1/` требуют заголовка `X-API-Key`. Значение — `API_KEY` из env.

## Запуск

```bash
cp .env.example .env
make build
make up
make logs           # смотреть логи
make ps             # статус контейнеров
```

Сервисы:

| Сервис             | Команда                                       | Порт |
|--------------------|-----------------------------------------------|------|
| `api`              | `python manage.py start-api`                  | 8000 |
| `consumer`         | `python manage.py start-consumer`             | -    |
| `outbox-publisher` | `python manage.py start-outbox-publisher`     | -    |
| `postgres`         | postgres:16-alpine                            | 5432 |
| `rabbitmq`         | rabbitmq:3.13-management-alpine               | 5672 + 15672 (management UI) |
| `redis`            | redis:7-alpine                                | 6379 |

RabbitMQ Management UI: <http://localhost:15672> (guest / guest).

OpenAPI: <http://localhost:8000/docs>

## Примеры

Создать платёж:

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: local-dev-api-key" \
  -H "Idempotency-Key: order-42" \
  -H "Content-Type: application/json" \
  -d '{
        "amount": "199.99",
        "currency": "USD",
        "description": "Order #42",
        "payment_metadata": {"order_id": "42"},
        "webhook_url": "https://webhook.site/your-uuid"
      }'
```

Ответ:

```json
{
  "id": "….",
  "status": "pending",
  "amount": "199.9900",
  "currency": "USD",
  …
}
```

Получить платёж:

```bash
curl -H "X-API-Key: local-dev-api-key" http://localhost:8000/api/v1/payments/<id>
```

Список:

```bash
curl -H "X-API-Key: local-dev-api-key" \
  "http://localhost:8000/api/v1/payments?status=succeeded&limit=20&offset=0"
```

Повтор с тем же ключом:

```bash
# второй раз → тот же payment_id
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: local-dev-api-key" \
  -H "Idempotency-Key: order-42" \
  -H "Content-Type: application/json" \
  -d '{ "amount": "199.99", "currency": "USD", "description": "Order #42", "payment_metadata": {"order_id": "42"}, "webhook_url": "https://webhook.site/your-uuid" }'
```

Тот же ключ с другим payload:

```bash
# → 409 Conflict
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: local-dev-api-key" \
  -H "Idempotency-Key: order-42" \
  -H "Content-Type: application/json" \
  -d '{"amount": "1", "currency": "USD"}'
```

## DLQ

DLQ — durable очередь `payments.new.dlq` в обмене `payments`. Туда попадают сообщения, у которых ретраи в consumer'е исчерпаны (после `PAYMENT_MAX_RETRIES` неудачных попыток доставки webhook'а). Удобнее всего посмотреть через Management UI (<http://localhost:15672/#/queues>). Или из CLI:

```bash
docker compose exec rabbitmq rabbitmqadmin get queue=payments.new.dlq count=10
```

### Topology RabbitMQ

- Exchange `payments` (topic, durable).
- Очереди (durable, routing key = имя очереди, объявляются и связываются в `declare_topology()` из `app/infra/broker/topology.py`):
  - `payments.new` — основной поток обработки (DLX = `payments`, DLR = `payments.new.dlq`).
  - `payments.new.retry` — отложенные ретраи (DLX = `payments`, DLR = `payments.new`). Сообщения попадают в `payments.new` обратно по истечении per-message TTL.
  - `payments.new.dlq` — DLQ для исчерпанных ретраев.
- Биндинги (queue ↔ exchange по routing key) создаются явно в `declare_topology()`, потому что у retry и dlq очередей нет subscriber'а.
- Consumer: `@broker.subscriber(queue, exchange, ack_policy=AckPolicy.REJECT_ON_ERROR)` — ack при успехе, reject(no requeue) при исключении (тогда сработает DLX → DLQ). Между этими двумя случаями вклинивается `RetryMiddleware`, который для ретраябельных исключений сам republish'ит сообщение в retry-очередь и подавляет исключение (тогда оригинал ACK'ается).
- Publisher: `broker.publish(..., persist=True)` (durable сообщения), `message_id = outbox.id` для трейсинга.

В outbox строки с `status='failed'` — публикация в RabbitMQ не удалась после `MAX_PUBLISH_RETRIES`. Запрос для аудита:

```sql
SELECT id, topic, retry_count, last_error, available_at FROM outbox WHERE status='failed';
```

## Тесты

```bash
pip install -e .[dev]
pytest                  # требует Docker для testcontainers
```

Покрытие:

- `tests/test_unit_utils.py` — HMAC, нормализация Decimal/UUID, backoff
- `tests/test_api_payments.py` — REST: создание, GET, list, валидация, X-API-Key
- `tests/test_idempotency.py` — 200 vs 409 vs новый платёж, одно outbox-событие при повторе
- `tests/test_outbox.py` — `FOR UPDATE SKIP LOCKED`, `available_at`, `mark_failed`
- `tests/test_consumer_payments.py` — одиночный consumer: gateway (success → SUCCEEDED, failure → FAILED) и webhook (2xx → delivered, 5xx → `HttpRetryableError`, 4xx → `HttpPermanentError`, HMAC)

## Конфигурация

Полный список переменных — в `.env.example`. Ключевые:

| Var | По умолчанию | Назначение |
|-----|--------------|------------|
| `API_KEY` | `local-dev-api-key` | Статический ключ для `X-API-Key` |
| `WEBHOOK_SECRET` | `local-dev-webhook-secret` | Секрет для HMAC SHA-256 |
| `WEBHOOK_TIMEOUT_SECONDS` | `5` | HTTP timeout для исходящего webhook |
| `PAYMENT_PROCESSING_MIN_SECONDS` / `MAX_SECONDS` | `2` / `5` | Эмуляция шлюза |
| `PAYMENT_SUCCESS_RATE` | `0.9` | Доля успехов в эмуляции |
| `PAYMENT_MAX_RETRIES` | `3` | Максимум попыток обработки сообщения в `payments.new` до DLQ |
| `CONSUMER_PREFETCH` | `10` | RabbitMQ QoS prefetch для consumer'а |
| `QUEUE_PAYMENTS_NEW` / `QUEUE_PAYMENTS_RETRY` / `QUEUE_PAYMENTS_DLQ` | `payments.new` / `payments.new.retry` / `payments.new.dlq` | Имена основной/retry/DLQ очередей |
| `OUTBOX_POLL_INTERVAL_SECONDS` | `1` | Пауза publisher'а при пустой пачке |
| `OUTBOX_BATCH_SIZE` | `50` | Размер пачки за тик |

## Миграции

```bash
make mig-up                       # alembic upgrade head
make mig-new MSG="add field x"    # autogenerate новую миграцию
```

## Линтеры

```bash
make lint    # ruff check
make format  # ruff format + auto-fix
```
