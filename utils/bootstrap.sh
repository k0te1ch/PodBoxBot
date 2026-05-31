#!/usr/bin/env bash
# bootstrap.sh — первичная инициализация PodBoxBot на чистом prod-сервере.
#
# Что делает (по фазам):
#   0. Preflight: docker/compose/curl/jq на месте, .env существует, репо в нужном состоянии.
#   1. Backup существующих docker-volumes в ./backups/<ts>/ (если есть что бэкапить).
#   2. docker compose pull && build.
#   3. Поэтапный up: kafka -> schema-registry -> kafka-init -> schema-watcher -> остальное.
#      На каждом шаге ждём healthy / completed.
#   4. Verify topics: сверка с app/kafka/topics.yaml.
#   5. Verify schemas: сверка с app/shared/kafka/schemas/*.avsc.
#   6. Smoke pub/sub: туда-обратно через временный топик bootstrap.smoke.<ts>.
#   7. Summary.
#
# Идемпотентен: повторный запуск ничего не ломает.
# Не предназначен для прода с горячим трафиком — на первой выкатке окей,
# для апгрейдов используй `docker compose up -d --build` отдельно.
#
# Зависимости: bash 4+, docker, docker compose (v2 предпочтительно, v1 тоже
# поддерживается), curl, jq.

set -euo pipefail

# === НАСТРОЙКИ ===
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BACKUP_DIR="$REPO_ROOT/backups/$(date -u +%Y-%m-%dT%H-%M-%SZ)"
# COMPOSE — команда compose; задаётся в preflight() по результату детекта v1/v2.
# COMPOSE_FILE — какой compose-файл использовать. По умолчанию docker-compose.yml
# (прямой коннект); для режима за блокировкой передай -f docker-compose.tun2socks.yml.
COMPOSE=""
COMPOSE_FILE="docker-compose.yml"
SMOKE_TOPIC="bootstrap.smoke.$(date -u +%s)"
WAIT_HEALTHY_TIMEOUT=180  # секунд на healthcheck одного сервиса
WAIT_INIT_TIMEOUT=120     # секунд на kafka-init
WAIT_SCHEMA_REG=60        # секунд на регистрацию схем schema-watcher'ом

# Volumes, которые имеет смысл бэкапить (state). telegram-bot-api-data — кэш,
# не бэкапим; pushgateway/prometheus_data восстанавливаются из сборщиков.
BACKUP_VOLUMES=(
  "redisdata"
  "kafka_data"
  "wordpress_data"
  "files"
  "grafana_data"
  "loki_data"
)

# === ЛОГИ ===
log_info()  { printf '\033[36m[i]\033[0m %s\n' "$*"; }
log_ok()    { printf '\033[32m[+]\033[0m %s\n' "$*"; }
log_warn()  { printf '\033[33m[!]\033[0m %s\n' "$*" >&2; }
log_err()   { printf '\033[31m[x]\033[0m %s\n' "$*" >&2; }
die()       { log_err "$*"; exit 1; }

usage() {
  cat <<EOF
usage: $(basename "$0") [-f FILE] [-h]

Bootstraps PodBoxBot stack on a fresh prod host.

Options:
  -f, --file FILE   compose-файл (по умолчанию: docker-compose.yml).
                    Для режима за блокировкой с tun2socks: docker-compose.tun2socks.yml.
  -h, --help        эта справка.
EOF
}

parse_args() {
  while (( $# > 0 )); do
    case "$1" in
      -f|--file)
        [[ $# -ge 2 ]] || die "$1 требует аргумент"
        COMPOSE_FILE="$2"
        shift 2
        ;;
      -h|--help)
        usage; exit 0
        ;;
      *)
        log_err "неизвестный аргумент: $1"
        usage >&2
        exit 2
        ;;
    esac
  done
  [[ -f "$REPO_ROOT/$COMPOSE_FILE" ]] || die "compose-файл не найден: $REPO_ROOT/$COMPOSE_FILE"
}

# === CLEANUP ===
cleanup() {
  local rc=$?
  # Прибираем за smoke-тестом, даже если упали посередине.
  # Проверяем kafka напрямую через docker ps, чтобы не зависеть от опций compose.
  if [[ -n "$COMPOSE" ]] && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx podboxbot_kafka; then
    if $COMPOSE exec -T kafka kafka-topics \
         --bootstrap-server kafka:9092 --list 2>/dev/null \
       | grep -qx "$SMOKE_TOPIC"; then
      log_info "Cleanup: удаляю smoke-топик $SMOKE_TOPIC"
      $COMPOSE exec -T kafka kafka-topics \
        --bootstrap-server kafka:9092 --delete --topic "$SMOKE_TOPIC" \
        >/dev/null 2>&1 || true
    fi
  fi
  exit $rc
}
trap cleanup EXIT

# === ФАЗА 0: PREFLIGHT ===
preflight() {
  log_info "Phase 0: preflight"

  for cmd in docker curl jq; do
    command -v "$cmd" >/dev/null || die "не найден '$cmd' — установи и повтори"
  done

  # Детект compose v2 -> v1. v2 предпочтительнее (v1 EOL с июля 2023).
  if docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose -f $COMPOSE_FILE"
    log_info "  compose: v2 ($(docker compose version --short 2>/dev/null || echo '?')), file=$COMPOSE_FILE"
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE="docker-compose -f $COMPOSE_FILE"
    log_warn "  compose: v1 ($(docker-compose --version 2>/dev/null | head -1)) — устарел, рекомендую"
    log_warn "  поставить плагин v2: sudo apt-get install docker-compose-plugin"
    log_info "  file=$COMPOSE_FILE"
  else
    die "ни 'docker compose' (v2), ни 'docker-compose' (v1) не доступны"
  fi

  [[ -f "$REPO_ROOT/.env" ]] || die ".env не найден в $REPO_ROOT (скопируй .env.example и заполни)"
  [[ -f "$REPO_ROOT/docker-compose.yml" ]] || die "docker-compose.yml не найден"

  # Проверяем обязательные ключи в .env по .env.example, чтобы не упасть на середине.
  # Игнорируем комментарии и пустые строки, сверяем только имена переменных.
  if [[ -f "$REPO_ROOT/.env.example" ]]; then
    local missing=()
    while IFS= read -r key; do
      [[ -z "$key" ]] && continue
      if ! grep -qE "^\s*${key}\s*=" "$REPO_ROOT/.env"; then
        missing+=("$key")
      fi
    done < <(grep -oE '^\s*[A-Z_][A-Z0-9_]*\s*=' "$REPO_ROOT/.env.example" \
             | sed -E 's/[[:space:]]*=.*$//; s/^[[:space:]]+//')

    if (( ${#missing[@]} > 0 )); then
      log_warn ".env не содержит ключи из .env.example:"
      printf '    - %s\n' "${missing[@]}" >&2
      read -r -p "Продолжить всё равно? [y/N] " ans
      [[ "$ans" =~ ^[Yy]$ ]] || die "прерывание по запросу пользователя"
    fi
  fi

  log_ok "preflight passed"
}

# === ФАЗА 1: BACKUP ===
backup_volumes() {
  log_info "Phase 1: backup существующих volumes"

  local any=0
  for vol in "${BACKUP_VOLUMES[@]}"; do
    # docker volume имена с префиксом проекта compose; маппим оба варианта.
    local full
    full=$(docker volume ls --format '{{.Name}}' | grep -E "(^|_)${vol}\$" | head -1 || true)
    if [[ -z "$full" ]]; then
      continue
    fi

    if (( any == 0 )); then
      mkdir -p "$BACKUP_DIR"
      log_info "Бэкаплю в $BACKUP_DIR"
      any=1
    fi

    log_info "  ${full} -> ${vol}.tgz"
    docker run --rm \
      -v "${full}:/data:ro" \
      -v "${BACKUP_DIR}:/backup" \
      alpine:3 \
      tar czf "/backup/${vol}.tgz" -C /data . 2>/dev/null \
      || log_warn "  не смог забэкапить $full (возможно volume пустой) — пропускаю"
  done

  if (( any == 0 )); then
    log_info "  существующих volumes не нашёл — это первый запуск, бэкап не нужен"
  else
    log_ok "  backup готов: $BACKUP_DIR"
  fi
}

# === ФАЗА 2: PULL + BUILD ===
pull_and_build() {
  log_info "Phase 2: pull + build образов"
  # --ignore-buildable есть только в v2; в v1 просто игнорим ошибки на build-only
  # сервисах (они всё равно соберутся следующим шагом).
  if [[ "$COMPOSE" == "docker compose" ]]; then
    $COMPOSE pull --ignore-buildable
  else
    $COMPOSE pull 2>&1 | grep -vE "(no such image|pull access denied)" || true
  fi
  $COMPOSE build
  log_ok "образы готовы"
}

# === ФАЗА 3: ПОЭТАПНЫЙ UP ===
wait_healthy() {
  local svc=$1
  local timeout=${2:-$WAIT_HEALTHY_TIMEOUT}
  local elapsed=0
  log_info "  жду healthy: $svc (timeout ${timeout}s)"
  while (( elapsed < timeout )); do
    local cid
    cid=$($COMPOSE ps -q "$svc" 2>/dev/null || true)
    if [[ -n "$cid" ]]; then
      local status
      status=$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo "no-healthcheck")
      case "$status" in
        healthy)        log_ok "  $svc healthy (${elapsed}s)"; return 0 ;;
        no-healthcheck) log_warn "  $svc без healthcheck — считаю готовым по факту запуска"; return 0 ;;
        unhealthy)      die "$svc unhealthy" ;;
      esac
    fi
    sleep 3
    elapsed=$(( elapsed + 3 ))
  done
  die "$svc не стал healthy за ${timeout}s"
}

wait_completed() {
  local svc=$1
  local timeout=${2:-$WAIT_INIT_TIMEOUT}
  local elapsed=0
  log_info "  жду completion: $svc (timeout ${timeout}s)"
  while (( elapsed < timeout )); do
    local cid
    cid=$($COMPOSE ps -aq "$svc" 2>/dev/null || true)
    if [[ -n "$cid" ]]; then
      local exit_code
      exit_code=$(docker inspect -f '{{.State.ExitCode}}' "$cid" 2>/dev/null || echo "")
      local state
      state=$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || echo "")
      if [[ "$state" == "exited" ]]; then
        if [[ "$exit_code" == "0" ]]; then
          log_ok "  $svc completed ok (${elapsed}s)"
          return 0
        else
          $COMPOSE logs "$svc" | tail -50 >&2
          die "$svc exited with code $exit_code"
        fi
      fi
    fi
    sleep 3
    elapsed=$(( elapsed + 3 ))
  done
  die "$svc не завершился за ${timeout}s"
}

bring_up_stack() {
  log_info "Phase 3: подъём стека по слоям"

  log_info "  layer 1: kafka"
  $COMPOSE up -d kafka
  wait_healthy kafka

  log_info "  layer 2: schema-registry"
  $COMPOSE up -d schema-registry
  wait_healthy schema-registry

  log_info "  layer 3: kafka-init (создание топиков)"
  $COMPOSE up -d kafka-init
  wait_completed kafka-init

  log_info "  layer 4: schema-watcher (регистрация .avsc)"
  $COMPOSE up -d schema-watcher
  log_info "  жду ${WAIT_SCHEMA_REG}s на регистрацию схем..."
  sleep "$WAIT_SCHEMA_REG"

  log_info "  layer 5: остальное (bot, publishers, monitoring)"
  $COMPOSE up -d

  log_ok "стек поднят"
}

# === ФАЗА 4: VERIFY TOPICS ===
verify_topics() {
  log_info "Phase 4: сверка топиков"

  local expected
  expected=$(grep -E '^\s*- name:' "$REPO_ROOT/app/kafka/topics.yaml" \
             | sed -E 's/^\s*- name:\s*//')
  local actual
  actual=$($COMPOSE exec -T kafka kafka-topics --bootstrap-server kafka:9092 --list)

  local missing=()
  while IFS= read -r t; do
    [[ -z "$t" ]] && continue
    if ! echo "$actual" | grep -qx "$t"; then
      missing+=("$t")
    fi
  done <<< "$expected"

  if (( ${#missing[@]} > 0 )); then
    log_err "не созданы топики:"
    printf '    - %s\n' "${missing[@]}" >&2
    $COMPOSE logs kafka-init | tail -30 >&2
    die "топики из topics.yaml не появились в кластере"
  fi

  log_ok "  все топики из topics.yaml на месте ($(echo "$expected" | wc -l) шт.)"
}

# === ФАЗА 5: VERIFY SCHEMAS ===
verify_schemas() {
  log_info "Phase 5: сверка схем в Schema Registry"

  local expected_subjects=()
  while IFS= read -r f; do
    local stem
    stem=$(basename "$f" .avsc)
    expected_subjects+=("${stem}-value")
  done < <(find "$REPO_ROOT/app/shared/kafka/schemas" -name '*.avsc' -type f)

  (( ${#expected_subjects[@]} > 0 )) || { log_warn "  .avsc файлов нет — пропускаю"; return 0; }

  local actual
  actual=$($COMPOSE exec -T schema-registry curl -s http://localhost:8081/subjects | jq -r '.[]?')

  local missing=()
  for s in "${expected_subjects[@]}"; do
    if ! echo "$actual" | grep -qx "$s"; then
      missing+=("$s")
    fi
  done

  if (( ${#missing[@]} > 0 )); then
    log_err "не зарегистрированы subjects:"
    printf '    - %s\n' "${missing[@]}" >&2
    $COMPOSE logs schema-watcher | tail -30 >&2
    die "schema-watcher не зарегистрировал все схемы — увеличь WAIT_SCHEMA_REG или проверь логи"
  fi

  log_ok "  все subjects из app/shared/kafka/schemas зарегистрированы (${#expected_subjects[@]} шт.)"
}

# === ФАЗА 6: SMOKE PUB/SUB ===
smoke_pubsub() {
  log_info "Phase 6: smoke pub/sub через топик $SMOKE_TOPIC"

  $COMPOSE exec -T kafka kafka-topics \
    --bootstrap-server kafka:9092 \
    --create --topic "$SMOKE_TOPIC" \
    --partitions 1 --replication-factor 1 >/dev/null

  local payload="bootstrap-$(date -u +%s)-$RANDOM"

  echo "$payload" | $COMPOSE exec -T kafka kafka-console-producer \
    --bootstrap-server kafka:9092 --topic "$SMOKE_TOPIC" >/dev/null 2>&1

  local got
  got=$($COMPOSE exec -T kafka kafka-console-consumer \
          --bootstrap-server kafka:9092 \
          --topic "$SMOKE_TOPIC" \
          --from-beginning --max-messages 1 \
          --timeout-ms 15000 2>/dev/null | head -1)

  if [[ "$got" != "$payload" ]]; then
    die "smoke pub/sub fail: послал '$payload', получил '$got'"
  fi

  log_ok "  туда-обратно прошло"
  # cleanup сделает trap
}

# === ФАЗА 7: SUMMARY ===
print_summary() {
  log_info "Phase 7: summary"
  echo
  $COMPOSE ps
  echo
  log_ok "bootstrap завершён успешно"
  echo "Дальше: проверь Grafana на http://<server>:3000 (admin/admin) и Kafdrop на :9000."
  echo "Логи бота: docker compose logs -f bot"
}

# === MAIN ===
main() {
  parse_args "$@"
  preflight
  backup_volumes
  pull_and_build
  bring_up_stack
  verify_topics
  verify_schemas
  smoke_pubsub
  print_summary
}

main "$@"
