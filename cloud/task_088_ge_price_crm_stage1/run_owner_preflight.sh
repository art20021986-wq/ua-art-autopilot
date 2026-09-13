#!/usr/bin/env bash
# Owner-console read-only TASK088 probe. Downloads go only to a private /tmp dir.
set -euo pipefail
TASK088_COMMIT=${1:?Pass the exact reviewed Git commit SHA}
case "$TASK088_COMMIT" in
  *[!0-9a-f]*|'') echo 'Invalid commit SHA' >&2; exit 2 ;;
esac
[[ ${#TASK088_COMMIT} -eq 40 ]] || exit 2
TASK088_WORKDIR=$(mktemp -d /tmp/task088-preflight.XXXXXXXX)
trap 'rm -rf -- "$TASK088_WORKDIR"' EXIT
TASK088_BASE="https://raw.githubusercontent.com/art20021986-wq/ua-art-autopilot/$TASK088_COMMIT/cloud/task_088_ge_price_crm_stage1"
for TASK088_FILE in owner_preflight.py capacity_probe.py ui_patch.py preflight.sha256; do
  curl --fail --silent --show-error --location --max-time 60 --retry 2 \
    --proto '=https' --proto-redir '=https' \
    "$TASK088_BASE/$TASK088_FILE" -o "$TASK088_WORKDIR/$TASK088_FILE"
done
(cd "$TASK088_WORKDIR" && sha256sum --check preflight.sha256 >&2)
TASK088_RESULT=$(mktemp /tmp/task088-preflight-result.XXXXXXXX.json)
task088_probe() {
  python3.10 -I -B -c 'import sys; p=sys.argv.pop(1); sys.path.insert(0,p); import owner_preflight; raise SystemExit(owner_preflight.main())' \
    "$TASK088_WORKDIR" "$@" > "$TASK088_WORKDIR/attempt.json" || return
  python3.10 -I -B -c 'import json,sys; json.load(open(sys.argv[1]))' "$TASK088_WORKDIR/attempt.json" || return
  cp -- "$TASK088_WORKDIR/attempt.json" "$TASK088_RESULT"
}
task088_probe
if python3.10 -I -B -c 'import json,sys; v=json.load(open(sys.argv[1])); sys.exit(0 if v.get("storage",{}).get("status") != "PASS" else 1)' "$TASK088_RESULT"; then
  if [[ -t 0 ]]; then
    echo 'Сервер не выдал лимит аккаунта автоматически.' >&2
    echo 'Откройте PythonAnywhere → Files и посмотрите общий лимит Disk quota.' >&2
    read -r -p 'Введите лимит с единицей, как на странице (например 35 GB или 35 GiB; Enter — пропустить): ' TASK088_QUOTA
    if [[ -n "$TASK088_QUOTA" ]]; then
      if ! task088_probe --account-quota "$TASK088_QUOTA"; then
        echo 'Повторная проверка не выполнена; сохранён исходный JSON.' >&2
      fi
    fi
  fi
fi
cat "$TASK088_RESULT"
echo "Результат сохранён: $TASK088_RESULT" >&2
echo 'Пришлите JSON в текущий чат. CRM и сайт не изменялись этой проверкой.' >&2
