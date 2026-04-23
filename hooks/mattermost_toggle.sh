#!/bin/bash
# Mattermost 通知機能のオン/オフを切り替えるスクリプト
# Usage: ./hooks/mattermost_toggle.sh [on|off|status]

ENV_FILE="$HOME/.claude/mattermost.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "エラー: $ENV_FILE が見つかりません"
    echo "先に .env.example を $ENV_FILE としてコピーして設定してください"
    exit 1
fi

case "${1:-}" in
    on)
        if grep -q "^MATTERMOST_ENABLED=" "$ENV_FILE"; then
            sed -i 's/^MATTERMOST_ENABLED=.*/MATTERMOST_ENABLED=1/' "$ENV_FILE"
        else
            echo "MATTERMOST_ENABLED=1" >> "$ENV_FILE"
        fi
        echo "Mattermost 通知: ON"
        ;;
    off)
        if grep -q "^MATTERMOST_ENABLED=" "$ENV_FILE"; then
            sed -i 's/^MATTERMOST_ENABLED=.*/MATTERMOST_ENABLED=0/' "$ENV_FILE"
        else
            echo "MATTERMOST_ENABLED=0" >> "$ENV_FILE"
        fi
        echo "Mattermost 通知: OFF"
        ;;
    status)
        current=$(grep "^MATTERMOST_ENABLED=" "$ENV_FILE" | cut -d= -f2)
        if [[ "$current" == "1" ]]; then
            echo "Mattermost 通知: ON"
        else
            echo "Mattermost 通知: OFF"
        fi
        ;;
    *)
        echo "Usage: $0 [on|off|status]"
        echo ""
        echo "  on     - Mattermost 通知を有効にする"
        echo "  off    - Mattermost 通知を無効にする"
        echo "  status - 現在の状態を表示する"
        exit 1
        ;;
esac
