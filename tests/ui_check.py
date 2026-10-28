import tempfile
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from app import App
from review import Review


class InterfaceTests(unittest.TestCase):
    def test_semantic_ranking_clear_and_stale_results(self):
        root = tk.Tk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as directory:
                app = App(root)
                app.review = Review('source.csv', ['https://example.com/a', 'https://example.com/b'], directory)
                app.search.set('programming tutorials')
                app.semantic_results.put(('done', app.search_version, {1: 0.8, 0: 0.4}))
                app.poll()
                self.assertEqual(app.visible(), [1, 0])
                self.assertIn('Semantic similarity', app.detail.get('1.0', 'end'))
                previous = app.search_version
                app.search.set('unrelated')
                app.semantic_results.put(('done', previous, {1: 0.9}))
                app.poll()
                self.assertIsNone(app.semantic_matches)
                self.assertEqual(app.visible(), [])
                app.clear_search()
                self.assertEqual(app.visible(), [0, 1])
                root.update()
        finally:
            for callback in root.tk.call('after', 'info'):
                root.after_cancel(callback)
            root.destroy()

    def test_word_search_across_groups_and_clear(self):
        root = tk.Tk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as directory:
                app = App(root)
                urls = ['https://coursera.org/learn/python', 'https://example.com/data%20science', 'https://example.org/other']
                app.review = Review('source.csv', urls, directory)
                app.review.items[2]['description'] = 'Advanced Python lessons'
                app.refresh()
                app.filters['site'][0].set('coursera.org')
                app.search.set('PYTHON')
                app.perform_search()
                self.assertEqual(app.visible(), [0, 2])
                self.assertTrue(all(variable.get() == 'All' for variable, _ in app.filters.values()))
                app.search.set('science data')
                app.perform_search()
                self.assertEqual(app.visible(), [1])
                app.search.set('no-matching-word')
                app.perform_search()
                self.assertEqual(app.visible(), [])
                app.clear_search()
                self.assertEqual(app.visible(), [0, 1, 2])
                root.update()
        finally:
            for callback in root.tk.call('after', 'info'):
                root.after_cancel(callback)
            root.destroy()

    def test_right_click_delete_persists_and_handles_pending_preview(self):
        root = tk.Tk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as directory:
                app = App(root)
                urls = ['https://example.com/a', 'https://example.com/b']
                source = __import__('pathlib').Path(directory) / 'source.csv'
                source.write_text('\n'.join(urls), encoding='utf-8')
                app.review = Review(source, urls, directory)
                app.refresh()
                app.table.selection_set(('0', '1'))
                with patch.object(app.table, 'identify_row', return_value='0'), patch.object(app.link_menu, 'tk_popup'), patch.object(app.link_menu, 'grab_release'):
                    app.show_link_menu(SimpleNamespace(y=30, x_root=100, y_root=100))
                app.link_menu.invoke(1)
                self.assertEqual(app.visible(), [1])
                app.results.put((0, 'Old preview', 'Description', None))
                app.poll()
                self.assertEqual(app.visible(), [1])
                restored = Review(source, urls, directory)
                self.assertTrue(restored.items[0]['deleted'])
                self.assertFalse(restored.items[1]['deleted'])
                self.assertNotIn(urls[0], source.read_text())
                self.assertIn(urls[1], source.read_text())
                root.update()
        finally:
            for callback in root.tk.call('after', 'info'):
                root.after_cancel(callback)
            root.destroy()

    def test_right_click_opens_only_clicked_link_without_changing_decisions(self):
        root = tk.Tk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as directory:
                app = App(root)
                app.review = Review('source.csv', ['https://example.com/a', 'https://example.com/b'], directory)
                app.refresh()
                app.table.selection_set(('0', '1'))
                with patch.object(app.table, 'identify_row', return_value='1'), patch.object(app.link_menu, 'tk_popup'), patch.object(app.link_menu, 'grab_release'):
                    app.show_link_menu(SimpleNamespace(y=30, x_root=100, y_root=100))
                self.assertEqual(app.selected(), [1])
                with patch('app.find_edge', return_value='edge.exe'), patch('app.subprocess.Popen') as launch:
                    app.link_menu.invoke(0)
                    self.assertEqual(launch.call_args.args[0], ['edge.exe', '--new-window', 'https://example.com/b'])
                self.assertTrue(all(item['status'] == 'Unreviewed' for item in app.review.items))
                root.update()
        finally:
            for callback in root.tk.call('after', 'info'):
                root.after_cancel(callback)
            root.destroy()

    def test_only_kept_filtered_batch_is_opened_and_saved(self):
        root = tk.Tk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as directory:
                app = App(root)
                urls = [f'https://coursera.org/learn/course-{i}' for i in range(24)] + ['https://udemy.com/course/python']
                app.review = Review('source.csv', urls, directory)
                for item in app.review.items:
                    item['status'] = 'Keep'
                app.review.items[0]['status'] = 'Skip'
                app.review.items[1]['status'] = 'Later'
                app.filters['site'][0].set('coursera.org')
                app.refresh()
                with patch('app.find_edge', return_value='edge.exe'), patch('app.subprocess.Popen') as launch:
                    app.open_kept()
                    command = launch.call_args.args[0]
                    self.assertEqual(len(command[2:]), 20)
                    self.assertNotIn(urls[0], command)
                    self.assertNotIn(urls[1], command)
                    self.assertNotIn(urls[-1], command)
                    self.assertEqual(sum(i['status'] == 'Opened' for i in app.review.items), 20)
                    app.open_kept()
                    self.assertEqual(len(launch.call_args.args[0][2:]), 2)
                restored = Review('source.csv', urls, directory)
                self.assertEqual(restored.items[2]['status'], 'Opened')
                self.assertEqual(restored.items[-1]['status'], 'Keep')
                root.update()
        finally:
            for callback in root.tk.call('after', 'info'):
                root.after_cancel(callback)
            root.destroy()


if __name__ == '__main__':
    unittest.main()
