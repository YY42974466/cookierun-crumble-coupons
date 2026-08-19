#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / "data" / "codes.json"
KST = ZoneInfo("Asia/Seoul")

HEADERS = {"User-Agent": "Mozilla/5.0 CookieRun-Crumble-CouponBook/13.0"}
CODE_RE = re.compile(r"\bCOOKIERUN[A-Z0-9_-]{5,}\b")

OFFICIAL = [
    ("Official Coupon", "https://coupon.devplay.com/coupon/cc/en"),
    ("Official Support", "https://cs-cookieruncrumble.devsisters.com/hc/en-us"),
]

SOURCES = [
    ("EOG", "https://eog.gg/games/cookierun-crumble/", "eog", 20),
    ("Crumble Hub", "https://crumblehub.co/zh-hant/coupon", "hub", 15),
]

KNOWN_NAMES = {
    "crystal": "水晶",
    "crystals": "水晶",
    "flame of bravery": "勇氣之火",
    "flames of bravery": "勇氣之火",
    "stellar point": "星辰點數",
    "stellar points": "星辰點數",
    "lucky dough": "幸運麵團",
    "rune crystal": "符文水晶",
    "rune crystals": "符文水晶",
    "one-hour auto hunt coin reward": "1 小時自動狩獵硬幣",
    "one-hour auto hunt coin rewards": "1 小時自動狩獵硬幣",
    "1-hour auto-hunt coin": "1 小時自動狩獵硬幣",
    "1-hour auto-hunt coins": "1 小時自動狩獵硬幣",
    "크리스탈": "水晶",
    "용기의 불꽃": "勇氣之火",
    "행운반죽": "幸運麵團",
    "룬결정": "符文水晶",
    "스텔라 포인트": "星辰點數",
    "코인 1시간 자동 사냥 보상": "1 小時自動狩獵硬幣",
}

COUNTABLE_ZH = {"1 小時自動狩獵硬幣"}

def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")

def parse_date(s: str):
    s = re.sub(r"(st|nd|rd|th)\b", "", clean(s), flags=re.I)
    dt = date_parser.parse(s, fuzzy=True)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt

def source_lines(url: str) -> list[str]:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    return [clean(x) for x in soup.stripped_strings if clean(x)]

def translate_known_name(name: str) -> str:
    raw = clean(name).strip("†•·:：- ")
    return KNOWN_NAMES.get(raw.casefold(), raw)

def format_reward(amount: str, name: str) -> str:
    shown_name = translate_known_name(name)
    amount = clean(amount)
    if shown_name in COUNTABLE_ZH:
        return f"{amount} 個 {shown_name}"
    return f"{amount} {shown_name}"

def split_eog_reward_blob(text: str) -> list[str]:
    t = clean(text)
    rewards = []
    pattern = re.compile(r"(\d[\d,]*)\s+(.+?)(?=(?:\s+\d[\d,]*\s+)|†|$)")
    for m in pattern.finditer(t):
        amount = m.group(1)
        name = clean(m.group(2)).strip("† ")
        if name:
            rewards.append(format_reward(amount, name))
    return rewards

def split_hub_reward_line(text: str):
    t = clean(text).replace("⧉", "")
    # zh-Hant page may show quantities as 10,000個.
    m = re.match(r"^(.+?)(\d[\d,]*)(?:\s*個)?$", t)
    if not m:
        return None
    name = clean(m.group(1))
    amount = m.group(2)
    return format_reward(amount, name) if name else None

def parse_hub_expiry(text: str):
    """Supports both Crumble Hub English and Traditional Chinese expiry labels."""
    t = clean(text)

    zh = re.search(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})\s*到期",
        t,
    )
    if zh:
        y, mo, d, h, mi = map(int, zh.groups())
        return datetime(y, mo, d, h, mi, tzinfo=KST)

    en = re.search(r"Expires\s+(.+)$", t, re.I)
    if en:
        return parse_date(en.group(1))

    return None

def reward_language_score(rewards: list[str]) -> int:
    """
    Prefer Chinese if a source already provides it.
    Otherwise prefer English over Korean for unknown item names.
    """
    text = " ".join(rewards or [])
    if re.search(r"[\uac00-\ud7af]", text):
        return 0
    if re.search(r"[A-Za-z]", text):
        return 1
    return 2

def parse_eog(ls: list[str]):
    out = []
    try:
        start = next(i for i, x in enumerate(ls) if x.lower() == "active codes")
    except StopIteration:
        start = 0
    try:
        end = next(i for i, x in enumerate(ls[start + 1:], start + 1) if x.lower() == "how to redeem")
    except StopIteration:
        end = len(ls)

    sec = ls[start:end]
    for i, s in enumerate(sec):
        code_match = CODE_RE.search(s)
        if not code_match:
            continue

        code = code_match.group(0)
        expiry = None
        announced = None
        rewards = []

        for j in range(i + 1, min(i + 14, len(sec))):
            t = sec[j]
            if CODE_RE.search(t):
                break

            full = re.search(r"Announced\s+(.+?)\s*[·•]\s*Expires\s+(.+)$", t, re.I)
            if full:
                try:
                    announced = parse_date(full.group(1)).date().isoformat()
                except Exception:
                    pass
                try:
                    expiry = parse_date(full.group(2)).isoformat()
                except Exception:
                    pass
                continue

            exp = re.search(r"Expires\s+(.+)$", t, re.I)
            if exp:
                try:
                    expiry = parse_date(exp.group(1)).isoformat()
                except Exception:
                    pass
                continue

            if expiry and re.match(r"^\d[\d,]*\s+", t):
                parsed = split_eog_reward_blob(t)
                if parsed:
                    rewards.extend(parsed)
                continue

            if rewards and t.lower() != "copy":
                break

        rewards = list(dict.fromkeys(rewards))
        out.append({"code": code, "announced": announced, "expiry": expiry, "rewards": rewards})
    return out

def parse_hub(ls: list[str]):
    out = []
    for i, s in enumerate(ls):
        code_match = CODE_RE.search(s.replace("⧉", ""))
        if not code_match:
            continue

        code = code_match.group(0)
        expiry = None
        rewards = []
        expected_reward_count = None

        for j in range(max(0, i - 7), i):
            try:
                dt = parse_hub_expiry(ls[j])
                if dt:
                    expiry = dt.isoformat()
            except Exception:
                pass

        for j in range(i + 1, min(i + 35, len(ls))):
            t = ls[j]
            if CODE_RE.search(t.replace("⧉", "")):
                break
            if "DEVSISTERS" in t.upper():
                break

            m_count = re.search(r"(\d+)\s+reward types", t, re.I)
            if not m_count:
                m_count = re.search(r"共\s*(\d+)\s*種", t)
            if m_count:
                expected_reward_count = int(m_count.group(1))
                continue

            parsed = split_hub_reward_line(t)
            if parsed:
                rewards.append(parsed)
                if expected_reward_count and len(rewards) >= expected_reward_count:
                    break

        rewards = list(dict.fromkeys(rewards))
        out.append({"code": code, "announced": None, "expiry": expiry, "rewards": rewards})
    return out

def load_old():
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"codes": []}

def merge(obs, old):
    pri = {x[0]: x[3] for x in SOURCES}
    by = defaultdict(list)
    for x in obs:
        by[x["code"]].append(x)

    prev = {x["code"]: x for x in old.get("codes", []) if x.get("code")}
    rows = []

    for code in sorted(set(prev) | set(by)):
        xs = sorted(by.get(code, []), key=lambda x: pri.get(x["source"], 0), reverse=True)
        oldrow = prev.get(code, {})

        announced = next((x.get("announced") for x in xs if x.get("announced")), oldrow.get("announced"))
        expiry = next((x.get("expiry") for x in xs if x.get("expiry")), oldrow.get("expires_at"))

        reward_candidates = [x for x in xs if x.get("rewards")]
        best_rewards = oldrow.get("rewards", [])
        if reward_candidates:
            best = max(
                reward_candidates,
                key=lambda x: (
                    len(x["rewards"]),
                    reward_language_score(x["rewards"]),
                    pri.get(x["source"], 0),
                ),
            )
            best_rewards = best["rewards"]

        srcs = []
        expmap = {}
        for x in xs:
            if x["source"] not in [s["name"] for s in srcs]:
                srcs.append({"name": x["source"]})
                if x.get("expiry"):
                    expmap[x["source"]] = x["expiry"]

        if not srcs:
            srcs = oldrow.get("sources", [])

        conflict = len(set(expmap.values())) > 1
        label = oldrow.get("expires_label", "")

        if expiry:
            try:
                label = date_parser.parse(expiry).astimezone(KST).strftime("%Y/%m/%d %H:%M KST")
            except Exception:
                pass

        row = {
            "code": code,
            "announced": announced,
            "expires_at": expiry,
            "expires_label": label,
            "rewards": best_rewards,
            "sources": srcs,
            "source_count": len(srcs),
            "expiry_conflict": conflict,
        }

        if conflict:
            row["expiry_candidates"] = [
                f'{name}：{date_parser.parse(value).astimezone(KST).strftime("%Y/%m/%d %H:%M KST")}'
                for name, value in expmap.items()
            ]

        rows.append(row)

    return rows

def main():
    old = load_old()
    obs = []
    health = []

    for name, url in OFFICIAL:
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            health.append({"name": name, "status": "ok" if r.ok else f"http-{r.status_code}", "kind": "official"})
        except Exception:
            health.append({"name": name, "status": "error", "kind": "official"})

    for name, url, parser, _ in SOURCES:
        try:
            ls = source_lines(url)
            rows = parse_eog(ls) if parser == "eog" else parse_hub(ls)
            for x in rows:
                x["source"] = name
                obs.append(x)
            health.append({"name": name, "status": "ok", "found": len(rows), "kind": "crawler"})
        except Exception as e:
            health.append({"name": name, "status": "error", "error": str(e)[:160], "kind": "crawler"})
        time.sleep(0.6)

    if not obs and not old.get("codes"):
        raise RuntimeError("所有資料站皆失敗，且沒有舊資料。")

    payload = {"generated_at": now_iso(), "source_health": health, "codes": merge(obs, old)}
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("updated", len(payload["codes"]), "codes")

if __name__ == "__main__":
    main()
