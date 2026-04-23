#!/usr/bin/env python3
"""
Claude Code → Mattermost 双方向連携フック

対応イベント:
  PreToolUse  : ツール実行前に Mattermost で承認を求める（yes/no 返信）
  Stop        : セッション終了時にサマリーを投稿、返信で元ターミナルで継続
  Notification: Claude からの通知を Mattermost へ転送

設定: ~/.claude/mattermost.env
トグル: MATTERMOST_ENABLED=1（有効）/ 0（無効）
"""

import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

# ─── 定数 ───────────────────────────────────────────────────────────────

ENV_FILE = Path.home() / ".claude" / "mattermost.env"
BOT_USER_ID_CACHE = Path.home() / ".claude" / ".mattermost_bot_user_id"
LOG_FILE = Path.home() / ".claude" / "mattermost.log"


# ─── 共通ユーティリティ ───────────────────────────────────────────────────

def log(msg: str) -> None:
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def load_config() -> dict | None:
    """~/.claude/mattermost.env を読み込んで設定 dict を返す。無効なら None。"""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip()

    # 環境変数で上書き可能
    for key in list(env.keys()):
        if key in os.environ:
            env[key] = os.environ[key]

    if env.get("MATTERMOST_ENABLED", "0") != "1":
        return None

    required = ["MATTERMOST_URL", "MATTERMOST_BOT_TOKEN", "MATTERMOST_CHANNEL_ID"]
    missing = [k for k in required if not env.get(k)]
    if missing:
        log(f"設定が不足しています: {missing}")
        return None

    return {
        "url": env["MATTERMOST_URL"].rstrip("/"),
        "token": env["MATTERMOST_BOT_TOKEN"],
        "channel_id": env["MATTERMOST_CHANNEL_ID"],
        "reply_timeout": int(env.get("MATTERMOST_REPLY_TIMEOUT", "300")),
        "approval_timeout": int(env.get("MATTERMOST_APPROVAL_TIMEOUT", "120")),
        "poll_interval": int(env.get("MATTERMOST_POLL_INTERVAL", "15")),
        "default_approve": env.get("MATTERMOST_DEFAULT_APPROVE", "1") == "1",
        "summary_chars": int(env.get("MATTERMOST_SUMMARY_CHARS", "800")),
    }


def api_request(config: dict, method: str, path: str, body: dict | None = None) -> dict:
    """Mattermost REST API を呼び出す。"""
    url = f"{config['url']}/api/v4{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {config['token']}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} {path}: {body_text}") from e


def get_bot_user_id(config: dict) -> str:
    """ボット自身の user_id を取得（キャッシュあり）。"""
    if BOT_USER_ID_CACHE.exists():
        cached = BOT_USER_ID_CACHE.read_text().strip()
        if cached:
            return cached
    data = api_request(config, "GET", "/users/me")
    user_id = data["id"]
    BOT_USER_ID_CACHE.write_text(user_id)
    return user_id


def send_message(config: dict, text: str, root_id: str | None = None) -> str:
    """Mattermost にメッセージを投稿して post_id を返す。"""
    body: dict = {"channel_id": config["channel_id"], "message": text}
    if root_id:
        body["root_id"] = root_id
    data = api_request(config, "POST", "/posts", body)
    return data["id"]


def get_replies_after(
    config: dict, post_id: str, since_ts: int, bot_user_id: str
) -> list[str]:
    """スレッド内の since_ts より後の（ボット以外の）返信テキスト一覧を返す。"""
    try:
        data = api_request(config, "GET", f"/posts/{post_id}/thread")
    except Exception as e:
        log(f"スレッド取得失敗: {e}")
        return []

    posts = data.get("posts", {})
    order = data.get("order", [])
    replies = []
    for pid in order:
        post = posts.get(pid, {})
        if (
            post.get("id") != post_id
            and post.get("user_id") != bot_user_id
            and post.get("create_at", 0) > since_ts
        ):
            replies.append(post.get("message", "").strip())
    return replies


def parse_transcript(path: str, max_chars: int) -> dict:
    """transcript.jsonl から最後の指示と結果を抽出する。"""
    result = {"instruction": "", "result": ""}
    if not path or not os.path.exists(path):
        return result

    try:
        lines = Path(path).read_text(errors="replace").strip().splitlines()
    except Exception:
        return result

    last_user = ""
    last_assistant = ""

    for line in lines:
        try:
            entry = json.loads(line)
        except Exception:
            continue

        # transcript.jsonl のエントリ形式に対応
        msg = entry.get("message", entry)
        role = msg.get("role", "")
        content = msg.get("content", "")

        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            text = "\n".join(parts)
        else:
            continue

        text = text.strip()
        if not text:
            continue

        if role == "user":
            last_user = text
        elif role == "assistant":
            last_assistant = text

    def trim(s: str) -> str:
        return s[:max_chars] + "..." if len(s) > max_chars else s

    result["instruction"] = trim(last_user)
    result["result"] = trim(last_assistant)
    return result


def poll_for_reply(
    config: dict, post_id: str, since_ts: int, bot_user_id: str, timeout: int
) -> str | None:
    """タイムアウトまで返信をポーリングし、最初の返信テキストを返す。"""
    deadline = time.time() + timeout
    interval = config["poll_interval"]
    while time.time() < deadline:
        replies = get_replies_after(config, post_id, since_ts, bot_user_id)
        if replies:
            return replies[0]
        remaining = int(deadline - time.time())
        sys.stderr.write(
            f"\r⏳ Mattermost の返信を待っています... 残り {remaining} 秒   "
        )
        sys.stderr.flush()
        time.sleep(min(interval, max(0, remaining)))
    sys.stderr.write("\n")
    return None


# ─── イベント別ハンドラ ─────────────────────────────────────────────────


def handle_pre_tool_use(hook_input: dict, config: dict) -> None:
    """PreToolUse: Mattermost で承認を求め、結果を stdout に JSON 出力する。"""
    tool_name = hook_input.get("tool_name", "不明")
    tool_input = hook_input.get("tool_input", {})
    session_id = hook_input.get("session_id", "")[:8]
    cwd = hook_input.get("cwd", "")

    # tool_input を読みやすい形に
    if tool_name == "Bash":
        cmd_preview = tool_input.get("command", "")
        input_text = f"```bash\n{cmd_preview}\n```"
    else:
        input_text = f"```json\n{json.dumps(tool_input, ensure_ascii=False, indent=2)}\n```"

    timeout = config["approval_timeout"]
    message = (
        f"#### 🔧 ツール実行の承認が必要です\n"
        f"**セッション**: `{session_id}` | **ディレクトリ**: `{cwd}`\n\n"
        f"**ツール**: `{tool_name}`\n"
        f"**引数**:\n{input_text}\n\n"
        f"---\n`yes` で承認 / `no` で拒否（タイムアウト: {timeout}秒）"
    )

    try:
        bot_user_id = get_bot_user_id(config)
        post_id = send_message(config, message)
        since_ts = int(time.time() * 1000)

        reply = poll_for_reply(config, post_id, since_ts, bot_user_id, timeout)
    except Exception as e:
        log(f"PreToolUse エラー: {e}")
        # エラー時はデフォルト動作
        if config["default_approve"]:
            print(json.dumps({"decision": "approve"}))
        else:
            print(json.dumps({"decision": "block", "reason": "Mattermost 通信エラー"}))
        return

    if reply is None:
        # タイムアウト
        if config["default_approve"]:
            try:
                send_message(config, "⏰ タイムアウト → 自動承認しました", root_id=post_id)
            except Exception:
                pass
            print(json.dumps({"decision": "approve"}))
        else:
            try:
                send_message(config, "⏰ タイムアウト → 自動ブロックしました", root_id=post_id)
            except Exception:
                pass
            print(json.dumps({"decision": "block", "reason": "タイムアウトによる自動ブロック"}))
        return

    reply_lower = reply.lower().strip()
    if reply_lower in ("yes", "y", "ok", "はい", "承認"):
        try:
            send_message(config, "✅ 承認されました", root_id=post_id)
        except Exception:
            pass
        print(json.dumps({"decision": "approve"}))
    else:
        try:
            send_message(config, f"🚫 拒否されました: {reply}", root_id=post_id)
        except Exception:
            pass
        print(json.dumps({"decision": "block", "reason": f"Mattermost で拒否: {reply}"}))


def handle_stop(hook_input: dict, config: dict) -> None:
    """Stop: サマリーを Mattermost に投稿し、返信を元ターミナルへの指示として返す。"""
    session_id = hook_input.get("session_id", "")[:8]
    cwd = hook_input.get("cwd", "")
    transcript_path = hook_input.get("transcript_path", "")

    transcript = parse_transcript(transcript_path, config["summary_chars"])
    instruction = transcript["instruction"] or "（取得できませんでした）"
    result = transcript["result"] or "（取得できませんでした）"

    timeout = config["reply_timeout"]
    message = (
        f"#### ✅ Claude Code セッション完了\n"
        f"**セッション**: `{session_id}` | **ディレクトリ**: `{cwd}`\n\n"
        f"**最後の指示**:\n> {instruction.replace(chr(10), chr(10) + '> ')}\n\n"
        f"**実行結果**:\n> {result.replace(chr(10), chr(10) + '> ')}\n\n"
        f"---\n返信で継続（{timeout}秒以内）/ `exit` でセッション終了"
    )

    try:
        bot_user_id = get_bot_user_id(config)
        post_id = send_message(config, message)
        since_ts = int(time.time() * 1000)
    except Exception as e:
        log(f"Stop 通知エラー: {e}")
        sys.exit(0)

    reply = poll_for_reply(config, post_id, since_ts, bot_user_id, timeout)

    if reply is None:
        sys.stderr.write("\n⏰ タイムアウト: セッションを終了します\n")
        try:
            send_message(config, "⏰ タイムアウト: セッションを終了しました", root_id=post_id)
        except Exception:
            pass
        sys.exit(0)

    if reply.lower().strip() == "exit":
        sys.stderr.write("\n👋 exit を受信: セッションを終了します\n")
        try:
            send_message(config, "👋 セッションを終了しました", root_id=post_id)
        except Exception:
            pass
        sys.exit(0)

    # 返信を Claude への新しい指示として stderr に書き込み、exit 2 で継続させる
    try:
        send_message(config, f"📨 指示を受け取りました:\n> {reply}", root_id=post_id)
    except Exception:
        pass

    sys.stderr.write(f"\n[Mattermost] {reply}\n")
    sys.exit(2)


def handle_notification(hook_input: dict, config: dict) -> None:
    """Notification: Claude の通知を Mattermost に転送する。"""
    session_id = hook_input.get("session_id", "")[:8]
    cwd = hook_input.get("cwd", "")
    msg_text = hook_input.get("message", "（内容なし）")

    message = (
        f"#### 💬 Claude Code からの通知\n"
        f"**セッション**: `{session_id}` | **ディレクトリ**: `{cwd}`\n\n"
        f"{msg_text}"
    )

    try:
        send_message(config, message)
    except Exception as e:
        log(f"Notification 送信エラー: {e}")

    sys.exit(0)


# ─── エントリポイント ─────────────────────────────────────────────────────

def main() -> None:
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw) if raw.strip() else {}
    except Exception as e:
        log(f"stdin 読み込みエラー: {e}")
        sys.exit(0)

    event = hook_input.get("hook_event_name", "")

    # Stop フックの再帰防止
    if event == "Stop" and hook_input.get("stop_hook_active") in (True, "true"):
        sys.exit(0)

    config = load_config()
    if config is None:
        sys.exit(0)

    try:
        if event == "PreToolUse":
            handle_pre_tool_use(hook_input, config)
        elif event == "Stop":
            handle_stop(hook_input, config)
        elif event == "Notification":
            handle_notification(hook_input, config)
        else:
            sys.exit(0)
    except Exception as e:
        log(f"予期しないエラー ({event}): {e}\n{traceback.format_exc()}")
        sys.exit(0)


if __name__ == "__main__":
    main()
