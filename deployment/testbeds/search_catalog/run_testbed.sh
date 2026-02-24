#!/usr/bin/env bash
set -euo pipefail

if ! command -v newman >/dev/null 2>&1; then
  echo "Erro: 'newman' nao encontrado. Instala com: npm i -g newman"
  exit 1
fi

if [ "$#" -lt 1 ]; then
  echo "Uso: $0 \"<FOLDER_NAME>\" [HOST1 HOST2 ...]"
  exit 1
fi

FOLDER_NAME="$1"
shift || true

COLLECTION="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../postman" && pwd)/search_catalog_testbeds.postman_collection.json"
API_KEY_VALUE="${API_KEY:-password}"

if [ "$#" -gt 0 ]; then
  HOSTS=("$@")
else
  HOSTS=("http://127.0.0.1/provider/cp")
fi

echo

echo "=== Search Catalog Testbed ==="
echo "Folder: ${FOLDER_NAME}"
echo "Collection: ${COLLECTION}"

echo
for host in "${HOSTS[@]}"; do
  echo "-> Host: ${host}"
  newman run \
    --folder "Cleanup" \
    --folder "${FOLDER_NAME}" \
    --env-var "HOST=${host}" \
    --env-var "API_KEY=${API_KEY_VALUE}" \
    "${COLLECTION}"
done
