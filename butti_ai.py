import argparse
import json
import sys
from pathlib import Path

from butti_interests import DEFAULT_INTERESTS_FILENAME, add_interests, load_interests
from crawl_catch_recruits import DEFAULT_MAX_RESULTS as DEFAULT_CATCH_MAX_RESULTS
from crawl_catch_recruits import crawl_catch_recruits, write_json as write_catch_json
from crawl_company_news import DEFAULT_MAX_RESULTS as DEFAULT_NEWS_MAX_RESULTS
from crawl_company_news import crawl_company_news, parse_date as parse_news_date, write_json as write_news_json
from download_business_reports import DEFAULT_OUTPUT_DIR


APP_DIR = Path(__file__).resolve().parent


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def resolve_output_dir(value):
    return Path(value) if value else DEFAULT_OUTPUT_DIR


def resolve_interests_path(output_dir, value):
    return Path(value) if value else Path(output_dir) / DEFAULT_INTERESTS_FILENAME


def command_catch_search(args):
    output_dir = resolve_output_dir(args.output_dir)
    result = crawl_catch_recruits(
        keyword=args.keyword or "",
        max_results=args.max_results,
        page_size=args.page_size,
        start_date=args.start_date,
        end_date=args.end_date,
        progress=print if args.verbose else None,
    )
    if args.output:
        output_path = Path(args.output)
    else:
        from crawl_catch_recruits import default_output_path

        output_path = output_dir / default_output_path(args.keyword or "all").name
    write_catch_json(result, output_path)
    summary = {
        "output_path": str(output_path.resolve()),
        "keyword": result["keyword"],
        "count": len(result["items"]),
        "items": result["items"],
    }
    print_json(summary)
    return 0


def command_interests_list(args):
    output_dir = resolve_output_dir(args.output_dir)
    path = resolve_interests_path(output_dir, args.interests)
    result = load_interests(path)
    result["path"] = str(path.resolve())
    print_json(result)
    return 0


def select_items(items, indexes):
    selected = []
    for index in indexes:
        if index < 1 or index > len(items):
            raise ValueError(f"Item index out of range: {index}")
        selected.append(items[index - 1])
    return selected


def command_interests_add(args):
    output_dir = resolve_output_dir(args.output_dir)
    interests_path = resolve_interests_path(output_dir, args.interests)
    source = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
    source_items = source.get("items", [])
    selected = select_items(source_items, args.index) if args.index else source_items
    result = add_interests(interests_path, selected)
    print_json(
        {
            "path": str(result["path"].resolve()),
            "added": result["added"],
            "count": result["count"],
            "items": result["items"],
        }
    )
    return 0


def command_news(args):
    start_date = parse_news_date(args.start_date)
    end_date = parse_news_date(args.end_date)
    output_dir = resolve_output_dir(args.output_dir)
    result = crawl_company_news(
        company=args.company,
        start_date=start_date,
        end_date=end_date,
        source=args.source,
        max_results=args.max_results,
        progress=print if args.verbose else None,
    )
    if args.output:
        output_path = Path(args.output)
    else:
        from crawl_company_news import default_output_path

        output_path = output_dir / default_output_path(args.company, start_date, end_date).name
    write_news_json(result, output_path)
    print_json(
        {
            "output_path": str(output_path.resolve()),
            "company": result["company"],
            "count": len(result["items"]),
            "errors": result["errors"],
            "items": result["items"],
        }
    )
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="AI-friendly command line interface for Butti.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    catch = subparsers.add_parser("catch-search", help="Search Catch recruit postings by title keyword.")
    catch.add_argument("keyword", nargs="?", default="", help="Title keyword. Leave blank for all postings.")
    catch.add_argument("--start-date", help="YYYY-MM-DD opened on or after.")
    catch.add_argument("--end-date", help="YYYY-MM-DD opened on or before.")
    catch.add_argument("--max-results", type=int, default=DEFAULT_CATCH_MAX_RESULTS)
    catch.add_argument("--page-size", type=int, default=30)
    catch.add_argument("--output-dir")
    catch.add_argument("--output")
    catch.add_argument("--verbose", action="store_true")
    catch.set_defaults(func=command_catch_search)

    interests = subparsers.add_parser("interests-list", help="List saved interested Catch recruits.")
    interests.add_argument("--output-dir")
    interests.add_argument("--interests")
    interests.set_defaults(func=command_interests_list)

    add = subparsers.add_parser("interests-add", help="Add recruit postings from a search JSON to interests.")
    add.add_argument("--from-file", required=True, help="Catch search JSON file.")
    add.add_argument("--index", type=int, action="append", help="1-based item index to add. Repeatable. Omit to add all.")
    add.add_argument("--output-dir")
    add.add_argument("--interests")
    add.set_defaults(func=command_interests_add)

    news = subparsers.add_parser("news", help="Crawl company news metadata.")
    news.add_argument("company")
    news.add_argument("--start-date", required=True)
    news.add_argument("--end-date", required=True)
    news.add_argument("--source", choices=("all", "naver", "google"), default="all")
    news.add_argument("--max-results", type=int, default=DEFAULT_NEWS_MAX_RESULTS)
    news.add_argument("--output-dir")
    news.add_argument("--output")
    news.add_argument("--verbose", action="store_true")
    news.set_defaults(func=command_news)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
