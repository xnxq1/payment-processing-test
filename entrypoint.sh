#!/bin/bash
set -e

echo "Waiting for PostgreSQL at $POSTGRES_HOST:$POSTGRES_PORT..."
until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\q' 2>/dev/null; do
  echo "PostgreSQL is unavailable - sleeping..."
  sleep 2
done
echo "PostgreSQL is up."

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "Running Alembic migrations..."
  alembic upgrade head
  echo "Migrations applied."
fi

echo "Starting: $@"
exec "$@"
