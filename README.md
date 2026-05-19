# WeRead Link Notion

把微信读书的书架、划线、想法、每日阅读时长和阅读热力图自动同步到 Notion。

这个项目适合不想每天手动整理读书记录的人：配置一次以后，GitHub Actions 会每天自动运行，把最新数据写进你的 Notion 阅读面板。

## 你最终会得到什么

- 一个 Notion 阅读首页，包含阅读热力图和数据入口。
- 一个 `书库` 数据库，保存微信读书书架里的电子书、有声书和文章收藏入口。
- 一个 `笔记` 数据库，保存划线和个人想法。
- 一个 `每日阅读` 数据库，保存每天的阅读秒数、分钟数、年月周字段。
- 一个 `同步快照` 数据库，记录每次同步是否成功、同步了多少书和笔记。
- 一个每天自动运行的 GitHub Actions workflow。

## 这个项目和旧版有什么不同

- 不再使用微信读书 Cookie。
- 使用 `WEREAD_API_KEY` 访问微信读书官方 Skill / Agent API。
- 使用 Notion 官方 API 写入数据。
- 热力图由项目自己生成 `assets/heatmap.png` 和 `assets/heatmap.svg`，再嵌入 Notion。
- 只保留同步需要的核心代码和文档，减少第三方依赖。

## 新手先看这里

你只需要准备三个值：

| 名称 | 从哪里拿 | 放在哪里 |
|---|---|---|
| `WEREAD_API_KEY` | 微信读书 Skill 页面 | GitHub Secrets |
| `NOTION_TOKEN` | Notion integration 页面 | GitHub Secrets |
| `NOTION_PAGE` | 你的 Notion 阅读首页链接 | GitHub Secrets |

完整获取方法见：[docs/GET_SECRETS.md](docs/GET_SECRETS.md)

完整安装流程见：[docs/SETUP.md](docs/SETUP.md)

## 最短部署流程

1. 创建一个 GitHub 仓库，例如 `weread-link-notion`。
2. 上传本项目全部文件，必须包含 `.github/workflows/sync.yml`。
3. 在 Notion 创建一个空白页面，例如 `阅读面板`。
4. 创建 Notion integration，并把刚才的 Notion 页面授权给它。
5. 在 GitHub 仓库里添加三个 Secrets：
   - `WEREAD_API_KEY`
   - `NOTION_TOKEN`
   - `NOTION_PAGE`
6. 打开 GitHub 仓库的 `Actions`。
7. 运行 `Sync WeRead Link Notion`。
8. 回到 Notion 查看同步结果。

如果你不知道三个 Secrets 怎么拿，先不要急着运行 Actions，按这个文档一步步来：

[docs/GET_SECRETS.md](docs/GET_SECRETS.md)

## 一键打开辅助页面

如果你已经把项目文件放进仓库，可以在仓库终端运行：

```bash
python scripts/setup_secrets.py --open --repo e5145/weread-link-notion
```

这个脚本会帮你打开常用页面、检查三个值的格式，并告诉你下一步应该把它们填到哪里。

注意：脚本不会、也不应该把密钥提交到代码仓库。真正用于 GitHub Actions 的值必须放在 GitHub Secrets 里。

## GitHub Secrets 必填项

进入仓库：

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

创建这三个 secret：

| Secret 名称 | 示例格式 |
|---|---|
| `WEREAD_API_KEY` | `wrk-...` 或 `wrk_...` |
| `NOTION_TOKEN` | `secret_...` 或 `ntn_...` |
| `NOTION_PAGE` | `https://www.notion.so/...` |

## 可选 Variables

进入仓库：

```text
Settings -> Secrets and variables -> Actions -> Variables
```

| Variable | 默认值 | 说明 |
|---|---:|---|
| `SYNC_NOTES` | `true` | 是否同步划线和想法 |
| `MAX_NOTEBOOKS` | `0` | 笔记同步的书籍上限，`0` 表示不限 |

第一次测试时，如果你的笔记很多，可以先设置：

```text
MAX_NOTEBOOKS=5
```

确认流程跑通后再改回：

```text
MAX_NOTEBOOKS=0
```

## 项目结构

```text
weread-link-notion/
  .github/workflows/sync.yml      # GitHub Actions 自动同步任务
  assets/                         # 热力图输出目录
  docs/                           # 新手说明和排错文档
  scripts/setup_secrets.py         # 三个密钥的辅助向导
  weread_link_notion/              # 同步器源码
  .env.example                     # 本地测试用环境变量模板
  pyproject.toml                   # Python 包配置
  requirements.txt                 # 依赖列表
```

## 本地测试

本地测试不是必须步骤。普通用户只需要配置 GitHub Actions。

如果你想在自己电脑上测试：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env
python -m weread_link_notion check
python -m weread_link_notion heatmap
python -m weread_link_notion sync
```

Windows PowerShell 可以把 `cp .env.example .env` 换成：

```powershell
copy .env.example .env
```

## 文档

- [从零安装说明](docs/SETUP.md)
- [三个密钥怎么获取](docs/GET_SECRETS.md)
- [Notion 页面布局说明](docs/NOTION_LAYOUT.md)
- [旧项目审查与精简说明](docs/AUDIT.md)
- [常见问题排错](docs/TROUBLESHOOTING.md)

## 安全提醒

不要把 `WEREAD_API_KEY`、`NOTION_TOKEN`、`NOTION_PAGE` 写进 README、issue、截图、commit 或公开聊天记录。

正确位置只有两个：

- GitHub Secrets：给自动同步用。
- 本地 `.env`：只给你自己电脑测试用，而且 `.env` 不要提交。

## License

MIT
