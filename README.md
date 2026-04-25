OpenDART / Catch / News Reader
==============================

GUI app for downloading recent annual business report PDFs from OpenDART/DART, reading Catch recruit postings, and crawling company news metadata from Naver/Google.

Files
-----

- `opendart_gui.py`: Main GUI application.
- `download_business_reports.py`: OpenDART/DART and Naver Finance download logic with optional CLI.
- `crawl_company_news.py`: Naver/Google company news metadata crawler.
- `crawl_catch_recruits.py`: Catch recruit metadata crawler with one-shot and watch modes.
- `test_crawl_company_news.py`: Unit tests for the news crawler.
- `test_crawl_catch_recruits.py`: Unit tests for the Catch recruit crawler.
- `.env`: API key configuration file for OpenDART.
- `run_downloader.bat`: double-click GUI launcher for Windows.
- `run_downloader.ps1`: PowerShell GUI launcher.
- `run_catch_recruits.bat`: double-click launcher for command-line Catch recruit crawling.

Setup
-----

1. Install Python 3.10 or newer.
2. Open `.env`.
3. Put your OpenDART API key after the equals sign:

```text
OPENDART_API_KEY=YOUR_API_KEY_HERE
```

GUI
---

Double-click `run_downloader.bat` to open the app.

The app has three tabs:

- `Business Reports`: download annual business report PDFs through OpenDART.
- `Catch Recruits`: read Catch recruit postings once or start regular reading.
- `Company News`: crawl Naver News and Google News metadata over a date range and save JSON.

Business report and news tabs use the company search UX: type a company name or stock code, then select the exact company from the suggestions shown under the input box. Catch recruit search can also be left blank to read general recruit postings.

In `Business Reports`:

1. Choose `OpenDART business reports`.
2. Type a company name or stock code in `Company`.
3. Select the exact company from the suggestions shown under the input box.
4. Choose an output folder and report count.
5. Click `Download PDFs`.

For `Naver Finance research`, use the same company suggestion list, then set `Naver start date` and `Naver end date` as `YYYY-MM-DD` and choose how many `Research PDFs` to download.

In `Catch Recruits`:

1. Type a keyword/company name, or leave it blank to read general recruit postings.
2. Choose an output folder.
3. Set the recruit opening date range, or click `Today` / check `Today only`.
4. Set `Max results`.
5. Click `Read Once`, or set `Interval minutes` and click `Start Regular Reading`.
6. Click `Stop` to end regular reading.

Each Catch run saves a timestamped JSON file in the selected output folder and shows the latest results in the table.
Double-click a row in the table to open the Catch recruit posting in your browser.

In `Company News`:

1. Type a company name or stock code.
2. Select the exact company from the suggestions shown under the input box.
3. Choose `YYYY-MM-DD` start and end dates.
4. Select `all`, `naver`, or `google`.
5. Optionally choose a JSON output file.
6. Click `Crawl News JSON`.

Command Line
------------

OpenDART:

```powershell
python .\download_business_reports.py Samsung
```

Naver Finance research PDFs:

```powershell
python .\download_business_reports.py Samsung --source naver --count 3
```

With a date range:

```powershell
python .\download_business_reports.py 삼성전자 --source naver --count 10 --start-date 2026-04-01 --end-date 2026-04-30
```

Catch recruit postings:

```powershell
python .\crawl_catch_recruits.py Samsung --max-results 30
python .\crawl_catch_recruits.py Samsung --start-date 2026-04-25 --end-date 2026-04-25 --max-results 30
python .\crawl_catch_recruits.py Samsung --watch --interval-minutes 60 --max-results 30
```

On Windows, command-line Catch crawling can also be started with:

```powershell
.\run_catch_recruits.bat Samsung 30
```

Company news:

```powershell
python .\crawl_company_news.py Samsung --start-date 2026-01-01 --end-date 2026-04-25
```

Tests
-----

```powershell
python -m unittest test_crawl_company_news.py
python -m unittest test_crawl_catch_recruits.py
```
