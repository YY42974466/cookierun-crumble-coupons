#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

REDEEM_URL = "https://coupon.devplay.com/coupon/cc/en"

def load_json(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"codes": []}
    return json.loads(p.read_text(encoding="utf-8"))

def by_code(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["code"]: row
        for row in data.get("codes", [])
        if isinstance(row, dict) and row.get("code")
    }

def normalize_rewards(row: dict[str, Any]) -> list[str]:
    return [str(x).strip() for x in row.get("rewards", []) if str(x).strip()]

def format_expiry(row: dict[str, Any]) -> str:
    return row.get("expires_label") or row.get("expires_at") or "未提供"

def diff_codes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    old = by_code(before)
    new = by_code(after)
    changes: list[dict[str, Any]] = []

    for code, row in new.items():
        if code not in old:
            changes.append({
                "type": "new",
                "code": code,
                "row": row,
                "title": "🎁 發現新禮包碼！",
            })
            continue

        prev = old[code]

        old_expiry = prev.get("expires_at") or prev.get("expires_label")
        new_expiry = row.get("expires_at") or row.get("expires_label")
        if old_expiry != new_expiry:
            changes.append({
                "type": "expiry",
                "code": code,
                "row": row,
                "old": format_expiry(prev),
                "new": format_expiry(row),
                "title": "⏰ 禮包碼期限更新",
            })

        old_rewards = normalize_rewards(prev)
        new_rewards = normalize_rewards(row)
        if old_rewards != new_rewards and new_rewards:
            changes.append({
                "type": "rewards",
                "code": code,
                "row": row,
                "old_rewards": old_rewards,
                "new_rewards": new_rewards,
                "title": "✨ 禮包碼獎勵更新",
            })

    return changes

def source_text(row: dict[str, Any]) -> str:
    names = []
    for src in row.get("sources", []):
        if isinstance(src, dict) and src.get("name"):
            names.append(str(src["name"]))
    return "、".join(names) if names else "資料站"

def reward_text(row: dict[str, Any]) -> str:
    rewards = normalize_rewards(row)
    return "\n".join(f"• {x}" for x in rewards) if rewards else "未提供"

def make_embed(change: dict[str, Any]) -> dict[str, Any]:
    row = change["row"]
    typ = change["type"]

    fields = [
        {
            "name": "禮包碼",
            "value": f"`{change['code']}`",
            "inline": False,
        },
        {
            "name": "獎勵",
            "value": reward_text(row)[:1024],
            "inline": False,
        },
        {
            "name": "結束日期",
            "value": format_expiry(row),
            "inline": True,
        },
        {
            "name": "來源",
            "value": source_text(row),
            "inline": True,
        },
    ]

    if typ == "expiry":
        fields.insert(1, {
            "name": "期限變更",
            "value": f"{change['old']} → **{change['new']}**",
            "inline": False,
        })
    elif typ == "rewards":
        old_txt = "\n".join(f"• {x}" for x in change.get("old_rewards", [])) or "未提供"
        fields.insert(1, {
            "name": "原獎勵",
            "value": old_txt[:1024],
            "inline": False,
        })

    # Discord embed color integer.
    color = {
        "new": 0xF2B544,
        "expiry": 0xE7793F,
        "rewards": 0x7EAF64,
    }.get(typ, 0xF2B544)

    return {
        "title": change["title"],
        "url": REDEEM_URL,
        "description": "點標題可前往官方兌換頁。",
        "color": color,
        "fields": fields,
        "footer": {
            "text": "CookieRun: Crumble 禮包碼通知"
        },
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
    }

def send_batches(webhook_url: str, changes: list[dict[str, Any]]) -> None:
    embeds = [make_embed(x) for x in changes]

    # Discord allows multiple embeds per webhook message; batch conservatively.
    for i in range(0, len(embeds), 8):
        payload = {
            "username": "CookieRun Crumble 禮包碼",
            "content": "🍪 **禮包碼資料有更新！**",
            "embeds": embeds[i:i+8],
            "allowed_mentions": {"parse": []},
        }
        r = requests.post(webhook_url, json=payload, timeout=20)
        if r.status_code not in (200, 204):
            raise RuntimeError(f"Discord Webhook 回傳 HTTP {r.status_code}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    args = parser.parse_args()

    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        print("未設定 DISCORD_WEBHOOK_URL，略過 Discord 通知。")
        return

    before = load_json(args.before)
    after = load_json(args.after)
    changes = diff_codes(before, after)

    if not changes:
        print("沒有需要通知的禮包碼變化。")
        return

    try:
        send_batches(webhook, changes)
    except Exception as e:
        # Do not print the webhook URL.
        print(f"Discord 通知失敗：{e}")
        raise

    print(f"Discord 通知完成，共 {len(changes)} 個變更。")

if __name__ == "__main__":
    main()
