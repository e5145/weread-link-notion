import argparse
from datetime import datetime

from dotenv import load_dotenv

from .config import Config
from .sync import generate_heatmap_assets, run_sync, build_client


def main(argv=None):
    load_dotenv()
    parser = argparse.ArgumentParser(prog="weread-link-notion")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check", help="Check environment variables and WeRead connectivity.")

    heatmap_parser = subparsers.add_parser("heatmap", help="Generate heatmap image assets.")
    heatmap_parser.add_argument("--year", type=int, default=datetime.now().year)

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

    if args.command == "heatmap":
        if not config.weread_api_key:
            raise RuntimeError("WEREAD_API_KEY is required.")
        generate_heatmap_assets(config, args.year)
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
