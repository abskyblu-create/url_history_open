"""Read URL values and spreadsheet hyperlink targets without opening browsers."""
import csv
import re
from pathlib import Path
from urllib.parse import urlsplit

URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)


def extract_urls(values):
    found = []
    seen = set()
    for value in values:
        for match in URL_PATTERN.finditer(str(value or "")):
            url = match.group().rstrip(".,;!)]}")
            if url.lower().startswith("www."):
                url = "https://" + url
            try:
                parsed = urlsplit(url)
                valid = parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname)
                parsed.port  # Reject malformed ports.
            except ValueError:
                valid = False
            if valid and url not in seen:
                seen.add(url)
                found.append(url)
    return found


def read_urls(filename):
    path = Path(filename)
    suffix = path.suffix.lower()
    values = []
    if suffix == ".csv":
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252")
        import io
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        for row in csv.reader(io.StringIO(text, newline=""), dialect):
            values.extend(row)
    elif suffix == ".xlsx":
        from openpyxl import load_workbook
        book = load_workbook(path, data_only=False)
        try:
            for sheet in book:
                for row in sheet:
                    for cell in row:
                        values.append(cell.value)
                        if cell.hyperlink:
                            values.append(cell.hyperlink.target)
        finally:
            book.close()
    elif suffix == ".xls":
        import xlrd
        book = xlrd.open_workbook(str(path), on_demand=True)
        try:
            for sheet in book.sheets():
                for row in range(sheet.nrows):
                    values.extend(sheet.row_values(row))
                for link in getattr(sheet, "hyperlink_list", []):
                    values.append(link.url_or_path)
        finally:
            book.release_resources()
    else:
        raise ValueError("Choose a .csv, .xlsx, or .xls file.")
    return extract_urls(values)


def batches(urls, size=20):
    return [urls[i:i + size] for i in range(0, len(urls), size)]
