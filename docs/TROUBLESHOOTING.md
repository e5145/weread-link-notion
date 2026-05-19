# 排错指南

## Actions 里没有 workflow

检查 `.github/workflows/sync.yml` 是否上传到仓库。

路径必须是：

```text
.github/workflows/sync.yml
```

## Missing required environment variables

说明 GitHub Secrets 没填完整。

检查：

- `WEREAD_API_KEY`
- `NOTION_TOKEN`
- `NOTION_PAGE`

## Notion 权限错误

常见原因：

1. `NOTION_TOKEN` 填错。
2. Notion 页面没有授权给 integration。
3. `NOTION_PAGE` 不是页面 URL，而是数据库 URL。

解决：

1. 打开 Notion 页面。
2. 点右上角 Share 或 `...`。
3. 邀请你的 integration。
4. 重新运行 Actions。

## WeRead 网络错误

如果日志里出现：

```text
Network is unreachable
```

新版默认会强制微信读书网关走 IPv4，通常可以绕开 GitHub runner 的 IPv6 路由问题。

如果仍然失败，手动重新运行一次。GitHub runner 区域偶尔会影响到微信读书域名连接。

## 热力图没有显示

先看仓库里有没有文件：

```text
assets/heatmap.png
assets/heatmap.svg
assets/heatmap.json
```

如果没有，说明 `Generate heatmap` 或 `Publish heatmap assets` 步骤失败。

如果有，但 Notion 没显示：

1. 确认 `Sync Notion` 步骤成功。
2. 刷新 Notion 页面。
3. 检查 `同步快照` 里最新记录的 `Heatmap` 字段。

## 笔记同步很慢

笔记同步需要逐本书拉取划线和想法。第一次运行慢是正常的。

可以先设置 GitHub Variable：

```text
MAX_NOTEBOOKS=5
```

确认流程跑通后再改回：

```text
MAX_NOTEBOOKS=0
```

## 不想同步笔记

设置 GitHub Variable：

```text
SYNC_NOTES=false
```

这样只同步书库、每日阅读和热力图。
