#!/usr/bin/env bash
set -euo pipefail

readonly REPO_DIR="/opt/moment"
readonly COMPOSE_FILE="${REPO_DIR}/backend/compose.yaml"
readonly ENV_FILE="/etc/moment/backend.env"
readonly LOG_TAG="moment-deploy"

log()
{
    logger -t "${LOG_TAG}" -- "$*"
    printf '%s\n' "$*"
}

healthcheck()
{
    local attempt

    for attempt in $(seq 1 20)
    do
        if docker compose -f "${COMPOSE_FILE}" ps --status running web \
            | grep -q web \
            && docker compose -f "${COMPOSE_FILE}" exec -T web \
                curl --fail --silent http://localhost:8000/healthz >/dev/null
        then
            return 0
        fi

        sleep 3
    done

    return 1
}

cd "${REPO_DIR}"
export MOMENT_ENV_FILE="${ENV_FILE}"

if ! git diff --quiet || ! git diff --cached --quiet
then
    log "Refusing deployment because the checkout has local changes."
    exit 1
fi

previous_commit="$(git rev-parse HEAD)"
git fetch --quiet origin main
target_commit="$(git rev-parse origin/main)"

if [ "${previous_commit}" = "${target_commit}" ]
then
    if healthcheck
    then
        exit 0
    fi

    log "Current commit is not healthy; reconciling ${target_commit}."
fi

log "Deploying ${target_commit} (previously ${previous_commit})."
git reset --hard "${target_commit}"

if docker compose -f "${COMPOSE_FILE}" up -d --build --remove-orphans \
    && healthcheck
then
    log "Deployment of ${target_commit} is healthy."
    exit 0
fi

log "Deployment failed health checks; rolling back to ${previous_commit}."
git reset --hard "${previous_commit}"
docker compose -f "${COMPOSE_FILE}" up -d --build --remove-orphans

if healthcheck
then
    log "Rollback completed successfully."
else
    log "Rollback did not become healthy. Manual intervention is required."
fi

exit 1
