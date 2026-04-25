import argparse
import html
from html.parser import HTMLParser
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree


OPENDART_BASE = "https://opendart.fss.or.kr/api"
DART_BASE = "https://dart.fss.or.kr"
NAVER_RESEARCH_BASE = "https://finance.naver.com/research"
APP_DIR = Path(__file__).resolve().parent
ENV_PATH = APP_DIR / ".env"
CORP_CODE_CACHE = APP_DIR / "corpCode.xml"
DEFAULT_OUTPUT_DIR = APP_DIR / "downloads"
DEFAULT_HEADERS = {"User-Agent": "Mozilla/5.0"}


class DartError(Exception):
    pass


class NaverResearchListParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_row = False
        self.in_cell = False
        self.current_cell = None
        self.current_text = []
        self.current_report = None
        self.reports = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.in_row = True
            self.current_report = {
                "stock_name": "",
                "title": "",
                "broker": "",
                "date": "",
                "pdf_url": "",
            }
            self.current_cell = 0
        elif self.in_row and tag == "td":
            self.in_cell = True
            self.current_text = []
        elif self.in_row and tag == "a":
            href = attrs.get("href", "")
            if href.endswith(".pdf") or ".pdf" in href:
                self.current_report["pdf_url"] = urllib.parse.urljoin(NAVER_RESEARCH_BASE + "/", href)

    def handle_data(self, data):
        if self.in_cell:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if self.in_row and tag == "td":
            text = normalize_spaces("".join(self.current_text))
            if self.current_cell == 0:
                self.current_report["stock_name"] = text
            elif self.current_cell == 1:
                self.current_report["title"] = text
            elif self.current_cell == 2:
                self.current_report["broker"] = text
            elif self.current_cell == 4:
                self.current_report["date"] = text
            self.current_cell += 1
            self.in_cell = False
            self.current_text = []
        elif self.in_row and tag == "tr":
            if self.current_report and self.current_report.get("pdf_url"):
                self.reports.append(self.current_report)
            self.in_row = False
            self.in_cell = False
            self.current_cell = None
            self.current_report = None


def load_env_file(path=ENV_PATH):
    values = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
        os.environ.setdefault(key, value)
    return values


def get_configured_api_key():
    load_env_file()
    return os.environ.get("OPENDART_API_KEY", "").strip()


def request_bytes(url, params=None, headers=None, data=None):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers or DEFAULT_HEADERS,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.read(), response.headers
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise DartError(f"HTTP {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise DartError(f"Network error: {exc.reason}") from exc


def request_json(url, params):
    body, _ = request_bytes(url, params=params)
    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise DartError(f"Invalid JSON response: {body[:300]!r}") from exc


def post_bytes(url, data, headers=None):
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    merged_headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    if headers:
        merged_headers.update(headers)
    return request_bytes(url, headers=merged_headers, data=encoded)


def ensure_corp_code_xml(api_key, cache_path=CORP_CODE_CACHE, progress=None):
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path

    if progress:
        progress("Downloading company code list. This can take a moment on first run.")
    body, _ = request_bytes(f"{OPENDART_BASE}/corpCode.xml", {"crtfc_key": api_key})

    tmp_zip = cache_path.with_suffix(".zip")
    tmp_zip.write_bytes(body)
    try:
        with zipfile.ZipFile(tmp_zip) as zf:
            xml_names = [name for name in zf.namelist() if name.lower().endswith(".xml")]
            if not xml_names:
                raise DartError("No XML file found inside corpCode.zip.")
            cache_path.write_bytes(zf.read(xml_names[0]))
    except zipfile.BadZipFile as exc:
        message = body.decode("utf-8", errors="replace")[:500]
        raise DartError(f"Could not open company code ZIP response: {message}") from exc
    finally:
        tmp_zip.unlink(missing_ok=True)

    return cache_path


def normalize_name(value):
    return re.sub(r"\s+", "", value or "").casefold()


def normalize_spaces(value):
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def find_corp(api_key, company_name, progress=None):
    xml_path = ensure_corp_code_xml(api_key, progress=progress)
    wanted = normalize_name(company_name)
    root = ElementTree.parse(xml_path).getroot()

    exact = []
    partial = []
    for item in root.findall("list"):
        corp_name = item.findtext("corp_name", default="")
        corp_code = item.findtext("corp_code", default="")
        stock_code = item.findtext("stock_code", default="").strip()
        row = {"corp_name": corp_name, "corp_code": corp_code, "stock_code": stock_code}
        normalized = normalize_name(corp_name)
        if normalized == wanted:
            exact.append(row)
        elif wanted and wanted in normalized:
            partial.append(row)

    candidates = exact or partial
    if not candidates:
        raise DartError(f"Company not found: {company_name}")

    listed = [corp for corp in candidates if corp["stock_code"]]
    return (listed or candidates)[0], candidates[:10]


def get_recent_business_reports(api_key, corp_code, years=5):
    current_year = date.today().year
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bgn_de": f"{current_year - years - 2}0101",
        "end_de": f"{current_year}1231",
        "last_reprt_at": "Y",
        "pblntf_ty": "A",
        "pblntf_detail_ty": "a001",
        "sort": "date",
        "sort_mth": "desc",
        "page_no": "1",
        "page_count": "100",
    }
    data = request_json(f"{OPENDART_BASE}/list.json", params)
    status = data.get("status")
    if status != "000":
        raise DartError(f"Disclosure search failed [{status}]: {data.get('message', 'unknown error')}")

    reports = []
    seen_years = set()
    for item in data.get("list", []):
        report_name = item.get("report_nm", "")
        match = re.search(r"\((\d{4})\.\d{2}\)", report_name)
        business_year = match.group(1) if match else item.get("rcept_dt", "")[:4]
        if business_year in seen_years:
            continue
        seen_years.add(business_year)
        reports.append(
            {
                "corp_name": item.get("corp_name", ""),
                "report_nm": report_name,
                "rcept_no": item.get("rcept_no", ""),
                "rcept_dt": item.get("rcept_dt", ""),
                "business_year": business_year,
            }
        )
        if len(reports) >= years:
            break

    if not reports:
        raise DartError("No recent annual business reports were found.")
    return reports


def extract_document_number(rcp_no):
    html_bytes, _ = request_bytes(f"{DART_BASE}/dsaf001/main.do", {"rcpNo": rcp_no})
    html = html_bytes.decode("utf-8", errors="replace")

    patterns = [
        r"openPdfDownload\(['\"]\d+['\"],\s*['\"](\d+)['\"]\)",
        r"pdfDownload\(['\"]\d+['\"],\s*['\"](\d+)['\"]\)",
        r"\[['\"]dcmNo['\"]\]\s*=\s*['\"](\d+)['\"]",
        r"dcmNo\s*[=:]\s*['\"]?(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)

    matches = re.findall(r"['\"]dcmNo['\"]\s*:\s*['\"](\d+)['\"]", html)
    if matches:
        return matches[0]

    raise DartError(f"Could not find PDF document number for receipt {rcp_no}.")


def safe_filename(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:160] or "report"


def unique_output_path(output_dir, filename):
    output_path = output_dir / filename
    if not output_path.exists():
        return output_path

    stem = output_path.stem
    suffix = output_path.suffix
    for index in range(2, 1000):
        candidate = output_dir / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise DartError(f"Could not create a unique file name for {filename}")


def download_pdf(report, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rcp_no = report["rcept_no"]
    dcm_no = extract_document_number(rcp_no)
    body, headers = post_bytes(
        f"{DART_BASE}/pdf/download/pdf.do",
        {"rcp_no": rcp_no, "dcm_no": dcm_no},
        headers={"Referer": f"{DART_BASE}/pdf/download/main.do?rcp_no={rcp_no}&dcm_no={dcm_no}"},
    )

    content_type = headers.get("Content-Type", "")
    if not body.startswith(b"%PDF"):
        preview = body[:300].decode("utf-8", errors="replace")
        raise DartError(f"Response is not a PDF. Content-Type={content_type}, body={preview}")

    filename = safe_filename(
        f"{report['business_year']}_{report['corp_name']}_{report['report_nm']}_{rcp_no}.pdf"
    )
    output_path = unique_output_path(output_dir, filename)
    output_path.write_bytes(body)
    return output_path


def encode_naver_keyword(keyword):
    return urllib.parse.quote_from_bytes(keyword.encode("cp949"))


def get_naver_research_page(company, page):
    keyword = encode_naver_keyword(company)
    url = f"{NAVER_RESEARCH_BASE}/company_list.naver?keyword={keyword}&page={page}"
    body, _ = request_bytes(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Python Naver Research Downloader",
            "Referer": f"{NAVER_RESEARCH_BASE}/company_list.naver",
        },
    )
    return body.decode("euc-kr", errors="replace")


def parse_naver_research_reports(page_html):
    parser = NaverResearchListParser()
    parser.feed(page_html)
    return parser.reports


def get_naver_research_reports(company, count=10, max_pages=20, progress=None):
    reports = []
    seen_urls = set()
    wanted = normalize_name(company)
    for page in range(1, max_pages + 1):
        if progress:
            progress(f"Searching Naver Finance research page {page} for {company}")
        page_reports = parse_naver_research_reports(get_naver_research_page(company, page))
        if not page_reports:
            break

        for report in page_reports:
            if wanted not in normalize_name(report["stock_name"]):
                continue
            pdf_url = report["pdf_url"]
            if pdf_url in seen_urls:
                continue
            seen_urls.add(pdf_url)
            reports.append(report)
            if len(reports) >= count:
                return reports

    if not reports:
        raise DartError(f"No Naver Finance research PDFs found for: {company}")
    return reports


def download_naver_research_pdf(report, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    body, headers = request_bytes(
        report["pdf_url"],
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Python Naver Research Downloader",
            "Referer": f"{NAVER_RESEARCH_BASE}/company_list.naver",
        },
    )

    content_type = headers.get("Content-Type", "")
    if not body.startswith(b"%PDF"):
        preview = body[:300].decode("utf-8", errors="replace")
        raise DartError(f"Response is not a PDF. Content-Type={content_type}, body={preview}")

    filename = safe_filename(
        f"네이버리서치_{report['date']}_{report['stock_name']}_{report['broker']}_{report['title']}.pdf"
    )
    output_path = unique_output_path(output_dir, filename)
    output_path.write_bytes(body)
    return output_path


def download_naver_research_reports(company, count=10, output_dir=DEFAULT_OUTPUT_DIR, progress=None):
    company = company.strip()
    if not company:
        raise DartError("Company name is empty.")
    if count < 1:
        raise DartError("Count must be 1 or greater.")

    def tell(message):
        if progress:
            progress(message)

    reports = get_naver_research_reports(company, count=count, progress=tell)
    tell(f"Found {len(reports)} Naver Finance research report(s).")

    downloaded = []
    failed = []
    for index, report in enumerate(reports, start=1):
        tell(f"[{index}/{len(reports)}] Downloading {report['stock_name']} - {report['title']} ({report['date']})")
        try:
            path = download_naver_research_pdf(report, output_dir)
            downloaded.append(path)
            tell(f"Saved: {path}")
        except DartError as exc:
            failed.append((report, str(exc)))
            tell(f"Failed: {report['pdf_url']} - {exc}")

    return {"company": company, "reports": reports, "downloaded": downloaded, "failed": failed}


def download_business_reports(company, api_key=None, years=5, output_dir=DEFAULT_OUTPUT_DIR, progress=None):
    api_key = (api_key or get_configured_api_key()).strip()
    if not api_key:
        raise DartError("OpenDART API key is empty. Put it in .env as OPENDART_API_KEY=your_key.")
    if not company.strip():
        raise DartError("Company name is empty.")

    def tell(message):
        if progress:
            progress(message)

    corp, candidates = find_corp(api_key, company.strip(), progress=tell)
    tell(f"Selected company: {corp['corp_name']} / corp_code={corp['corp_code']} / stock={corp['stock_code'] or '-'}")

    reports = get_recent_business_reports(api_key, corp["corp_code"], years=years)
    tell(f"Found {len(reports)} annual business report(s).")

    downloaded = []
    failed = []
    for index, report in enumerate(reports, start=1):
        tell(f"[{index}/{len(reports)}] Downloading {report['report_nm']} ({report['rcept_dt']})")
        try:
            path = download_pdf(report, output_dir)
            downloaded.append(path)
            tell(f"Saved: {path}")
        except DartError as exc:
            failed.append((report, str(exc)))
            tell(f"Failed: {report['rcept_no']} - {exc}")

    return {"corp": corp, "candidates": candidates, "reports": reports, "downloaded": downloaded, "failed": failed}


def read_api_key(args):
    if args.source == "naver":
        return None
    if args.api_key:
        return args.api_key.strip()
    configured = get_configured_api_key()
    if configured:
        return configured
    return input("OpenDART API key: ").strip()


def parse_args():
    parser = argparse.ArgumentParser(description="Download OpenDART business reports or Naver Finance research PDFs.")
    parser.add_argument("company", nargs="?", help="Company name, for example Samsung Electronics")
    parser.add_argument("--source", choices=("dart", "naver"), default="dart", help="Download source. Default: dart")
    parser.add_argument("--api-key", help="OpenDART API key. Defaults to OPENDART_API_KEY from .env or environment.")
    parser.add_argument("--years", type=int, default=5, help="Number of annual reports to download. Default: 5")
    parser.add_argument("--count", type=int, default=10, help="Number of Naver research PDFs to download. Default: 10")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR), help="PDF output directory. Default: downloads")
    return parser.parse_args()


def main():
    args = parse_args()
    company = args.company or input("Company name: ").strip()
    if args.source == "naver":
        result = download_naver_research_reports(
            company=company,
            count=args.count,
            output_dir=Path(args.output),
            progress=print,
        )
    else:
        api_key = read_api_key(args)
        result = download_business_reports(
            company=company,
            api_key=api_key,
            years=args.years,
            output_dir=Path(args.output),
            progress=print,
        )
    print()
    print(f"Done: {len(result['downloaded'])} PDF file(s) saved.")
    print(f"Output folder: {Path(args.output).resolve()}")
    return 0 if result["downloaded"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCanceled")
        raise SystemExit(130)
    except DartError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
