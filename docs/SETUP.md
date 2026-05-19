# 从零安装说明

这份说明写给第一次使用这个项目的人。照着做完以后，你会得到一个每天自动同步微信读书到 Notion 的 GitHub Actions。

整个流程分为四件事：

1. 把项目文件放到你的 GitHub 仓库。
2. 准备微信读书和 Notion 的三个密钥。
3. 把三个密钥放进 GitHub Secrets。
4. 手动运行一次 Actions，确认 Notion 里出现数据。

## 0. 你需要准备什么

开始前确认你有这些账号：

| 需要的东西 | 用来做什么 |
|---|---|
| GitHub 账号 | 放项目文件，运行每天同步任务 |
| Notion 账号 | 接收同步后的读书面板 |
| 微信读书账号 | 提供书架、笔记和阅读时长数据 |
| `WEREAD_API_KEY` | 让程序访问你的微信读书数据 |

如果你还不知道 `WEREAD_API_KEY`、`NOTION_TOKEN`、`NOTION_PAGE` 怎么拿，先看：

[GET_SECRETS.md](GET_SECRETS.md)

## 1. 创建 GitHub 仓库

1. 打开 GitHub。
2. 点击右上角 `+`。
3. 选择 `New repository`。
4. Repository name 填：

```text
weread-link-notion
```

5. 公开或私有都可以。建议私有，因为你会在这个仓库里运行个人同步任务。
6. 创建仓库。

如果你已经创建好了仓库，可以跳过这一节。

## 2. 上传项目文件

仓库根目录必须包含这些文件和目录：

```text
.github/
assets/
docs/
scripts/
weread_link_notion/
.env.example
.gitignore
LICENSE
README.md
pyproject.toml
requirements.txt
```

最重要的是这个文件：

```text
.github/workflows/sync.yml
```

如果这个文件没有上传成功，GitHub 的 `Actions` 页面不会出现同步任务。

## 3. 准备 Notion 页面

1. 打开 Notion。
2. 新建一个空白页面。
3. 页面名可以叫：

```text
阅读面板
```

4. 复制这个页面的链接，稍后作为 `NOTION_PAGE`。

注意：这里要复制普通 Notion 页面链接，不要复制数据库链接。同步器会自己在这个页面下面创建数据库。

## 4. 创建 Notion Integration

1. 打开 [Notion Integrations](https://www.notion.so/my-integrations)。
2. 点击 `New integration`。
3. 名字填：

```text
WeRead Link Notion
```

4. 选择你的 Notion workspace。
5. 保存。
6. 找到 `Internal Integration Secret` 或 `Internal Integration Token`。
7. 点击显示或复制。

复制出来的值就是 `NOTION_TOKEN`，常见格式类似：

```text
secret_xxxxxxxxxxxxxxxxx
```

或者：

```text
ntn_xxxxxxxxxxxxxxxxx
```

## 5. 把 Notion 页面授权给 Integration

这一步非常容易漏。漏掉以后，Actions 会报 Notion 权限错误。

1. 回到你刚才创建的 Notion 页面。
2. 点击右上角 `Share`，或者点击 `...`。
3. 找到 `Connections` / `Add connections`。
4. 选择刚才创建的 `WeRead Link Notion`。
5. 确认授权。

完成后，integration 才能在这个页面下创建数据库和更新内容。

## 6. 准备 WeRead API Key

1. 打开微信读书 Skill 页面：

[https://weread.qq.com/r/weread-skills](https://weread.qq.com/r/weread-skills)

2. 按页面提示登录微信读书。
3. 找到 API Key / 获取密钥 / 复制密钥入口。
4. 复制 key 本身。

常见格式类似：

```text
wrk-xxxxxxxxxxxxxxxx
```

或者：

```text
wrk_xxxxxxxxxxxxxxxx
```

只复制 key，不要复制成下面这样：

```text
Authorization: Bearer wrk-xxxxxxxx
Bearer wrk-xxxxxxxx
WEREAD_API_KEY=wrk-xxxxxxxx
```

## 7. 添加 GitHub Secrets

进入你的仓库页面：

```text
Settings -> Secrets and variables -> Actions
```

点击：

```text
New repository secret
```

创建三次，分别填：

| Name | Secret |
|---|---|
| `WEREAD_API_KEY` | 你复制的微信读书 API Key |
| `NOTION_TOKEN` | 你复制的 Notion integration token |
| `NOTION_PAGE` | 你复制的 Notion 页面链接 |

保存后，GitHub 页面不会再显示 Secret 的明文，这是正常的。

## 8. 可选：添加 GitHub Variables

进入：

```text
Settings -> Secrets and variables -> Actions -> Variables
```

可选添加：

| Name | 推荐值 | 说明 |
|---|---|---|
| `SYNC_NOTES` | `true` | 是否同步划线和想法 |
| `MAX_NOTEBOOKS` | `0` | 同步多少本书的笔记，`0` 表示不限 |

如果你第一次运行怕太慢，可以先填：

```text
MAX_NOTEBOOKS=5
```

跑通以后再改成：

```text
MAX_NOTEBOOKS=0
```

## 9. 第一次运行

1. 打开仓库的 `Actions` 页面。
2. 左侧选择 `Sync WeRead Link Notion`。
3. 点击右侧 `Run workflow`。
4. 分支选择 `main`。
5. 再点击绿色的 `Run workflow`。
6. 等待任务完成。

第一次运行会做这些事：

1. 检查三个环境变量是否存在。
2. 检查微信读书 API 是否能访问。
3. 生成 `assets/heatmap.png`、`assets/heatmap.svg`、`assets/heatmap.json`。
4. 把热力图文件提交回 GitHub 仓库。
5. 在 Notion 页面下创建阅读面板和数据库。
6. 同步书架、每日阅读、笔记。

第一次可能比后续运行慢，这是正常的。

## 10. 验证是否成功

GitHub Actions 运行成功后，检查两处。

仓库里应该出现：

```text
assets/heatmap.png
assets/heatmap.svg
assets/heatmap.json
```

Notion 页面里应该出现：

```text
阅读热力图
书库
笔记
每日阅读
同步快照
```

如果 Actions 显示成功，但 Notion 页面没变化，优先检查：

1. `NOTION_PAGE` 是否填的是页面链接。
2. 页面是否授权给了 integration。
3. 你看的是否就是 `NOTION_PAGE` 对应的那个页面。

更多问题见：[TROUBLESHOOTING.md](TROUBLESHOOTING.md)

## 11. 以后怎么用

默认每天北京时间 00:30 自动同步。

你也可以随时手动同步：

```text
Actions -> Sync WeRead Link Notion -> Run workflow
```

## 12. 本地测试，可跳过

普通用户不需要本地测试。只有你想改代码时才需要。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Windows PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env
```

把 `.env` 里的三个值填好以后运行：

```bash
python -m weread_link_notion check
python -m weread_link_notion heatmap
python -m weread_link_notion sync
```

不要提交 `.env` 文件。
