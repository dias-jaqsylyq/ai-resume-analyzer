.PHONY: help install test lint fmt

help: ## Show available targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-8s %s\n", $$1, $$2}'

install: ## Install backend dev tools (pytest, ruff)
	pip install -r backend/requirements-dev.txt

test: ## Run backend unit tests
	cd backend && pytest -q

lint: ## Ruff lint + format check, terraform fmt check
	ruff check .
	ruff format --check .
	terraform -chdir=infra fmt -check -recursive

fmt: ## Auto-format Python and Terraform
	ruff check --fix .
	ruff format .
	terraform -chdir=infra fmt -recursive
