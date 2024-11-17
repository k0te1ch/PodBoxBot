# NOT WORKING IN *NIX

pip-tools:
	python -m pip install -U pip
	python -m pip install -U poetry
	poetry add poetry-plugin-up --group dev
	poetry add pre-commit --group dev

requirements: pip-tools
	poetry install --with=dev,test

run:
	python app/bot.py run

async-makemigrations:
	python app/bot.py makemigrations -s False

async-migrate:
	python app/bot.py migrate -s False

test:
	poetry run pytest --cov=.

check:
	poetry run pre-commit run --show-diff-on-failure --color=always --all-files

update: pip-tools
	poetry update
	poetry run poetry up
	poetry run pre-commit autoupdate

lock:
	poetry lock

docker-build:
	docker-compose --env-file .env build

docker-test: docker-build
	docker-compose run test-runner pytest

docker-run:
	docker-compose up -d --force-recreate

docker-up: docker-build
	docker-compose up -d --force-recreate

docker-stop:
	docker-compose down

docker-rm: docker-stop
	docker-compose rm
