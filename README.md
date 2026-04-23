# claude

Claude Code の Mattermost 双方向連携フック。Claude Code の停止・ツール実行・通知を Mattermost に転送し、返信で元のターミナルから作業を継続できます。

## 機能

| フックイベント | 動作 |
|---|---|
| **PreToolUse** (Bash) | Bash コマンド実行前に Mattermost で `yes`/`no` 承認 |
| **Stop** | セッション終了時にサマリーを投稿。返信で元ターミナルで作業継続 |
| **Notification** | Claude からの通知を Mattermost へ転送 |

### Stop フックの動作

```
Claude がセッション終了
    ↓
Mattermost にサマリー投稿（最後の指示・実行結果）
    ↓ ユーザーが Mattermost で返信
stderr に返信内容を書き込んで exit 2
    ↓
Claude Code: セッション継続
Claude: 返信内容を新しい指示として解釈して作業継続
    ↓ ループ
```

## 必要条件

- Python 3.8 以上（stdlib のみ使用、追加パッケージ不要）
- Mattermost Bot アカウントと Personal Access Token
- Claude Code

## セットアップ

### 1. Mattermost Bot の準備

1. Mattermost の管理画面で Bot アカウントを作成
2. 通知を送りたいチャンネルに Bot を招待
3. Bot の Personal Access Token を発行
4. チャンネル ID を取得（チャンネル URL または API で確認）

### 2. 設定ファイルの作成

```bash
cp .env.example ~/.claude/mattermost.env
```

`~/.claude/mattermost.env` を編集して実際の値を設定：

```bash
MATTERMOST_URL=https://your-mattermost.example.com
MATTERMOST_BOT_TOKEN=your-personal-access-token-here
MATTERMOST_CHANNEL_ID=your-channel-id-here
MATTERMOST_ENABLED=1
```

### 3. スクリプトに実行権限を付与

```bash
chmod +x hooks/mattermost_notify.py
chmod +x hooks/mattermost_toggle.sh
```

### 4. hooks の登録（初回のみ）

`~/.claude/settings.json` に以下が追加されていることを確認します（自動設定済み）：

```json
{
    "hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 /home/user/claude/hooks/mattermost_notify.py"}]}],
        "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "python3 /home/user/claude/hooks/mattermost_notify.py"}]}],
        "Notification": [{"matcher": "", "hooks": [{"type": "command", "command": "python3 /home/user/claude/hooks/mattermost_notify.py"}]}]
    }
}
```

## 使い方

### オン/オフの切り替え

```bash
./hooks/mattermost_toggle.sh on     # 有効化
./hooks/mattermost_toggle.sh off    # 無効化
./hooks/mattermost_toggle.sh status # 現在の状態を確認
```

### Mattermost での操作

| 操作 | 方法 |
|---|---|
| Bash コマンドを承認 | `yes`（または `y`、`ok`、`はい`、`承認`）と返信 |
| Bash コマンドを拒否 | `no`（またはそれ以外の文字列）と返信 |
| セッションを継続 | Stop 通知に次のタスクを返信 |
| セッションを終了 | Stop 通知に `exit` と返信 |

## 設定オプション

`.env.example` を参照してください。

| 変数 | デフォルト | 説明 |
|---|---|---|
| `MATTERMOST_ENABLED` | `1` | `1`=有効 / `0`=無効 |
| `MATTERMOST_REPLY_TIMEOUT` | `300` | Stop フックの返信待機秒数 |
| `MATTERMOST_POLL_INTERVAL` | `15` | ポーリング間隔秒数 |
| `MATTERMOST_APPROVAL_TIMEOUT` | `120` | PreToolUse の承認待機秒数 |
| `MATTERMOST_DEFAULT_APPROVE` | `1` | タイムアウト時 `1`=自動承認 / `0`=自動ブロック |
| `MATTERMOST_SUMMARY_CHARS` | `800` | サマリー最大文字数 |

## ログ

エラーは `~/.claude/mattermost.log` に記録されます。

```bash
tail -f ~/.claude/mattermost.log
```

## ライセンス

MIT
