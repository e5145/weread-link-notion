import argparse
from datetime import datetime

from dotenv import load_dotenv

from .config import Config
from .notion import NotionStore
from .sync import generate_heatmap_assets, generate_monthly_chart_assets, generate_profile_assets, run_sync, build_client


def main(argv=None):
    load_dotenv()
    parser = argparse.ArgumentParser(prog="weread-link-notion")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check", help="Check environment variables and WeRead connectivity.")
    subparsers.add_parser("reset-page", help="Archive all blocks in the target Notion page before rebuilding.")

    heatmap_parser = subparsers.add_parser("heatmap", help="Generate heatmap image assets.")
    heatmap_parser.add_argument("--year", type=int, default=datetime.now().year)

    monthly_parser = subparsers.add_parser("monthly-chart", help="Generate this month's reading chart image assets.")
    monthly_parser.add_argument("--year", type=int, default=None)
    monthly_parser.add_argument("--month", type=int, default=None)

    subparsers.add_parser("profile", help="Generate reading profile image assets.")

    sync_parser = subparsers.add_parser("sync", help="Sync WeRead data to Notion.")
    sync_parser.add_argument("--skip-notes", action="store_true", help="Skip note/highlight export for this run.")
    sync_parser.add_argument("--max-notebooks", type=int, default=None, help="Limit note books for a faster test run.")

    args = parser.parse_args(argv)
    config = Config.from_env()

    if args.command == "check":
        config.validate()
        client = build_client(config)
        shelf = client.get_shelf()
        books = len(shelf.get("books") or [])
        albums = len(shelf.get("albums") or [])
        articles = 1 if shelf.get("mp") else 0
        print(f"OK. WeRead shelf visible items: {books + albums + articles} ({books} books, {albums} audiobooks, {articles} article collection).")
        return 0

    if args.command == "reset-page":
        config.validate()
        store = NotionStore(config.notion_token, config.notion_page)
        store.reset_page()
        print("OK. Notion page blocks were archived; the next sync will rebuild the dashboard and databases.")
        return 0

    if args.command == "heatmap":
        if not config.weread_api_key:
            raise RuntimeError("WEREAD_API_KEY is required.")
        generate_heatmap_assets(config, args.year)
        return 0

    if args.command == "monthly-chart":
        if not config.weread_api_key:
            raise RuntimeError("WEREAD_API_KEY is required.")
        generate_monthly_chart_assets(config, args.year, args.month)
        return 0

    if args.command == "profile":
        if not config.weread_api_key:
            raise RuntimeError("WEREAD_API_KEY is required.")
        generate_profile_assets(config)
        return 0

    if args.command == "sync":
        if args.skip_notes:
            object.__setattr__(config, "sync_notes", False)
        if args.max_notebooks is not None:
            object.__setattr__(config, "max_notebooks", args.max_notebooks)
        run_sync(config)
        return 0

    parser.print_help()
    return 1
