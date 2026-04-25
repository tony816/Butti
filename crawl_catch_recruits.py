import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
CATCH_RECRUIT_API = "https://www.catch.co.kr/api/v1.0/recruit/information/getRecruitList"
DEFAULT_MAX_RESULTS = 3000


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


def parse_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError as exc:
        raise CatchRecruitError(f"Invalid date '{value}'. Use YYYY-MM-DD.") from exc


def parse_recruit_date(value):
    value = clean_text(value)
    if not value:
        return None
    for candidate in (value[:10], value):
        try:
            return datetime.strptime(candidate, "%Y-%m-%d").date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def validate_date_range(start_date, end_date):
    if start_date and end_date and end_date < start_date:
        raise CatchRecruitError("End date must be the same as or later than start date.")


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


def is_within_date_range(item, start_date=None, end_date=None):
    recruit_date = parse_recruit_date(item.get("start_date", ""))
    if not recruit_date:
        return True
    if start_date and recruit_date < start_date:
        return False
    if end_date and recruit_date > end_date:
        return False
    return True


def title_contains_keyword(item, keyword):
    keyword = clean_text(keyword).casefold()
    if not keyword:
        return True
    return keyword in clean_text(item.get("title", "")).casefold()


def crawl_catch_recruits(
    keyword="",
    max_results=DEFAULT_MAX_RESULTS,
    page_size=30,
    sort=1,
    start_date=None,
    end_date=None,
    fetch=request_json,
    progress=None,
):
    keyword = keyword.strip()
    if max_results < 1:
        raise CatchRecruitError("max_results must be 1 or greater.")
    if page_size < 1:
        raise CatchRecruitError("page_size must be 1 or greater.")
    start_date = parse_date(start_date) if start_date else None
    end_date = parse_date(end_date) if end_date else None
    validate_date_range(start_date, end_date)

    items = []
    total_count = 0
    page = 1
    while len(items) < max_results:
        if progress:
            progress(f"Reading Catch recruit page {page}...")
        request_page_size = min(page_size, max_results)
        params = build_recruit_params(keyword, page, request_page_size, sort)
        payload = fetch(CATCH_RECRUIT_API, params=params)
        rows = get_recruit_rows(payload)
        total_count = total_count or get_total_count(payload)
        if not rows:
            break
        normalized_rows = [normalize_recruit(row) for row in rows]
        items.extend(
            item
            for item in normalized_rows
            if title_contains_keyword(item, keyword) and is_within_date_range(item, start_date, end_date)
        )
        if len(rows) < request_page_size:
            break
        if start_date and normalized_rows:
            row_dates = [parse_recruit_date(item.get("start_date", "")) for item in normalized_rows]
            dated_rows = [row_date for row_date in row_dates if row_date]
            if dated_rows and max(dated_rows) < start_date:
                break
        page += 1
        time.sleep(0.5)

    items = deduplicate_recruits(items)[:max_results]
    return {
        "source": "catch",
        "keyword": keyword,
        "start_date": start_date.isoformat() if start_date else "",
        "end_date": end_date.isoformat() if end_date else "",
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
        start_date=args.start_date,
        end_date=args.end_date,
        progress=print,
    )
    output_path = Path(args.output) if args.output else default_output_path(args.keyword or "all")
    write_json(result, output_path)
    print(f"Done: {len(result['items'])} recruit item(s) saved.")
    print(f"Output file: {output_path.resolve()}")
    return result


def parse_args():
    parser = argparse.ArgumentParser(description="Read Catch recruit data and save it as JSON.")
    parser.add_argument("keyword", nargs="?", default="", help="Title keyword to search. Leave blank for all postings.")
    parser.add_argument("--output", help="JSON output path. Defaults to catch_recruits_<keyword>_<timestamp>.json")
    parser.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS, help="Maximum recruits to save. Default: 3000")
    parser.add_argument("--page-size", type=int, default=30, help="Catch API page size. Default: 30")
    parser.add_argument("--sort", type=int, default=1, help="Catch sort code. 1 is latest on the current site.")
    parser.add_argument("--start-date", help="Only include postings opened on or after this date, YYYY-MM-DD.")
    parser.add_argument("--end-date", help="Only include postings opened on or before this date, YYYY-MM-DD.")
    return parser.parse_args()


def main():
    args = parse_args()
    run_once(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCanceled")
        raise SystemExit(130)
    except CatchRecruitError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
