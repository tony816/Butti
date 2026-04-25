import argparse
import email.utils
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree


APP_DIR = Path(__file__).resolve().parent
DEFAULT_MAX_RESULTS = 50
REQUEST_DELAY_SECONDS = 0.7


class NewsCrawlerError(Exception):
    pass


def request_text(url, params=None, headers=None, timeout=30):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers=headers
        or {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise NewsCrawlerError(f"HTTP {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise NewsCrawlerError(f"Network error: {exc.reason}") from exc


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise NewsCrawlerError(f"Invalid date '{value}'. Use YYYY-MM-DD.") from exc


def validate_date_range(start_date, end_date):
    if end_date < start_date:
        raise NewsCrawlerError("End date must be the same as or later than start date.")


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def safe_filename(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", "_", value).strip("._")
    return value[:80] or "company"


def default_output_path(company, start_date, end_date):
    filename = f"news_{safe_filename(company)}_{start_date.isoformat()}_{end_date.isoformat()}.json"
    return APP_DIR / filename


def build_naver_params(company, start_date, end_date, start):
    start_compact = start_date.strftime("%Y%m%d")
    end_compact = end_date.strftime("%Y%m%d")
    return {
        "where": "news",
        "query": company,
        "sm": "tab_opt",
        "sort": "1",
        "pd": "3",
        "ds": start_date.strftime("%Y.%m.%d"),
        "de": end_date.strftime("%Y.%m.%d"),
        "nso": f"so:dd,p:from{start_compact}to{end_compact},a:all",
        "start": str(start),
    }


def extract_first(pattern, text, flags=re.IGNORECASE | re.DOTALL):
    match = re.search(pattern, text, flags)
    return clean_text(match.group(1)) if match else ""


def parse_naver_legacy_news_html(page_html):
    items = []
    title_matches = list(
        re.finditer(
            r'<a\b(?=[^>]*\bclass="[^"]*\bnews_tit\b[^"]*")[^>]*href="([^"]+)"[^>]*title="([^"]*)"[^>]*>(.*?)</a>',
            page_html,
            re.IGNORECASE | re.DOTALL,
        )
    )

    for index, match in enumerate(title_matches):
        block_start = max(
            page_html.rfind("<li", 0, match.start()),
            page_html.rfind('<div class="news_wrap"', 0, match.start()),
        )
        next_start = title_matches[index + 1].start() if index + 1 < len(title_matches) else len(page_html)
        block = page_html[block_start if block_start >= 0 else match.start() : next_start]

        link = html.unescape(match.group(1).strip())
        title = clean_text(match.group(2) or match.group(3))
        publisher = extract_first(r'<a\b(?=[^>]*\bclass="[^"]*\binfo press\b[^"]*")[^>]*>(.*?)</a>', block)
        if not publisher:
            publisher = extract_first(r'<span\b(?=[^>]*\bclass="[^"]*\bpress\b[^"]*")[^>]*>(.*?)</span>', block)
        publisher = publisher.replace("언론사 선정", "").strip()
        summary = extract_first(r'<a\b(?=[^>]*\bclass="[^"]*\bdsc_txt_wrap\b[^"]*")[^>]*>(.*?)</a>', block)
        published_at = extract_first(r'<span\b(?=[^>]*\bclass="[^"]*\binfo\b[^"]*")[^>]*>(\d{4}\.\d{2}\.\d{2}\.)</span>', block)
        if published_at.endswith("."):
            published_at = published_at[:-1].replace(".", "-")

        items.append(
            {
                "source": "naver",
                "title": title,
                "publisher": publisher,
                "published_at": published_at,
                "link": link,
                "summary": summary,
            }
        )

    return items


def parse_naver_sds_news_html(page_html):
    items = []
    blocks = re.split(r'(?=<div\b[^>]*\bdata-sds-comp="Profile")', page_html)
    for block in blocks:
        if 'data-heatmap-target=".tit"' not in block:
            continue

        title_match = re.search(
            r'<a\b(?=[^>]*\bdata-heatmap-target="\.tit")[^>]*\bhref="([^"]+)"[^>]*>(.*?)</a>',
            block,
            re.IGNORECASE | re.DOTALL,
        )
        if not title_match:
            continue

        publisher = extract_first(
            r'sds-comps-profile-info-title-text.*?<span\b[^>]*>(.*?)</span>',
            block,
        )
        if not publisher:
            publisher = extract_first(
                r'<img\b[^>]*\balt="([^"]+?)의 프로필 이미지"',
                block,
            )

        published_at = extract_first(r'>(\d{4}\.\d{2}\.\d{2}\.)<', block)
        if published_at.endswith("."):
            published_at = published_at[:-1].replace(".", "-")

        summary_match = re.search(
            r'<a\b(?=[^>]*\bdata-heatmap-target="\.body")[^>]*>(.*?)</a>',
            block,
            re.IGNORECASE | re.DOTALL,
        )

        items.append(
            {
                "source": "naver",
                "title": clean_text(title_match.group(2)),
                "publisher": publisher,
                "published_at": published_at,
                "link": html.unescape(title_match.group(1).strip()),
                "summary": clean_text(summary_match.group(1)) if summary_match else "",
            }
        )

    return items


def parse_naver_news_html(page_html):
    items = parse_naver_legacy_news_html(page_html)
    if items:
        return items
    return parse_naver_sds_news_html(page_html)


def crawl_naver_news(company, start_date, end_date, max_results, fetch=request_text):
    results = []
    start = 1
    while len(results) < max_results:
        params = build_naver_params(company, start_date, end_date, start)
        page_html = fetch("https://search.naver.com/search.naver", params=params)
        page_items = parse_naver_news_html(page_html)
        if not page_items:
            if not results and ("검색결과가 없습니다" in page_html or "뉴스검색 결과입니다" in page_html):
                return []
            break
        results.extend(page_items)
        if len(page_items) < 10:
            break
        start += 10
        time.sleep(REQUEST_DELAY_SECONDS)
    return results[:max_results]


def build_google_rss_params(company, start_date, end_date):
    exclusive_end = end_date + timedelta(days=1)
    query = f"{company} after:{start_date.isoformat()} before:{exclusive_end.isoformat()}"
    return {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}


def parse_google_pubdate(value):
    if not value:
        return ""
    parsed = email.utils.parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def parse_google_news_rss(rss_xml):
    try:
        root = ElementTree.fromstring(rss_xml)
    except ElementTree.ParseError as exc:
        raise NewsCrawlerError("Google News RSS response was not valid XML.") from exc
    items = []
    for item in root.findall("./channel/item"):
        pub_date = item.findtext("pubDate", default="")
        try:
            published_at = parse_google_pubdate(pub_date)
        except (TypeError, ValueError, IndexError):
            published_at = clean_text(pub_date)

        items.append(
            {
                "source": "google",
                "title": clean_text(item.findtext("title", default="")),
                "publisher": clean_text(item.findtext("source", default="")),
                "published_at": published_at,
                "link": clean_text(item.findtext("link", default="")),
                "summary": clean_text(item.findtext("description", default="")),
            }
        )
    return items


def crawl_google_news(company, start_date, end_date, max_results, fetch=request_text):
    params = build_google_rss_params(company, start_date, end_date)
    rss_xml = fetch("https://news.google.com/rss/search", params=params)
    return parse_google_news_rss(rss_xml)[:max_results]


def deduplicate_items(items):
    seen = set()
    unique = []
    for item in items:
        link_key = item.get("link", "").strip().casefold()
        title_key = re.sub(r"\s+", " ", item.get("title", "")).strip().casefold()
        publisher_key = item.get("publisher", "").strip().casefold()
        key = ("link", link_key) if link_key else ("title", publisher_key, title_key)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def crawl_company_news(company, start_date, end_date, source="all", max_results=DEFAULT_MAX_RESULTS, progress=None):
    company = company.strip()
    if not company:
        raise NewsCrawlerError("Company name is empty.")
    validate_date_range(start_date, end_date)

    sources = ["naver", "google"] if source == "all" else [source]
    items = []
    errors = {}

    for source_name in sources:
        if progress:
            progress(f"Crawling {source_name} news...")
        try:
            if source_name == "naver":
                source_items = crawl_naver_news(company, start_date, end_date, max_results)
            elif source_name == "google":
                source_items = crawl_google_news(company, start_date, end_date, max_results)
            else:
                raise NewsCrawlerError(f"Unknown source: {source_name}")
            items.extend(source_items)
            if progress:
                progress(f"Found {len(source_items)} {source_name} item(s).")
        except NewsCrawlerError as exc:
            errors[source_name] = str(exc)
            if progress:
                progress(f"{source_name} failed: {exc}")

    return {
        "company": company,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "errors": errors,
        "items": deduplicate_items(items),
    }


def write_json(result, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def parse_args():
    parser = argparse.ArgumentParser(description="Crawl company news metadata from Naver News and Google News.")
    parser.add_argument("company", nargs="?", help="Company name, for example Samsung Electronics or 삼성전자")
    parser.add_argument("--start-date", required=True, help="Start date in YYYY-MM-DD format")
    parser.add_argument("--end-date", required=True, help="End date in YYYY-MM-DD format")
    parser.add_argument("--output", help="JSON output path. Defaults to news_<company>_<start>_<end>.json")
    parser.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS, help="Maximum results per source. Default: 50")
    parser.add_argument("--source", choices=["all", "naver", "google"], default="all", help="News source. Default: all")
    return parser.parse_args()


def main():
    args = parse_args()
    company = args.company or input("Company name: ").strip()
    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)
    if args.max_results < 1:
        raise NewsCrawlerError("--max-results must be 1 or greater.")

    result = crawl_company_news(
        company=company,
        start_date=start_date,
        end_date=end_date,
        source=args.source,
        max_results=args.max_results,
        progress=print,
    )
    output_path = Path(args.output) if args.output else default_output_path(company, start_date, end_date)
    write_json(result, output_path)

    print()
    print(f"Done: {len(result['items'])} unique news item(s) saved.")
    print(f"Output file: {output_path.resolve()}")
    if result["errors"]:
        print(f"Source errors: {', '.join(result['errors'])}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCanceled")
        raise SystemExit(130)
    except NewsCrawlerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
