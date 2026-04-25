import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
CATCH_RECRUIT_API = "https://www.catch.co.kr/api/v1.0/recruit/information/getRecruitList"
DEFAULT_MAX_RESULTS = 30
DEFAULT_INTERVAL_MINUTES = 60


class CatchRecruitError(Exception):
    pass


def request_json(url, params=None, headers=None, timeout=30):
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
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.catch.co.kr/NCS/RecruitSearch/",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            text = raw.decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise CatchRecruitError(f"HTTP {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise CatchRecruitError(f"Network error: {exc.reason}") from exc

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise CatchRecruitError(f"Invalid JSON response: {text[:300]!r}") from exc


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", str(value or ""))
    value = re.sub(r"\s+", " ", value).strip()
    return value


def first_value(row, *keys):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def safe_filename(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", "_", value).strip("._")
    return value[:80] or "catch_recruits"


def default_output_path(keyword):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return APP_DIR / f"catch_recruits_{safe_filename(keyword or 'all')}_{stamp}.json"


def build_recruit_params(keyword, page, page_size, sort):
    return {
        "Keyword": keyword,
        "JobCode": "",
        "Sido": "",
        "Career": "",
        "JCode": "",
        "Size": "",
        "EduLevel": "",
        "Sort": str(sort),
        "curpage": str(page),
        "pageSize": str(page_size),
        "onRecruitYN": "Y",
        "ExceptIDList": "",
    }


def get_recruit_rows(payload):
    if isinstance(payload, dict):
        for key in ("recruitData", "RecruitData", "recruitList", "RecruitList", "data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        nested = payload.get("data")
        if isinstance(nested, dict):
            return get_recruit_rows(nested)
    return []


def get_total_count(payload):
    if not isinstance(payload, dict):
        return 0
    for key in ("intTotalRecordCount", "totalRecordCount", "totalCount", "count"):
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    nested = payload.get("data")
    if isinstance(nested, dict):
        return get_total_count(nested)
    return 0


def normalize_recruit(row):
    recruit_id = clean_text(first_value(row, "RecruitID", "recruitID", "RecruitId", "ID", "id"))
    company = clean_text(first_value(row, "CompName", "CompNm", "CompanyName", "compName", "company"))
    title = clean_text(first_value(row, "RecruitTitle", "Title", "title", "Subject", "subject"))
    deadline = clean_text(first_value(row, "ApplyEndDatetime", "ApplyEndDate", "EndDate", "CloseDate", "Dday", "DDay", "deadline"))
    start_date = clean_text(first_value(row, "ApplyStartDatetime", "ApplyStartDate", "StartDate", "RegDate", "regDate"))
    career = clean_text(first_value(row, "ExperienceText", "CareerGubunCode", "Career", "CareerName", "career"))
    education = clean_text(first_value(row, "EduLevel", "EduLevelName", "education"))
    location = clean_text(first_value(row, "Sido", "Region", "Area", "WorkArea", "location"))
    employment_type = clean_text(first_value(row, "GubunCode", "RecruitClass", "EmployType", "employmentType"))

    link = clean_text(first_value(row, "RecruitURL", "Url", "url", "link"))
    if not link and recruit_id:
        link = f"https://www.catch.co.kr/NCS/RecruitInfoDetails/{recruit_id}"
    elif link.startswith("/"):
        link = urllib.parse.urljoin("https://www.catch.co.kr", link)

    return {
        "source": "catch",
        "recruit_id": recruit_id,
        "company": company,
        "title": title,
        "deadline": deadline,
        "start_date": start_date,
        "career": career,
        "education": education,
        "location": location,
        "employment_type": employment_type,
        "link": link,
        "raw": row,
    }


def deduplicate_recruits(items):
    seen = set()
    unique = []
    for item in items:
        key = item.get("recruit_id") or item.get("link") or f"{item.get('company')}::{item.get('title')}"
        key = str(key).strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def crawl_catch_recruits(keyword="", max_results=DEFAULT_MAX_RESULTS, page_size=30, sort=1, fetch=request_json, progress=None):
    keyword = keyword.strip()
    if max_results < 1:
        raise CatchRecruitError("max_results must be 1 or greater.")
    if page_size < 1:
        raise CatchRecruitError("page_size must be 1 or greater.")

    items = []
    total_count = 0
    page = 1
    while len(items) < max_results:
        if progress:
            progress(f"Reading Catch recruit page {page}...")
        params = build_recruit_params(keyword, page, min(page_size, max_results), sort)
        payload = fetch(CATCH_RECRUIT_API, params=params)
        rows = get_recruit_rows(payload)
        total_count = total_count or get_total_count(payload)
        if not rows:
            break
        items.extend(normalize_recruit(row) for row in rows)
        if len(rows) < page_size:
            break
        page += 1
        time.sleep(0.5)

    items = deduplicate_recruits(items)[:max_results]
    return {
        "source": "catch",
        "keyword": keyword,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_count": total_count,
        "items": items,
    }


def write_json(result, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def run_once(args):
    result = crawl_catch_recruits(
        keyword=args.keyword or "",
        max_results=args.max_results,
        page_size=args.page_size,
        sort=args.sort,
        progress=print,
    )
    output_path = Path(args.output) if args.output else default_output_path(args.keyword or "all")
    write_json(result, output_path)
    print(f"Done: {len(result['items'])} recruit item(s) saved.")
    print(f"Output file: {output_path.resolve()}")
    return result


def parse_args():
    parser = argparse.ArgumentParser(description="Read Catch 채용공고 data and save it as JSON.")
    parser.add_argument("keyword", nargs="?", default="", help="Company or keyword to search, for example 삼성 or 네이버")
    parser.add_argument("--output", help="JSON output path. Defaults to catch_recruits_<keyword>_<timestamp>.json")
    parser.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS, help="Maximum recruits to save. Default: 30")
    parser.add_argument("--page-size", type=int, default=30, help="Catch API page size. Default: 30")
    parser.add_argument("--sort", type=int, default=1, help="Catch sort code. 1 is latest on the current site.")
    parser.add_argument("--watch", action="store_true", help="Keep reading on a regular interval.")
    parser.add_argument("--interval-minutes", type=float, default=DEFAULT_INTERVAL_MINUTES, help="Watch interval. Default: 60")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.watch and args.interval_minutes <= 0:
        raise CatchRecruitError("--interval-minutes must be greater than 0.")

    if not args.watch:
        run_once(args)
        return 0

    print(f"Watching Catch recruits every {args.interval_minutes:g} minute(s). Press Ctrl+C to stop.")
    while True:
        run_once(args)
        time.sleep(args.interval_minutes * 60)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCanceled")
        raise SystemExit(130)
    except CatchRecruitError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
