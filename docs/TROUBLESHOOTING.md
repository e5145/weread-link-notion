# 常见问题排错

先看 GitHub Actions 里的失败步骤。大多数问题都能从步骤名判断：

| 失败步骤 | 通常原因 |
|---|---|
| `Check connection` | `WEREAD_API_KEY`、`NOTION_TOKEN`、`NOTION_PAGE` 有问题 |
| `Generate heatmap` | 微信读书阅读数据获取失败，或热力图生成失败 |
| `Publish heatmap assets` | GitHub Actions 没有写仓库权限 |
| `Sync Notion` | Notion token、页面权限或页面链接有问题 |

## Actions 里没有同步任务

检查仓库里是否有这个文件：

```text
.github/workflows/sync.yml
```

注意路径必须完全一致，不能放成：

```text
github/workflows/sync.yml
```

也不能只上传 `sync.yml`。

## 报 Missing required environment variables

说明 GitHub Secrets 没配好。

检查仓库：

```text
Settings -> Secrets and variables -> Actions -> Secrets
```

必须有三个 secret，名字必须完全一致：

```text
WEREAD_API_KEY
NOTION_TOKEN
NOTION_PAGE
```

常见错误：

- 少填了一个。
- 名字大小写不一致。
- 填到了 `Variables`，而不是 `Secrets`。
- 填到了另一个仓库。

## WeRead API Key 不通过

先检查 `WEREAD_API_KEY` 是否只填了 key 本身。

正确：

```text
wrk-xxxxxxxx
```

错误：

```text
Bearer wrk-xxxxxxxx
Authorization: Bearer wrk-xxxxxxxx
WEREAD_API_KEY=wrk-xxxxxxxx
```

如果格式没问题但仍然失败：

1. 回到微信读书 Skill 页面重新复制一次 key。
2. 确认复制时没有多余空格或换行。
3. 在 GitHub Secrets 里删除旧值，重新创建。
4. 重新运行 Actions。

## Notion 权限错误

最常见原因：Notion 页面没有授权给 integration。

解决方法：

1. 打开 `NOTION_PAGE` 对应的 Notion 页面。
2. 点击右上角 `Share` 或 `...`。
3. 找到 `Connections` / `Add connections`。
4. 添加你的 `WeRead Link Notion` integration。
5. 回到 GitHub Actions 重新运行。

如果仍然失败：

- 确认 `NOTION_TOKEN` 来自同一个 Notion workspace。
- 确认 `NOTION_PAGE` 是普通页面链接，不是数据库链接。
- 确认你没有把页面移到另一个未授权的 workspace。

## 热力图没有显示

先看仓库里有没有生成文件：

```text
assets/heatmap.png
assets/heatmap.svg
assets/heatmap.json
```

### 仓库里没有这些文件

说明 `Generate heatmap` 或 `Publish heatmap assets` 失败。

检查：

1. GitHub Actions 日志里 `Generate heatmap` 是否成功。
2. 仓库 `Settings -> Actions -> General` 里，Workflow permissions 是否允许写入。
3. `.github/workflows/sync.yml` 里是否有：

```yaml
permissions:
  contents: write
```

### 仓库里有文件，但 Notion 没显示

检查：

1. `Sync Notion` 步骤是否成功。
2. Notion 页面是否刷新过。
3. `同步快照` 数据库里最新记录的 `Heatmap` 字段是否有链接。
4. 仓库如果是私有仓库，Notion 可能无法稳定加载 raw 图片链接。此时仍可以查看 `每日阅读` 数据库，热力图文件也会保留在 GitHub 仓库里。

## Actions 跑了很久

第一次同步笔记可能比较慢，因为要逐本书读取划线和想法。

可以先限制笔记数量：

```text
MAX_NOTEBOOKS=5
```

路径：

```text
Settings -> Secrets and variables -> Actions -> Variables
```

确认流程跑通以后，再改回：

```text
MAX_NOTEBOOKS=0
```

## 不想同步笔记

添加 GitHub Variable：

```text
SYNC_NOTES=false
```

这样只同步书库、每日阅读和热力图。

## GitHub 自动提交热力图失败

如果 `Publish heatmap assets` 报权限错误，检查仓库设置：

```text
Settings -> Actions -> General -> Workflow permissions
```

选择：

```text
Read and write permissions
```

保存后重新运行 Actions。

## Notion 页面重复创建内容

正常情况下，同步器会尽量复用已经创建的数据库。

新版同步器会自动保留每类数据库里数据最多的那个，并归档其余同名数据库入口。首页会维护一个 `微信读书阅读面板`，你在面板里看到的是摘要，完整书库、笔记和每日阅读数据仍然在对应数据库里。

如果你手动删除或重命名了数据库，下一次运行可能会重新创建。建议：

1. 不要删除 `书库`、`笔记`、`每日阅读`、`同步快照`。
2. 可以新增自己的视图、筛选、分组。
3. 不建议修改关键字段名，例如 `Book ID`、`Note ID`、`Date`。

## 仍然不知道哪里错了

把 GitHub Actions 失败步骤截图，重点截这几处：

1. 失败的步骤名。
2. 红色报错信息。
3. 报错前后 20 行日志。

不要截图或公开显示任何 secret 明文。
