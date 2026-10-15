ARG POSTGRES
FROM ${POSTGRES}
COPY --chmod=755 infra/compose/init-databases.sh /docker-entrypoint-initdb.d/10-reguard.sh
COPY --chmod=755 infra/k3s/backup/run.sh /opt/reguard/backup.sh
