# CookieRun: Crumble 禮包碼手冊 v8

定稿 UI：
- 移除重複的左側目錄。
- 主內容加寬，右側保留銀河餅乾角色卡。
- 新禮包碼公告後 3 天內自動顯示 NEW。
- 有公告日期時顯示「新增：YYYY/MM/DD」。
- 每頁 6 組，分頁列永遠顯示。
- EOG + Crumble Hub 每小時自動監控。
- 官方兌換頁保留作兌換入口。


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
