OpenDART / Naver Finance PDF Downloader
=======================================

GUI app for downloading recent annual business report PDFs from OpenDART/DART, plus command-line tools for Naver Finance research PDFs and company news metadata.

Files
-----

- `opendart_gui.py`: OpenDART GUI application.
- `download_business_reports.py`: OpenDART/DART and Naver Finance download logic with optional CLI.
- `crawl_company_news.py`: Naver/Google company news metadata crawler.
- `crawl_catch_recruits.py`: Catch 채용공고 metadata crawler with one-shot and watch modes.
- `test_crawl_company_news.py`: Unit tests for the news crawler.
- `test_crawl_catch_recruits.py`: Unit tests for the Catch recruit crawler.
- `.env`: API key configuration file for OpenDART.
- `run_downloader.bat`: double-click launcher for Windows.
- `run_downloader.ps1`: PowerShell launcher.
- `run_catch_recruits.bat`: double-click launcher for regular Catch recruit crawling.

Setup
-----

1. Install Python 3.10 or newer.
2. Open `.env`.
3. Put your OpenDART API key after the equals sign:

```text
OPENDART_API_KEY=YOUR_API_KEY_HERE
```

Run
---

Double-click `run_downloader.bat` to open the OpenDART GUI.

In the app:

1. Enter a company name, for example `Samsung Electronics` or `삼성전자`.
2. Confirm the API key field is filled from `.env`.
3. Choose the output folder.
4. Click `Download PDFs`.

Command-line mode is still available for OpenDART:

```powershell
python .\download_business_reports.py 삼성전자
```

Naver Finance research PDFs can be downloaded from the command line without an OpenDART API key:

```powershell
python .\download_business_reports.py 삼성전자 --source naver --count 3
```

Naver mode searches the Npay 증권 종목분석 리포트 page and saves matching PDF files to `downloads` by default. Use `--output` to choose another folder.

Company News Crawler
--------------------

Collect Naver News and Google News metadata for a company over a date range and save it as JSON:

```powershell
python .\crawl_company_news.py 삼성전자 --start-date 2026-01-01 --end-date 2026-04-25
```

Useful options:

```powershell
python .\crawl_company_news.py 삼성전자 --start-date 2026-01-01 --end-date 2026-04-25 --source google --max-results 5 --output news_results.json
```

The JSON includes `company`, `start_date`, `end_date`, `generated_at`, `sources`, and `items`. Each item contains `source`, `title`, `publisher`, `published_at`, `link`, and `summary`.

Run tests:

```powershell
python -m unittest test_crawl_company_news.py
```

Catch Recruit Crawler
---------------------

Collect 채용공고 metadata from Catch and save it as JSON:

```powershell
python .\crawl_catch_recruits.py 삼성 --max-results 30
```

Run it regularly in the foreground:

```powershell
python .\crawl_catch_recruits.py 삼성 --watch --interval-minutes 60 --max-results 30
```

On Windows, you can also double-click `run_catch_recruits.bat`. By default it searches `삼성` every 60 minutes. From PowerShell, pass a keyword and interval like this:

```powershell
.\run_catch_recruits.bat 네이버 30
```

The JSON includes `source`, `keyword`, `generated_at`, `total_count`, and `items`. Each item contains normalized fields such as `company`, `title`, `deadline`, `career`, `education`, `location`, `employment_type`, `link`, plus the original `raw` Catch API row.

Run Catch crawler tests:

```powershell
python -m unittest test_crawl_catch_recruits.py
```
