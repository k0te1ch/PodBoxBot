# Локальная разработка. Каждый сервис — отдельный poetry-проект, поэтому почти
# всё делается через `cd <dir> && poetry run ...`. Прод поднимается через
# docker compose (см. README), а не отсюда.
#
# Две причины, почему рецепты выглядят так, а не короче:
#   * `poetry -C <dir> run` выполняет команду с cwd=<dir>, поэтому относительные
#     пути к tests/ из корня ломаются — отсюда `cd` и $(CURDIR);
#   * корневого pyproject.toml нет, и конфиг ruff (line-length 119) подхватывается
#     только из app/bot. Из корня ruff берёт дефолтные 88 и форматирует иначе,
#     чем проверит CI.

BOT := app/bot
PUBLISHERS := app/publishers/FTP app/publishers/WordPress app/publishers/Boosty

.PHONY: install install-publishers lock update lint format test test-publishers         check run migrate makemigrations docker-build docker-up docker-stop docker-logs

# --- зависимости ------------------------------------------------------------

install:
	poetry -C $(BOT) install --with testing,dev

install-publishers:
	@for d in $(PUBLISHERS); do echo "--- $$d"; poetry -C $$d install || exit 1; done

lock:
	poetry -C $(BOT) lock
	@for d in $(PUBLISHERS); do poetry -C $$d lock || exit 1; done

update:
	# poetry-plugin-up — плагин самого poetry, а не зависимость проекта: как
	# зависимость он пинил древний poetry и тянул уязвимый dulwich.
	poetry self add poetry-plugin-up
	poetry -C $(BOT) up
	poetry -C $(BOT) run pre-commit autoupdate

# --- проверки ---------------------------------------------------------------

lint:
	cd $(BOT) && poetry run ruff check "$(CURDIR)/app" "$(CURDIR)/tests"
	cd $(BOT) && poetry run ruff format --check "$(CURDIR)/app" "$(CURDIR)/tests"

format:
	cd $(BOT) && poetry run ruff check --fix "$(CURDIR)/app" "$(CURDIR)/tests"
	cd $(BOT) && poetry run ruff format "$(CURDIR)/app" "$(CURDIR)/tests"

# Тесты публишеров требуют зависимостей своих сервисов (asyncssh, aioprometheus,
# boosty), которых нет в окружении бота — поэтому отдельная цель, как и в CI.
test:
	cd $(BOT) && poetry run python -m pytest -c pyproject.toml --rootdir "$(CURDIR)" 		-o addopts="--cov=$(CURDIR)/app -m 'not e2e'" 		--ignore "$(CURDIR)/tests/e2e" --ignore "$(CURDIR)/tests/unit/publishers" 		"$(CURDIR)/tests"

test-publishers:
	cd app/publishers/FTP && poetry run python -m pytest -c "$(CURDIR)/$(BOT)/pyproject.toml" 		--rootdir "$(CURDIR)" -o addopts="" "$(CURDIR)/tests/unit/publishers/ftp"
	cd app/publishers/WordPress && poetry run python -m pytest -c "$(CURDIR)/$(BOT)/pyproject.toml" 		--rootdir "$(CURDIR)" -o addopts="" "$(CURDIR)/tests/unit/publishers/wordpress"
	cd app/publishers/Boosty && poetry run python -m pytest -c "$(CURDIR)/$(BOT)/pyproject.toml" 		--rootdir "$(CURDIR)" -o addopts="" "$(CURDIR)/tests/unit/publishers/boosty"

check:
	poetry -C $(BOT) run pre-commit run --show-diff-on-failure --color=always --all-files

# --- запуск бота локально ---------------------------------------------------

# main.py импортирует свои модули голыми именами (config, handlers, ...), так что
# запускать только из app/bot.
run:
	cd $(BOT) && poetry run python main.py run

migrate:
	cd $(BOT) && poetry run python main.py migrate -s False

makemigrations:
	cd $(BOT) && poetry run python main.py makemigrations -s False

# --- docker -----------------------------------------------------------------

docker-build:
	docker compose --env-file .env build

docker-up:
	docker compose up -d

docker-stop:
	docker compose down

docker-logs:
	docker compose logs -f --tail=200 bot publisher_ftp publisher_wordpress publisher_boosty
