.DEFAULT_GOAL := format
DIR = starlette_feedgen

deps:
	pip install -r requirements.txt

format:
	isort --recursive $(DIR)
	black $(DIR)

lint:
	isort --recursive --check-only --diff $(DIR)
	black --check $(DIR)
	flake8 $(DIR)
