"""Remove a reviewed URL from its source, with a backup and atomic replacement."""
import csv
import io
import os
from pathlib import Path
import shutil
import tempfile
from datetime import datetime

from urls import URL_PATTERN


def remove_url_text(value, url):
    if not isinstance(value, str):
        return value

    def replace(match):
        raw = match.group()
        candidate = raw.rstrip('.,;!)]}')
        normalized = 'https://' + candidate if candidate.lower().startswith('www.') else candidate
        return raw[len(candidate):] if normalized == url else raw

    return URL_PATTERN.sub(replace, value)


def edit_csv(path, target, url):
    raw = path.read_bytes()
    try:
        text = raw.decode('utf-8-sig')
        encoding = 'utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8'
    except UnicodeDecodeError:
        text = raw.decode('cp1252')
        encoding = 'cp1252'
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel
    newline = '\r\n' if '\r\n' in text else '\n'
    rows = list(csv.reader(io.StringIO(text, newline=''), dialect))
    changed = 0
    for row in rows:
        for index, value in enumerate(row):
            replacement = remove_url_text(value, url)
            if replacement != value:
                row[index] = replacement
                changed += 1
    if changed:
        with target.open('w', encoding=encoding, newline='') as stream:
            writer = csv.writer(stream, dialect, lineterminator=newline)
            writer.writerows(rows)
    return changed


def edit_xlsx(path, target, url):
    from openpyxl import load_workbook
    book = load_workbook(path, data_only=False)
    changed = 0
    try:
        for sheet in book:
            for row in sheet:
                for cell in row:
                    before = cell.value
                    after = remove_url_text(before, url)
                    hyperlink = bool(cell.hyperlink and cell.hyperlink.target == url)
                    if before != after or hyperlink:
                        # A changed formula cannot safely be kept with a missing URL.
                        cell.value = None if cell.data_type == 'f' or after == '' else after
                        if hyperlink:
                            cell.hyperlink = None
                        changed += 1
        if changed:
            book.save(target)
    finally:
        book.close()
    return changed


def edit_xls(path, target, url):
    """Use installed Excel to preserve the legacy workbook format."""
    try:
        import win32com.client
    except ImportError as exc:
        raise RuntimeError('Legacy .xls editing requires pywin32. Run setup.bat first, or save the file as .xlsx.') from exc
    excel = None
    book = None
    changed = 0
    try:
        excel = win32com.client.DispatchEx('Excel.Application')
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.AutomationSecurity = 3  # Disable macros in this automation instance.
        book = excel.Workbooks.Open(str(path.resolve()), UpdateLinks=0, ReadOnly=True)
        for sheet in book.Worksheets:
            for cell in sheet.UsedRange.Cells:
                before = cell.Formula if cell.HasFormula else cell.Value
                after = remove_url_text(before, url)
                hyperlink = any(link.Address == url for link in cell.Hyperlinks)
                if before != after or hyperlink:
                    if hyperlink:
                        cell.Hyperlinks.Delete()
                    if cell.HasFormula:
                        cell.ClearContents()
                    else:
                        cell.Value = None if after == '' else after
                    changed += 1
        if changed:
            book.SaveCopyAs(str(target.resolve()))
        return changed
    except Exception as exc:
        raise RuntimeError('Could not edit the .xls workbook. Microsoft Excel must be installed and the workbook editable. Close it in Excel and retry, or save as .xlsx. ' + str(exc)) from exc
    finally:
        if book is not None:
            book.Close(SaveChanges=False)
        if excel is not None:
            excel.Quit()


def delete_from_source(filename, url):
    path = Path(filename)
    editors = {'.csv': edit_csv, '.xlsx': edit_xlsx, '.xls': edit_xls}
    editor = editors.get(path.suffix.lower())
    if editor is None:
        raise ValueError('Unsupported source file type.')
    original = path.read_bytes()
    handle, name = tempfile.mkstemp(prefix='.' + path.stem + '-', suffix=path.suffix, dir=path.parent)
    os.close(handle)
    temporary = Path(name)
    try:
        changed = editor(path, temporary, url)
        if not changed:
            raise ValueError('This URL was not found in the source file. Reload the file and try again.')
        if path.read_bytes() != original:
            raise RuntimeError('The source file changed during deletion. Reload it and try again.')
        backup = path.with_name(path.name + '.' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.bak')
        shutil.copy2(path, backup)
        os.replace(temporary, path)
        return changed, backup
    finally:
        temporary.unlink(missing_ok=True)
