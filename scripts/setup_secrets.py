"""Helper for collecting WeRead Link Notion setup values.

The script never uploads or commits secrets. It only opens setup pages, checks
obvious formatting mistakes, and can write a local .env file for testing.
GitHub Actions still needs the same values saved as repository secrets.
"""

from __future__ import annotations

import argparse
import re
import textwrap
import webbrowser
from pathlib import Path


WEREAD_SKILL_URL = "https://weread.qq.com/r/weread-skills"
NOTION_INTEGRATIONS_URL = "https://www.notion.so/my-integrations"


def main() -> int:
    parser = argparse.ArgumentParser(description="Open setup pages and validate required secrets.")
    parser.add_argument("--open", action="store_true", help="Open WeRead, Notion, and GitHub setup pages.")
    parser.add_argument("--repo", default="", help="GitHub repository, for example e5145/weread-link-notion.")
    args = parser.parse_args()

    print_header()

    repo = args.repo.strip() or ask("GitHub 仓库名，格式 owner/repo；不知道可留空", required=False)
    if args.open:
        open_setup_pages(repo)

    print(
        "\n请按提示粘贴三个值。输入内容会直接显示在终端里，"
        "所以不要在直播、录屏或公开截图时运行。\n"
    )

    values = {
        "WEREAD_API_KEY": ask_secret("WEREAD_API_KEY", validate_weread_key),
        "NOTION_TOKEN": ask_secret("NOTION_TOKEN", validate_notion_token),
        "NOTION_PAGE": ask_secret("NOTION_PAGE", validate_notion_page),
    }

    if yes_no("\n是否写入本地 .env 文件用于本地测试？", default=False):
        write_env(Path(".env"), values)
        print("已写入 .env。这个文件只用于本地测试，不要提交到 GitHub。")

    print_github_steps(repo)
    return 0


def print_header() -> None:
    print(
        textwrap.dedent(
            """
            WeRead Link Notion 设置向导

            你需要准备三个值：
            1. WEREAD_API_KEY：微信读书 API Key，通常形如 wrk-... 或 wrk_...
            2. NOTION_TOKEN：Notion integration token，通常形如 secret_... 或 ntn_...
            3. NOTION_PAGE：你的 Notion 阅读面板页面链接

            文档见 docs/GET_SECRETS.md
            """
        ).strip()
    )


def open_setup_pages(repo: str) -> None:
    webbrowser.open(WEREAD_SKILL_URL)
    webbrowser.open(NOTION_INTEGRATIONS_URL)
    if repo:
        webbrowser.open(f"https://github.com/{repo}/settings/secrets/actions")


def ask(label: str, required: bool = True) -> str:
    while True:
        value = input(label + ": ").strip()
        if value or not required:
            return value
        print("这个值不能为空。")


def ask_secret(name: str, validator) -> str:
    while True:
        value = ask(name)
        ok, message = validator(value)
        if ok:
            print(f"{name}: 格式看起来正常。")
            return value
        print(f"{name}: {message}")
        if yes_no("仍然使用这个值？", default=False):
            return value


def yes_no(prompt: str, default: bool = True) -> bool:
    suffix = "Y/n" if default else "y/N"
    value = input(f"{prompt} [{suffix}] ").strip().lower()
    if not value:
        return default
    return value in ("y", "yes", "是", "好")


def validate_weread_key(value: str) -> tuple[bool, str]:
    if value.startswith("Authorization:"):
        return False, "只粘贴 key 本身，不要带 Authorization: Bearer。"
    if value.lower().startswith("bearer "):
        return False, "只粘贴 Bearer 后面的 key，不要带 Bearer。"
    if value.startswith("WEREAD_API_KEY="):
        return False, "只粘贴等号后面的 key，不要带 WEREAD_API_KEY=。"
    if value.startswith(("wrk-", "wrk_")):
        return True, ""
    if len(value) >= 20:
        return True, ""
    return False, "看起来太短。常见格式是 wrk-... 或 wrk_..."


def validate_notion_token(value: str) -> tuple[bool, str]:
    if value.startswith(("secret_", "ntn_")):
        return True, ""
    if value.startswith("NOTION_TOKEN="):
        return False, "只粘贴等号后面的 token，不要带 NOTION_TOKEN=。"
    if len(value) >= 30:
        return True, ""
    return False, "看起来不像 Notion integration token。"


def validate_notion_page(value: str) -> tuple[bool, str]:
    if "notion.so" in value or "notion.site" in value:
        return True, ""
    if value.startswith("NOTION_PAGE="):
        return False, "只粘贴等号后面的页面链接，不要带 NOTION_PAGE=。"
    if re.search(r"([a-fA-F0-9]{32}|[a-fA-F0-9-]{36})", value):
        return True, ""
    return False, "请粘贴 Notion 页面 URL，或者页面 ID。"


def write_env(path: Path, values: dict[str, str]) -> None:
    lines = [
        "# Local secrets for testing. Do not commit this file.",
        f"WEREAD_API_KEY={values['WEREAD_API_KEY']}",
        f"NOTION_TOKEN={values['NOTION_TOKEN']}",
        f"NOTION_PAGE={values['NOTION_PAGE']}",
        "GITHUB_BRANCH=main",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def print_github_steps(repo: str) -> None:
    print("\n接下来把这三个值保存到 GitHub Secrets。\n")
    if repo:
        print(f"打开：https://github.com/{repo}/settings/secrets/actions")
    else:
        print("打开：你的仓库 -> Settings -> Secrets and variables -> Actions")

    print(
        textwrap.dedent(
            """
            点击 New repository secret，创建三次：

            Name: WEREAD_API_KEY
            Secret: 你的微信读书 API Key

            Name: NOTION_TOKEN
            Secret: 你的 Notion integration token

            Name: NOTION_PAGE
            Secret: 你的 Notion 阅读面板页面链接

            保存后，到 Actions -> Sync WeRead Link Notion -> Run workflow。
            """
        ).strip()
    )
    print("\n安全提醒：不要把这些值粘贴进 README、issue、截图、代码或 commit。")


if __name__ == "__main__":
    raise SystemExit(main())
