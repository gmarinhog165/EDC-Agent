#!/usr/bin/env bash
set -euo pipefail

if ! command -v newman >/dev/null 2>&1; then
  echo "Erro: 'newman' nao encontrado. Instala com: npm i -g newman"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COLLECTION="${SCRIPT_DIR}/search_catalog_testbeds.postman_collection.json"
API_KEY_VALUE="${API_KEY:-password}"

if [ "$#" -gt 0 ]; then
  HOSTS=("$@")
else
  HOSTS=("http://192.168.112.126/provider/cp")
fi

echo
echo "=== Search Catalog Seed ==="
echo "Collection: ${COLLECTION}"
echo

for host in "${HOSTS[@]}"; do
  echo "-> Host: ${host}"
  newman run \
    --folder "Cleanup" \
    --env-var "HOST=${host}" \
    --env-var "API_KEY=${API_KEY_VALUE}" \
    "${COLLECTION}"

  newman run \
    --folder "TB02 - Seed All Assets" \
    --env-var "HOST=${host}" \
    --env-var "API_KEY=${API_KEY_VALUE}" \
    "${COLLECTION}"
done
