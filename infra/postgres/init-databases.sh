#!/bin/sh
# One database per service: each service owns its data and nothing else reads it.
set -e
for db in accounts commercial operations billing notifications; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" -c "CREATE DATABASE halyard_$db;"
done
