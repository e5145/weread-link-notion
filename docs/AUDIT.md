# 项目审查与精简说明

这个仓库是从旧版 WeRead to Notion 同步方案重新整理出来的精简版。

目标不是保留所有实验代码，而是保留一个新人能照着部署、能长期自动运行、出错时能排查的版本。

## 保留的能力

- 使用 `WEREAD_API_KEY` 调用微信读书 Skill / Agent API。
- 使用 `NOTION_TOKEN` 调用 Notion 官方 API。
- 使用 `NOTION_PAGE` 指定同步首页。
- 同步书库、每日阅读、划线、想法和推荐好书。
- 生成热力图、当月阅读时长分布和阅读画像图片。
- 通过 GitHub Actions 每天自动运行。
- 自动提交图表资源到 `assets/`。
- 在 Notion 里创建轻量首页和五个核心数据库。

## 删除或不再依赖的内容

- Cookie 登录方案。
- 浏览器 Cookie 提取脚本。
- 第三方热力图网页嵌入。
- 临时探测目录。
- 本地调试输出。
- 旧项目里和同步主流程无关的缓存、报告、实验代码。

## 为什么删除 Cookie 方案

旧方案依赖浏览器 Cookie，容易遇到这些问题：

- Cookie 过期。
- Cookie 复制不完整。
- GitHub Secrets 里换行或转义导致失败。
- 微信读书风控后同步不稳定。

新版使用 `WEREAD_API_KEY`，配置更短，也更适合放进 GitHub Actions 长期运行。

## 为什么自己生成图表

Notion 嵌入第三方热力图网页时，可能出现：

- 白屏。
- 加载慢。
- 移动端显示不稳定。
- 第三方服务不可用。

新版直接生成：

```text
assets/heatmap.png
assets/heatmap.svg
assets/heatmap.json
assets/monthly-reading.png
assets/monthly-reading.json
assets/reading-profile.png
assets/reading-profile.json
```

Notion 首页使用图片块展示热力图、当月阅读时长分布和阅读画像，数据库里仍保留每日阅读原始数据。

## 依赖控制

项目只保留少量必要依赖：

| 依赖 | 用途 |
|---|---|
| `requests` | 访问微信读书 API |
| `notion-client` | 访问 Notion API |
| `Pillow` | 生成图表和画像图片 |
| `python-dotenv` | 本地测试读取 `.env` |

## Notion 设计取舍

Notion 页面采用“轻首页 + 数据库”的结构：

- 首页只放标题、摘要、图表、最近内容和入口。
- 书库、笔记、每日阅读、推荐好书、同步快照分别放进独立数据库。
- 自定义视图建议在 Notion 里手动添加。

这样比把所有内容都堆在一个页面里更流畅，也更容易维护。

## 自动化设计

GitHub Actions 做四件事：

1. 安装 Python 依赖。
2. 检查微信读书和 Notion 连接。
3. 生成并提交图表资源。
4. 同步数据到 Notion。

默认每天北京时间 00:30 自动运行，也可以手动运行。

## 安全边界

密钥只应该放在 GitHub Secrets：

```text
WEREAD_API_KEY
NOTION_TOKEN
NOTION_PAGE
```

项目不会要求把密钥写入代码、README 或提交记录。

本地 `.env` 只用于自己电脑测试，并且已被 `.gitignore` 忽略。
