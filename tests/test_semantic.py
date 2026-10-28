import tempfile
import unittest
from unittest.mock import Mock, patch

from review import make_item, PageInfo
from semantic import SemanticSearch, expand_query, OllamaModel


class SemanticTests(unittest.TestCase):
    def test_gemma_query_and_local_embeddings(self):
        with patch('semantic.ollama_request') as request:
            request.return_value = {'response': '{"query":"beginner programming tutorials"}'}
            self.assertIn('programming tutorials', OllamaModel().expand('learning to code'))
            self.assertEqual(request.call_args.args[0], 'generate')
            self.assertEqual(request.call_args.args[1]['model'], 'gemma3:4b')
            request.return_value = {'embeddings': [[0.1, 0.2]]}
            self.assertEqual(list(OllamaModel().embed(['test'])), [[0.1, 0.2]])
            self.assertEqual(request.call_args.args[1]['model'], 'qwen3-embedding:0.6b')

    def test_custom_adapter_query_normalization(self):
        self.assertEqual(expand_query('  programming tutorials  '), 'programming tutorials')
        self.assertEqual(expand_query('Python'), 'Python')

    def test_ranking_threshold_deletion_and_reused_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            def embed(texts, **kwargs):
                for text in texts:
                    yield [1., 0.] if 'residence' in text else [0., 1.]
            model = Mock()
            model.embed.side_effect = embed
            engine = SemanticSearch(directory, model)
            items = [make_item('https://example.com/residence'), make_item('https://example.com/cake'), make_item('https://example.com/residence-deleted')]
            items[2]['deleted'] = True
            self.assertEqual(list(engine.search(items, 'residence')), [0])
            calls = model.embed.call_count
            self.assertEqual(list(engine.search(items, 'residence')), [0])
            self.assertEqual(model.embed.call_count, calls)
            items[1].update(title='residence', page_text='residence application')
            self.assertEqual(set(engine.search(items, 'residence')), {0, 1})
            self.assertGreater(model.embed.call_count, calls)

    def test_page_text_excludes_scripts_and_styles(self):
        parser = PageInfo()
        parser.feed('<title>Residence</title><style>ignore-css</style><script>ignore-js</script><p>Apply for a residence permit.</p>')
        text = ' '.join(parser.text)
        self.assertIn('residence permit', text)
        self.assertNotIn('ignore-css', text)
        self.assertNotIn('ignore-js', text)


if __name__ == '__main__':
    unittest.main()
