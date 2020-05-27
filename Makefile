.DEFAULT_GOAL := format
DIR = starlette_feedgen

format:
	isort --recursive $(DIR)
	black $(DIR)

lint:
	isort --recursive --check-only --diff $(DIR)
	black --check $(DIR)
	flake8 $(DIR)
