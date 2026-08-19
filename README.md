# CookieRun: Crumble 禮包碼手冊 v8

## Discord 通知 v10
使用 `notify_discord.py` 比較更新前後的 `data/codes.json`。

會通知：
- 新禮包碼
- 結束日期變更
- 獎勵變更

Webhook URL 必須存於 GitHub Actions Repository Secret：
`DISCORD_WEBHOOK_URL`

請勿把 Webhook URL 寫進公開原始碼。


## v11 部署方式
GitHub Pages 請設定為 **GitHub Actions**，不要使用 Deploy from a branch。

同一個 workflow 會：
1. 更新資料
2. 發 Discord 通知
3. commit codes.json
4. 使用官方 Pages Actions 直接部署網站
