#!/usr/bin/env python3
from __future__ import annotations
import json, re, time
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
HEADERS = {"User-Agent":"Mozilla/5.0 CookieRun-Crumble-CouponBook/4.0"}
CODE_RE = re.compile(r"\bCOOKIERUN[A-Z0-9_-]{5,}\b")

OFFICIAL = [
    ("Official Coupon","https://coupon.devplay.com/coupon/cc/en"),
    ("Official Support","https://cs-cookieruncrumble.devsisters.com/hc/en-us"),
]
SOURCES = [
    ("EOG","https://eog.gg/games/cookierun-crumble/","eog",20),
    ("Crumble Hub","https://crumblehub.co/en/coupon","hub",15),
]

def clean(s): return re.sub(r"\s+"," ",(s or "").replace("†"," ")).strip()
def now_iso(): return datetime.now().astimezone().isoformat(timespec="seconds")
def parse_date(s):
    s = re.sub(r"(st|nd|rd|th)\b","",clean(s),flags=re.I)
    dt = date_parser.parse(s, fuzzy=True)
    if dt.tzinfo is None: dt = dt.replace(tzinfo=KST)
    return dt

def lines(url):
    r=requests.get(url,headers=HEADERS,timeout=30)
    r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser")
    return [clean(x) for x in soup.stripped_strings if clean(x)]

def parse_eog(ls):
    out=[]
    try: start=next(i for i,x in enumerate(ls) if x.lower()=="active codes")
    except StopIteration: start=0
    try: end=next(i for i,x in enumerate(ls[start+1:],start+1) if x.lower()=="how to redeem")
    except StopIteration: end=len(ls)
    sec=ls[start:end]
    for i,s in enumerate(sec):
        if not CODE_RE.fullmatch(s): continue
        code=s; expiry=None; announced=None; rewards=[]
        for j in range(i+1,min(i+10,len(sec))):
            t=sec[j]
            if CODE_RE.fullmatch(t): break

            m_full=re.search(r"Announced\s+(.+?)\s*[·•]\s*Expires\s+(.+)$",t,re.I)
            if m_full:
                try: announced=parse_date(m_full.group(1)).date().isoformat()
                except: pass
                try: expiry=parse_date(m_full.group(2)).isoformat()
                except: pass
                continue

            m=re.search(r"Expires\s+(.+)$",t,re.I)
            if m:
                try: expiry=parse_date(m.group(1)).isoformat()
                except: pass
                continue

            if expiry and re.search(r"\d",t) and len(t)<170 and t.lower()!="copy":
                rewards.append(t)
        out.append({"code":code,"announced":announced,"expiry":expiry,"rewards":rewards})
    return out

def parse_hub(ls):
    out=[]
    for i,s in enumerate(ls):
        code=s.replace("⧉","").strip()
        if not CODE_RE.fullmatch(code): continue
        expiry=None; rewards=[]
        for j in range(max(0,i-6),i):
            m=re.search(r"Expires\s+(.+)$",ls[j],re.I)
            if m:
                try: expiry=parse_date(m.group(1)).isoformat()
                except: pass
        kr={"크리스탈":"水晶","용기의 불꽃":"勇氣之火","행운반죽":"幸運麵團","룬결정":"符文水晶",
            "스텔라 포인트":"星辰點數","코인 1시간 자동 사냥 보상":"1 小時自動狩獵硬幣"}
        for j in range(i+1,min(i+24,len(ls))):
            t=ls[j]
            if CODE_RE.fullmatch(t.replace("⧉","").strip()) or "DEVSISTERS" in t.upper(): break
            if "reward types" in t.lower(): continue
            for a,b in kr.items(): t=t.replace(a,b)
            if re.search(r"\d",t) and any(k in t for k in ["水晶","勇氣之火","幸運麵團","符文水晶","星辰點數","自動狩獵硬幣"]):
                rewards.append(t)
        out.append({"code":code,"announced":None,"expiry":expiry,"rewards":rewards})
    return out

def load_old():
    try:return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except:return {"codes":[]}

def merge(obs,old):
    pri={x[0]:x[3] for x in SOURCES}
    by=defaultdict(list)
    for x in obs: by[x["code"]].append(x)
    prev={x["code"]:x for x in old.get("codes",[]) if x.get("code")}
    rows=[]
    for code in sorted(set(prev)|set(by)):
        xs=sorted(by.get(code,[]),key=lambda x:pri.get(x["source"],0),reverse=True)
        oldrow=prev.get(code,{})
        announced=next((x.get("announced") for x in xs if x.get("announced")),oldrow.get("announced"))
        expiry=next((x["expiry"] for x in xs if x.get("expiry")),oldrow.get("expires_at"))
        rewards=max((x for x in xs if x.get("rewards")),key=lambda x:len(x["rewards"]),default=None)
        rewards=rewards["rewards"] if rewards else oldrow.get("rewards",[])
        srcs=[]; expmap={}
        for x in xs:
            if x["source"] not in [s["name"] for s in srcs]:
                srcs.append({"name":x["source"]})
                if x.get("expiry"): expmap[x["source"]]=x["expiry"]
        if not srcs: srcs=oldrow.get("sources",[])
        conflict=len(set(expmap.values()))>1
        label=oldrow.get("expires_label","")
        if expiry:
            try: label=date_parser.parse(expiry).astimezone(KST).strftime("%Y/%m/%d %H:%M KST")
            except: pass
        row={"code":code,"announced":announced,"expires_at":expiry,"expires_label":label,"rewards":rewards,
             "sources":srcs,"source_count":len(srcs),"expiry_conflict":conflict}
        if conflict:
            row["expiry_candidates"]=[f'{k}：{date_parser.parse(v).astimezone(KST).strftime("%Y/%m/%d %H:%M KST")}' for k,v in expmap.items()]
        rows.append(row)
    return rows

def main():
    old=load_old(); obs=[]; health=[]
    for name,url in OFFICIAL:
        try:
            r=requests.get(url,headers=HEADERS,timeout=20)
            health.append({"name":name,"status":"ok" if r.ok else f"http-{r.status_code}","kind":"official"})
        except: health.append({"name":name,"status":"error","kind":"official"})
    for name,url,parser,_ in SOURCES:
        try:
            ls=lines(url)
            rows=parse_eog(ls) if parser=="eog" else parse_hub(ls)
            for x in rows: x["source"]=name; obs.append(x)
            health.append({"name":name,"status":"ok","found":len(rows),"kind":"crawler"})
        except Exception as e:
            health.append({"name":name,"status":"error","error":str(e)[:120],"kind":"crawler"})
        time.sleep(.6)
    if not obs and not old.get("codes"): raise RuntimeError("所有資料站皆失敗，且沒有舊資料。")
    payload={"generated_at":now_iso(),"source_health":health,"codes":merge(obs,old)}
    DATA_FILE.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print("updated",len(payload["codes"]),"codes")

if __name__=="__main__": main()
