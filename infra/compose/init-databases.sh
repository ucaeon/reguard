#!/bin/bash
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres --set=pw="$MEMBER_DB_PASSWORD" <<'SQL'
CREATE ROLE reguard_member LOGIN PASSWORD :'pw';
CREATE DATABASE reguard_member OWNER reguard_member;
REVOKE ALL ON DATABASE reguard_member FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres --set=pw="$SAFETY_DB_PASSWORD" <<'SQL'
CREATE ROLE reguard_safety LOGIN PASSWORD :'pw';
CREATE DATABASE reguard_safety OWNER reguard_safety;
REVOKE ALL ON DATABASE reguard_safety FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres --set=pw="$NOTIFICATION_DB_PASSWORD" <<'SQL'
CREATE ROLE reguard_notification LOGIN PASSWORD :'pw';
CREATE DATABASE reguard_notification OWNER reguard_notification;
REVOKE ALL ON DATABASE reguard_notification FROM PUBLIC;
SQL
