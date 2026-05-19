# 三个密钥怎么获取

这个项目必须准备三个值：

```text
WEREAD_API_KEY
NOTION_TOKEN
NOTION_PAGE
```

它们不要写进代码，不要提交到 GitHub，不要发到 issue，不要放进截图。

正确位置是：

```text
GitHub 仓库 -> Settings -> Secrets and variables -> Actions -> Secrets
```

## 一句话理解这三个值

| 名称 | 它是什么 | 从哪里复制 |
|---|---|---|
| `WEREAD_API_KEY` | 证明“这是你的微信读书账号”的 key | 微信读书 Skill 页面 |
| `NOTION_TOKEN` | 允许程序操作 Notion 的 token | Notion integration 页面 |
| `NOTION_PAGE` | 同步结果写到哪个 Notion 页面 | 你创建的 Notion 页面链接 |

## 方式一：使用辅助脚本

如果你已经在项目目录里，可以运行：

```bash
python scripts/setup_secrets.py --open --repo e5145/weread-link-notion
```

这个脚本会做三件事：

1. 打开微信读书 Skill 页面。
2. 打开 Notion integration 页面。
3. 打开 GitHub Secrets 页面。

它还会提示你粘贴三个值，并做简单格式检查。

注意：脚本不能替你直接创建 GitHub Secrets。GitHub Secrets 属于高权限设置，必须你在网页里确认保存。

## 方式二：手动获取

下面是完全手动的傻瓜式流程。

## 1. 获取 WEREAD_API_KEY

打开：

[https://weread.qq.com/r/weread-skills](https://weread.qq.com/r/weread-skills)

然后按页面提示操作：

1. 登录微信读书。
2. 如果页面要求扫码，用微信扫码确认。
3. 找到 API Key / 获取密钥 / 复制密钥相关按钮。
4. 复制 key 本身。

你要复制的通常长这样：

```text
wrk-xxxxxxxxxxxxxxxx
```

或者：

```text
wrk_xxxxxxxxxxxxxxxx
```

只复制 key 本身。不要带这些前缀：

```text
Authorization: Bearer
Bearer
WEREAD_API_KEY=
```

正确示例：

```text
wrk-abc123xxxxxxxx
```

错误示例：

```text
Bearer wrk-abc123xxxxxxxx
Authorization: Bearer wrk-abc123xxxxxxxx
WEREAD_API_KEY=wrk-abc123xxxxxxxx
```

如果你已经从别的入口拿到了 `wrk-...` 或 `wrk_...`，直接用那个值即可。

## 2. 获取 NOTION_TOKEN

打开：

[https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)

然后这样做：

1. 点击 `New integration`。
2. Name 填：

```text
WeRead Link Notion
```

3. 选择你的 Notion workspace。
4. 保存。
5. 进入这个 integration 的详情页。
6. 找到 `Internal Integration Secret` 或 `Internal Integration Token`。
7. 点击 `Show` 或复制按钮。

复制出来的值就是 `NOTION_TOKEN`。

常见格式：

```text
secret_xxxxxxxxxxxxxxxxx
```

或者：

```text
ntn_xxxxxxxxxxxxxxxxx
```

## 3. 获取 NOTION_PAGE

`NOTION_PAGE` 不是 token，也不是数据库链接。它是你希望同步结果写入的 Notion 页面链接。

操作步骤：

1. 打开 Notion。
2. 新建一个空白页面。
3. 页面名可以叫：

```text
阅读面板
```

4. 点击右上角 `Share`。
5. 点击 `Copy link`。
6. 复制出来的页面链接就是 `NOTION_PAGE`。

常见格式类似：

```text
https://www.notion.so/xxxxxx?pvs=4
```

也可以是：

```text
https://your-workspace.notion.site/xxxxxx
```

## 4. 把 Notion 页面授权给 Integration

这一步和 `NOTION_PAGE` 一样重要。

如果不做这一步，程序虽然有 `NOTION_TOKEN`，但还是没有权限写入你的页面。

操作步骤：

1. 打开刚才创建的 Notion 页面。
2. 点击右上角 `Share`，或者点击 `...`。
3. 找到 `Connections` / `Add connections`。
4. 搜索并选择：

```text
WeRead Link Notion
```

5. 确认连接。

## 5. 把三个值放进 GitHub Secrets

打开你的 GitHub 仓库：

```text
https://github.com/e5145/weread-link-notion
```

进入：

```text
Settings -> Secrets and variables -> Actions
```

点击：

```text
New repository secret
```

创建三次：

### 第一次

Name：

```text
WEREAD_API_KEY
```

Secret：

```text
你复制的微信读书 API Key
```

### 第二次

Name：

```text
NOTION_TOKEN
```

Secret：

```text
你复制的 Notion integration token
```

### 第三次

Name：

```text
NOTION_PAGE
```

Secret：

```text
你复制的 Notion 页面链接
```

保存后 GitHub 不会再显示明文，这是正常的。

## 6. 检查有没有填对

打开仓库：

```text
Actions -> Sync WeRead Link Notion -> Run workflow
```

如果三项都正确，第一次运行会创建 Notion 页面内容，并生成热力图文件。

如果失败，按下面排查。

## 常见错误

### 1. WEREAD_API_KEY 填成了 Bearer 开头

错误：

```text
Bearer wrk-xxxx
```

正确：

```text
wrk-xxxx
```

### 2. NOTION_TOKEN 正确，但 Notion 仍然报权限错误

通常是你没有把 Notion 页面授权给 integration。

回到 Notion 页面：

```text
Share / ... -> Connections -> Add connections -> WeRead Link Notion
```

### 3. NOTION_PAGE 填成了数据库链接

请填普通页面链接。同步器会自己在页面下面创建数据库。

### 4. Secret 名字打错

名字必须完全一致，大小写也要一致：

```text
WEREAD_API_KEY
NOTION_TOKEN
NOTION_PAGE
```

### 5. 在 README 或 .env 里填了密钥，但 Actions 还是读不到

GitHub Actions 只读取 GitHub Secrets。

`.env` 只适合本地测试，不能替代 GitHub Secrets。
