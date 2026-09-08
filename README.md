---
title: 权限统计与考核系统
emoji: 🔐
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# 权限统计与考核系统

基于 Python（`http.server`）+ SQLite 的评审权限统计与考核后台系统，支持：

- 评审员账号与等级（待转正 / 初审 / 中审 / 高审）管理
- 评审权限一览（矩阵视图，剔除测试账号）
- 账号用途标记（测试 / 实际，仅超级管理员）
- 密码重置（7 天/账号限频）、彻底删除账号（全局闭环）
- 分类字典维护、官方任务名单等

## 部署

本仓库含 `Dockerfile`，可直接部署到 Hugging Face Spaces（Docker SDK）、Render（dockerDeploy）或任意 Docker 主机。

- 服务监听 `$PORT`（默认 7860），绑定 `$HOST`（默认 0.0.0.0）。
- 健康检查路径：`/`。

## 本地运行

```bash
pip install -r requirements.txt
PORT=8000 python app.py
```
