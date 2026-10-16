# 更新日志

## v3.8（2026-10-16）

- 新增：`credits_report.py` 积分余额与到期时间报告（国内 / 国际版）：
  - 余额组成 + 逐笔到期时间（月度套餐月底清零、活动赠送 30 天逐笔到期）；
  - 支持 Bark / WxPusher 推送与到期预警窗口。
- 新增：`daily_forward.py` 可选工具：读取 Actions 运行日志、重建签到报告并按需转发（社区贡献 #25，感谢 @wuge0）。
- 新增：WxPusher（微信）内置推送渠道，配置 `WXPUSHER_APP_TOKEN` + `WXPUSHER_UID` 即启用（社区贡献 #25）。
- 文档：README 环境变量表、目录结构与可选工具说明同步更新。

## v3.7（2026-10-11）

- 新增：国际版设备授权登录工具 `workbuddy_intl_login.py`（适配 Google / GitHub / X 注册的纯 OAuth 账号，免手机号）：
  申请授权会话 → 浏览器授权 → 轮询换令牌 → 取账号信息，输出可直接填入 `WORKBUDDY_INTL_TOKENS`；
  支持 `--refresh '备注|AT|uid|RT'` 直接续期已有令牌。
- 安全：`.gitignore` 补上 `wb_intl_login_result.json`、`wb_intl_tokens.json`（含令牌的本地结果文件不入库）。

## v3.6（2026-10-10）

- 新增：国际版（www.workbuddy.ai）每日活跃脚本 `workbuddy_intl_daily.py`
  - 活动探测 → 条件领取 → 免费模型活跃保活，三步一条链；
  - 活动未开放按正常状态处理，保活成功与领取成功分开报告；
  - 支持多账号与可选 refresh token 自动续期（写回 `wb_intl_tokens.json`）；
  - 可用 `--no-keepalive` 只探测与领取，`--only N` 单账号运行。

## v3.5（2026-10-08）

- 青龙默认通知兼容新版应用授权（OpenAPI /open/auth/token + PUT /open/system/notify）。
- 环境变量表与通知说明补齐青龙新版 / 旧版两种方式。

## v3.4（2026-10-07）

- 归档开学季活动与校园日实现快照（活动已结束）。
