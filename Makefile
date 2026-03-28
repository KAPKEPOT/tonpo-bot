.PHONY: help install dev-install run run-dev migrate create-migration test lint format clean docker-up docker-down

help:
	@echo "Available commands:"
	@echo "  make install          - Install production dependencies"
	@echo "  make dev-install      - Install development dependencies"
	@echo "  make run              - Run the bot"
	@echo "  make run-dev          - Run bot in development mode"
	@echo "  make migrate          - Run database migrations"
	@echo "  make create-migration - Create new migration"
	@echo "  make test             - Run tests"
	@echo "  make lint             - Run linters"
	@echo "  make format           - Format code"
	@echo "  make clean            - Clean cache files"
	@echo "  make docker-up        - Start Docker services"
	@echo "  make docker-down      - Stop Docker services"

install:
	pip install -r requirements.txt

dev-install: install
	pip install -r requirements-dev.txt

run:
	python main.py

run-dev:
	export DEBUG=true && python main.py

migrate:
	alembic upgrade head

create-migration:
	alembic revision --autogenerate -m "$(message)"

test:
	pytest tests/ -v --cov=. --cov-report=term

lint:
	flake8 .
	mypy .

format:
	black .
	isort .

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name "*.egg" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +

start-services:
	sudo systemctl start postgresql redis-server

stop-services:
	sudo systemctl stop redis-server

status:
	@echo "PostgreSQL:" && sudo systemctl is-active postgresql
	@echo "Redis:" && sudo systemctl is-active redis-server