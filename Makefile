.DEFAULT_GOAL := format
VENV_DIR = venv
DIR = starlette_feedgen
PYTHON = $(shell which python)
BIN_PATH = bin

ifeq ($(OS), Windows_NT)
	BIN_PATH = Scripts
endif

venv:
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_DIR)/$(BIN_PATH)/python -m pip install --upgrade pip
	$(VENV_DIR)/$(BIN_PATH)/python -m pip install poetry

deps:
	poetry install --no-root

lint:
	isort --check-only --diff $(DIR)
	find . -name '*.py' -not -path '*/$(VENV_DIR)/*' | xargs pyupgrade --py310-plus || true
	black --check $(DIR) --skip-magic-trailing-comma
	flake8 $(DIR) --config=flake8.ini

type:
	mypy $(DIR)

check:
	make lint
	make type

format:
	isort $(DIR)
	find . -name '*.py' -not -path '*/$(VENV_DIR)/*' | xargs pyupgrade --py310-plus || true
	black $(DIR) --skip-magic-trailing-comma
