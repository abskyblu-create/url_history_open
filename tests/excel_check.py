"""Optional integration test requiring installed Microsoft Excel."""
import tempfile
import unittest
from pathlib import Path

import win32com.client
import xlrd

from source_edit import delete_from_source


class LegacyExcelTests(unittest.TestCase):
    def test_legacy_workbook_deletion_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.xls'
            excel = win32com.client.DispatchEx('Excel.Application')
            book = None
            try:
                excel.Visible = False
                excel.DisplayAlerts = False
                book = excel.Workbooks.Add()
                sheet = book.Worksheets(1)
                sheet.Cells(1, 1).Value = 'https://example.com/a'
                sheet.Cells(1, 2).Value = 'Keep me'
                sheet.Hyperlinks.Add(Anchor=sheet.Cells(2, 1), Address='https://example.com/a', TextToDisplay='Label')
                sheet.Cells(2, 1).Value = 'Label'
                book.SaveAs(str(path), FileFormat=56)
            finally:
                if book is not None:
                    book.Close(SaveChanges=False)
                excel.Quit()
            changed, backup = delete_from_source(path, 'https://example.com/a')
            self.assertEqual(changed, 2)
            self.assertTrue(backup.exists())
            result = xlrd.open_workbook(str(path))
            try:
                self.assertEqual(result.sheet_by_index(0).cell_value(0, 0), '')
                self.assertEqual(result.sheet_by_index(0).cell_value(0, 1), 'Keep me')
                self.assertEqual(result.sheet_by_index(0).cell_value(1, 0), 'Label')
                self.assertFalse(result.sheet_by_index(0).hyperlink_list)
            finally:
                result.release_resources()


if __name__ == '__main__':
    unittest.main()
