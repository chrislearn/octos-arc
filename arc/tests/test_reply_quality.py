import unittest

from codegen import parse_edit_blocks
from reply_quality import prune_degenerate_edits, reply_quality


def edit(old, new, path='frontend/src/a.js'):
    return f'<<<EDIT {path}>>>\n<<<SEARCH>>>\n{old}\n<<<REPLACE>>>\n{new}\n<<<END EDIT>>>\n'


class ReplyQualityTests(unittest.TestCase):
    def test_noop_does_not_need_a_valid_anchor(self):
        real = edit('old', 'new')
        cleaned, info = prune_degenerate_edits(real + edit('missing', 'missing'))
        self.assertEqual(parse_edit_blocks(cleaned), parse_edit_blocks(real))
        self.assertEqual(info['noop_edits'], 1)
        self.assertFalse(info['cycle_trimmed'])

    def test_long_repeated_suffix_keeps_one_cycle(self):
        first = edit('initial', 'next')
        cycle = edit('x' * 100, 'y' * 100) + edit('z' * 100, 'q' * 100)
        text = first + cycle * 5 + '<<<EDIT frontend/src/a.js>>>\n<<<SEARCH>>>\nincomplete'
        cleaned, info = prune_degenerate_edits(text)
        self.assertTrue(info['cycle_trimmed'])
        self.assertEqual(parse_edit_blocks(cleaned), parse_edit_blocks(first + cycle))

    def test_ordered_reversal_is_not_arbitrary_deduplicated(self):
        text = edit('A', 'B') + edit('B', 'A') + edit('A', 'B')
        cleaned, info = prune_degenerate_edits(text)
        self.assertEqual(cleaned, text)
        self.assertFalse(info['cycle_trimmed'])

    def test_long_periodic_reversal_preserves_final_cycle_phase(self):
        forward, backward = edit('A' * 100, 'B' * 100), edit('B' * 100, 'A' * 100)
        text = (forward + backward) * 4 + forward
        cleaned, info = prune_degenerate_edits(text)
        self.assertTrue(info['cycle_trimmed'])
        self.assertEqual(parse_edit_blocks(cleaned), parse_edit_blocks(forward + backward + forward))

    def test_later_different_edit_prevents_trimming(self):
        text = edit('a' * 100, 'b' * 100) * 5 + edit('last', 'changed')
        cleaned, info = prune_degenerate_edits(text)
        self.assertEqual(cleaned, text)
        self.assertFalse(info['cycle_trimmed'])

    def test_prose_between_cycles_is_not_deleted(self):
        block = edit('x' * 200, 'y' * 200)
        text = (block + 'unrecognized meaningful content\n') * 4
        cleaned, info = prune_degenerate_edits(text)
        self.assertEqual(cleaned, text)
        self.assertFalse(info['cycle_trimmed'])

    def test_metrics_are_content_free(self):
        data = reply_quality(edit('secret', 'value') * 2)
        self.assertEqual(data['repeated_edit_blocks'], 1)
        self.assertNotIn('secret', str(data))

    def test_marker_literals_inside_file_body_are_preserved(self):
        text = '<<<FILE frontend/fixture.txt>>>\n' + edit('same', 'same') + '<<<END FILE>>>\n'
        cleaned, info = prune_degenerate_edits(text)
        self.assertEqual(cleaned, text)
        self.assertEqual(info['edit_blocks'], 0)

    def test_unrecognized_final_content_is_not_erased(self):
        text = edit('x' * 200, 'y' * 200) * 4 + 'unrecognized final content'
        cleaned, info = prune_degenerate_edits(text)
        self.assertEqual(cleaned, text)
        self.assertFalse(info['cycle_trimmed'])


if __name__ == '__main__':
    unittest.main()
