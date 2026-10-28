import tempfile
import unittest
from pathlib import Path

from urls import batches, extract_urls, read_urls


class UrlTests(unittest.TestCase):
    def test_extract_and_deduplicate(self):
        self.assertEqual(extract_urls(["See https://example.com and www.python.org.", "https://example.com", "file:///C:/secret", None]), ["https://example.com", "https://www.python.org"])

    def test_batches(self):
        groups = batches(list(range(45)))
        self.assertEqual([len(group) for group in groups], [20, 20, 5])
        self.assertEqual(batches([]), [])

    def test_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "urls.csv"
            path.write_text('name;url\nExample;"https://example.com"\n', encoding="utf-8-sig")
            self.assertEqual(read_urls(path), ["https://example.com"])

    def test_excel_cells_and_hyperlinks(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "urls.xlsx"
            book = Workbook()
            book.active["A1"] = "https://example.com"
            sheet = book.create_sheet("More")
            sheet["A1"] = "Python"
            sheet["A1"].hyperlink = "https://www.python.org"
            book.save(path)
            book.close()
            self.assertEqual(read_urls(path), ["https://example.com", "https://www.python.org"])


if __name__ == "__main__":
    unittest.main()
