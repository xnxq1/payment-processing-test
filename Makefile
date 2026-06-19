.PHONY: help build up down restart logs ps shell-api shell-db clean test lint format mig-new mig-up

help: ## Показать помощь
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

build: ## Собрать образы
	docker compose build

up: ## Поднять все сервисы
	docker compose up --build

down: ## Остановить сервисы
	docker compose down

restart: ## Перезапустить
	docker compose restart

logs: ## Логи всех сервисов
	docker compose logs -f

ps: ## Статус контейнеров
	docker compose ps

shell-api: ## Shell в api
	docker compose exec api /bin/bash

shell-db: ## psql
	docker compose exec postgres psql -U $${POSTGRES_USER:-payments} -d $${POSTGRES_DB:-payments}

clean: ## Удалить контейнеры и volumes
	docker compose down -v

test: ## Запустить тесты локально
	pytest -v

lint: ## ruff check
	ruff check .

format: ## ruff format
	ruff check . --fix
	ruff format .

mig-new: ## Создать миграцию: make mig-new MSG="..."
	docker compose exec api alembic revision --autogenerate -m "$(MSG)"

mig-up: ## Применить миграции
	docker compose exec api alembic upgrade head
