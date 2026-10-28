"""Real-model integration check requiring local Ollama and installed models."""
import unittest
from review import make_item
from semantic import SemanticSearch


class RealSemanticTests(unittest.TestCase):
    def test_general_meanings_in_english_and_french(self):
        texts = [
            ('Renewable energy research', 'Scientific publications about solar panels, wind turbines and sustainable electricity generation.'),
            ('Web development foundations', 'Beginner lessons in HTML, CSS and JavaScript for building websites.'),
            ('Chocolate cake', 'Mix flour, eggs and chocolate, then bake the dessert.'),
            ('Apprendre Python', 'Un cours de programmation Python pour les debutants.'),
        ]
        items = []
        for i, (title, description) in enumerate(texts):
            item = make_item(f'https://example.com/page-{i}')
            item.update(title=title, description=description, preview='Fetched')
            items.append(item)
        engine = SemanticSearch()
        for query, expected in [('clean electricity generation', 0), ('learn to build websites', 1), ('cours de programmation pour debutants', 3)]:
            matches = engine.search(items, query, progress=lambda message: print(message, flush=True))
            print(query, matches, flush=True)
            self.assertTrue(matches)
            self.assertEqual(next(iter(matches)), expected)
            # Approximate search can include weak matches above the display cutoff.
            self.assertLess(matches.get(2, -1), matches[expected] - 0.1)


if __name__ == '__main__':
    unittest.main()
