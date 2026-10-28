import tempfile
import unittest
from unittest.mock import patch
from review import Review, PageInfo, classify, fetch_preview, specific_category


class ReviewTests(unittest.TestCase):
    def test_specific_topics_and_resource_types(self):
        self.assertEqual(specific_category('https://coursera.org/learn/python'), 'Online courses / Python / Courses')
        self.assertEqual(specific_category('https://coursera.org/specializations/machine-learning'), 'Online courses / Machine learning / Specializations')
        self.assertEqual(specific_category('https://github.com/user/python-repo/issues/1'), 'Developer resources / Python / Issues')
        self.assertIn('Deep learning', specific_category('https://udemy.com/course/abc', 'Deep learning with Python'))
        self.assertEqual(specific_category('https://example.com/unknown'), 'Other websites / example.com')

    def test_old_automatic_group_is_upgraded(self):
        with tempfile.TemporaryDirectory() as directory:
            review = Review('source.csv', ['https://coursera.org/learn/python'], directory)
            review.items[0]['category'] = 'Online courses'
            review.items[0].pop('custom_category')
            review.items[0]['status'] = 'Later'
            review.save()
            restored = Review('source.csv', ['https://coursera.org/learn/python'], directory)
            self.assertEqual(restored.items[0]['category'], 'Online courses / Python / Courses')
            self.assertEqual(restored.items[0]['status'], 'Later')

    def test_provider_groups_and_domain_boundary(self):
        self.assertEqual(classify('https://www.coursera.org/learn/python'), ('coursera.org', 'Online courses'))
        self.assertEqual(classify('https://udemy.com/course/python')[1], 'Online courses')
        self.assertEqual(classify('https://coursera.org.evil.example/path')[1], 'Other')
        self.assertEqual(classify('https://linkedin.com/learning/python')[1], 'Online courses')

    def test_restore_preserves_decisions_and_custom_categories(self):
        with tempfile.TemporaryDirectory() as directory:
            urls = ['https://coursera.org/learn/python', 'https://example.com']
            review = Review('source.csv', urls, directory)
            review.items[0].update(status='Keep', category='Study Python')
            review.items[0].pop('custom_category')  # Legacy saved custom topic, before the explicit flag.
            review.save()
            restored = Review('source.csv', [*urls, 'https://udemy.com'], directory)
            self.assertEqual(restored.items[0]['status'], 'Keep')
            self.assertEqual(restored.items[0]['category'], 'Study Python')
            self.assertEqual(restored.items[2]['status'], 'Unreviewed')
            self.assertEqual(len(restored.items), 3)

    def test_bad_saved_file_is_recoverable(self):
        with tempfile.TemporaryDirectory() as directory:
            review = Review('source.csv', ['https://example.com'], directory)
            review.path.parent.mkdir(exist_ok=True)
            review.path.write_text('invalid json')
            restored = Review('source.csv', ['https://example.com'], directory)
            self.assertTrue(restored.warning)
            self.assertEqual(restored.items[0]['status'], 'Unreviewed')

    def test_page_information(self):
        parser = PageInfo()
        parser.feed('<title>Python &amp; Data</title><meta name="description" content="Learn Python"><script>ignored()</script>')
        self.assertEqual(parser.title, 'Python & Data')
        self.assertEqual(parser.description, 'Learn Python')

    def test_fetch_is_bounded_and_uses_metadata(self):
        with patch('review.urlopen') as opener:
            response = opener.return_value.__enter__.return_value
            response.headers.get_content_type.return_value = 'text/html'
            response.headers.get_content_charset.return_value = 'utf-8'
            response.read.return_value = b'<title>Course</title><meta property="og:description" content="Learn skills">'
            self.assertEqual(fetch_preview('https://example.com'), ('Course', 'Learn skills'))
            response.read.assert_called_once_with(512 * 1024)


if __name__ == '__main__':
    unittest.main()
