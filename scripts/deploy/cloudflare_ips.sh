#!/usr/bin/env bash
# Диапазоны IP Cloudflare (https://www.cloudflare.com/ips/) для двух задач: настоящий адрес клиента в nginx и закрытый
# для остальных порт 80/443 сервера, чтобы origin нельзя было обойти мимо Cloudflare.
#   cloudflare_ips.sh nginx   — пишет deploy/cloudflare_real_ip.inc (set_real_ip_from + CF-Connecting-IP); потом
#                               `docker compose ... restart web`;
#   cloudflare_ips.sh ufw     — разрешает 80/443 только этим диапазонам (нужен ufw и root); остальным они закрыты;
#   cloudflare_ips.sh print   — просто список.
# Список Cloudflare меняется редко: запускать раз в месяц (cron) и после объявлений Cloudflare. Ничего не хранит и
# не использует токенов — читает публичные списки.
set -euo pipefail

MODE="${1:-print}"
OUT="${CLOUDFLARE_REAL_IP_FILE:-$(dirname "$0")/../../deploy/cloudflare_real_ip.inc}"
CIDR='^[0-9a-fA-F:.]+/[0-9]{1,3}$'

fetch() {
    local list
    list="$(curl -fsS --max-time 20 "https://www.cloudflare.com/$1")"
    [ -n "$list" ] || { echo "пустой список $1" >&2; exit 1; }
    # Чужой ответ не должен попасть в конфиг nginx или правила файрвола: только строки вида адрес/длина.
    while IFS= read -r line; do
        [[ "$line" =~ $CIDR ]] || { echo "неожиданная строка в $1: $line" >&2; exit 1; }
    done <<< "$list"
    printf '%s\n' "$list"
}

RANGES="$(fetch ips-v4; fetch ips-v6)"

case "$MODE" in
    print)
        printf '%s\n' "$RANGES" ;;
    nginx)
        mkdir -p "$(dirname "$OUT")"
        {
            echo "# Создан scripts/deploy/cloudflare_ips.sh $(date -u +%F): адреса Cloudflare; клиента берём из CF-Connecting-IP."
            while IFS= read -r cidr; do echo "set_real_ip_from $cidr;"; done <<< "$RANGES"
            echo "real_ip_header CF-Connecting-IP;"
        } > "$OUT"
        echo "записан $OUT" ;;
    ufw)
        while IFS= read -r cidr; do
            ufw allow proto tcp from "$cidr" to any port 80,443 comment 'cloudflare'
        done <<< "$RANGES"
        echo "Правила добавлены. Чтобы закрыть 80/443 остальным: ufw default deny incoming (SSH разрешите отдельно: ufw allow OpenSSH)." ;;
    *)
        echo "использование: $0 nginx|ufw|print" >&2; exit 2 ;;
esac
