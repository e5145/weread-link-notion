# 安装说明

这份说明面向第一次使用的人。照着走完后，你会得到一个每天自动同步的 GitHub Actions，以及一个自动维护的 Notion 阅读面板。

## 1. 创建 GitHub 仓库

1. 打开 GitHub。
2. 新建仓库。
3. 仓库名填写：`weread-link-notion`。
4. 仓库可以选择 Public 或 Private。
5. 不需要勾选模板文件；如果已经勾选 README 也没关系，上传时覆盖即可。

## 2. 上传项目文件

把本项目目录里的全部文件上传到仓库根目录，包含隐藏目录：

```text
.github/
assets/
docs/
weread_link_notion/
.env.example
.gitignore
README.md
pyproject.toml
requirements.txt
```

注意：`.github/workflows/sync.yml` 必须上传成功，否则 Actions 不会出现。

## 3. 准备 Notion 页面

1. 在 Notion 新建一个空白页面，例如命名为 `阅读面板`。
2. 复制这个页面的 URL，稍后作为 `NOTION_PAGE`。
3. 去 Notion 的 My integrations 页面创建 integration。
4. 复制 integration secret，稍后作为 `NOTION_TOKEN`。
5. 回到刚才的 Notion 页面，点右上角 `...` 或 `Share`，把页面授权给这个 integration。

如果没有把页面授权给 integration，GitHub Actions 会报 Notion 权限错误。

## 4. 准备 WeRead API Key

你需要一个微信读书 Agent API Key，通常格式类似：

```text
wrk_xxxxxxxxxxxxxxxxx
```

把它保存为 GitHub Secret：`WEREAD_API_KEY`。

## 5. 添加 GitHub Secrets

进入仓库：

`Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`

添加三个 Secret：

| Secret | 示例 |
|---|---|
| `WEREAD_API_KEY` | `wrk_xxx` |
| `NOTION_TOKEN` | `secret_xxx` |
| `NOTION_PAGE` | `https://www.notion.so/...` |

## 6. 可选变量

进入：

`Settings` -> `Secrets and variables` -> `Actions` -> `Variables`

可添加：

| Variable | 推荐值 | 说明 |
|---|---|---|
| `SYNC_NOTES` | `true` | 同步划线和想法 |
| `MAX_NOTEBOOKS` | `0` | `0` 表示不限；测试时可设成 `5` |

## 7. 第一次运行

1. 打开仓库的 `Actions`。
2. 选择 `Sync WeRead Link Notion`。
3. 点击 `Run workflow`。
4. 等待运行完成。

第一次运行会做这些事：

1. 检查 WeRead API Key。
2. 生成热力图文件到 `assets/`。
3. 把热力图提交回 GitHub。
4. 在 Notion 页面创建布局和数据库。
5. 同步书库、每日阅读和笔记。

## 8. 验证结果

运行成功后检查：

1. GitHub 仓库里出现：
   - `assets/heatmap.png`
   - `assets/heatmap.svg`
   - `assets/heatmap.json`
2. Notion 页面里出现：
   - 阅读热力图
   - `书库`
   - `笔记`
   - `每日阅读`
   - `同步快照`

## 9. 日常使用

默认每天北京时间 00:30 自动同步。

你也可以随时手动运行：

`Actions` -> `Sync WeRead Link Notion` -> `Run workflow`

## 10. 本地测试

本地测试适合改代码时使用。

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env
```

编辑 `.env` 后运行：

```bash
python -m weread_link_notion check
python -m weread_link_notion heatmap
python -m weread_link_notion sync
```
