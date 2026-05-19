# WeRead Link Notion

把微信读书的书架、笔记、每日阅读时长和阅读热力图同步到 Notion。

这个项目使用 `WEREAD_API_KEY` 调用微信读书 Agent API Gateway，不再依赖浏览器 Cookie；使用 GitHub Actions 每天自动运行；使用 Notion 官方 API 自动创建并维护一个轻量的阅读面板。

## 功能

- 同步书库：电子书、有声书、文章收藏入口、阅读状态、私密状态、最近阅读时间。
- 同步笔记：划线和个人想法，保留书名、章节、创建时间、位置和微信读书网页链接。
- 同步每日阅读：按天保存阅读秒数、分钟数、年、月、周。
- 生成热力图：生成 `assets/heatmap.png` 和 `assets/heatmap.svg`，并直接嵌入 Notion，避免第三方热力图服务白屏。
- 自动建表：第一次运行会在你的 Notion 页面下创建 `书库`、`笔记`、`每日阅读`、`同步快照` 四个数据库。
- 自动运行：GitHub Actions 默认每天北京时间 00:30 同步，也可以手动运行。

## 项目结构

```text
weread-link-notion/
  .github/workflows/sync.yml      # 每日自动同步
  assets/                         # 热力图输出
  docs/                           # 新手说明和排错
  weread_link_notion/             # 同步器源码
  .env.example                    # 本地环境变量模板
  pyproject.toml                  # Python 包配置
  requirements.txt                # 依赖列表
```

## 快速开始

完整步骤见 [docs/SETUP.md](docs/SETUP.md)。

最短流程：

1. 新建 GitHub 仓库：`weread-link-notion`。
2. 上传本项目全部文件。
3. 在 Notion 创建一个空白页面，并把页面分享给你的 Notion integration。
4. 在 GitHub 仓库添加 Secrets：
   - `WEREAD_API_KEY`
   - `NOTION_TOKEN`
   - `NOTION_PAGE`
5. 打开 GitHub Actions，运行 `Sync WeRead Link Notion`。

## 必填 Secrets

| 名称 | 说明 |
|---|---|
| `WEREAD_API_KEY` | 微信读书 Agent API Key，格式通常是 `wrk-...` |
| `NOTION_TOKEN` | Notion integration secret，格式通常是 `secret_...` |
| `NOTION_PAGE` | 作为同步首页的 Notion 页面 URL 或页面 ID |

## 可选 Variables

| 名称 | 默认值 | 说明 |
|---|---:|---|
| `SYNC_NOTES` | `true` | 是否同步划线和想法 |
| `MAX_NOTEBOOKS` | `0` | 笔记同步书籍上限，`0` 表示不限制 |

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env
python -m weread_link_notion check
python -m weread_link_notion heatmap
python -m weread_link_notion sync
```

## 设计原则

- 少依赖：只保留 `requests`、`notion-client`、`Pillow`、`python-dotenv`。
- 少状态：不保存 Cookie，不保存本地数据库，重复运行会按唯一 ID 更新 Notion。
- Notion 轻量：核心信息放数据库，首页只保留热力图和入口，避免页面越来越卡。
- 可恢复：GitHub Actions 日志能定位绝大多数问题；热力图资产直接在仓库里可见。

## 文档

- [安装说明](docs/SETUP.md)
- [Notion 页面布局](docs/NOTION_LAYOUT.md)
- [旧项目审查与精简说明](docs/AUDIT.md)
- [排错指南](docs/TROUBLESHOOTING.md)

## License

MIT
