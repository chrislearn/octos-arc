import unittest
from snapshot_focus import focus_interaction_snapshot


class SnapshotFocusTests(unittest.TestCase):
    def test_modal_after_long_hidden_background_is_first(self):
        tree = '- generic:\n  - generic [aria-hidden]:\n' + '    - button: Background\n' * 400
        tree += '  - dialog "Editor":\n    - textbox "Title" [active]\n    - button "Close"\n'
        result = focus_interaction_snapshot(tree)
        self.assertIn('dialog "Editor"', result[:200])
        self.assertIn('button "Close"', result)
        self.assertNotIn('Background', result)

    def test_no_surface_preserves_original_tree(self):
        tree = '- navigation:\n  - link "Home"\n- main:\n  - heading "Items"'
        self.assertEqual(focus_interaction_snapshot(tree), tree)

    def test_hidden_dialog_is_not_selected(self):
        tree = '- generic [aria-hidden]:\n  - dialog "Old"\n- heading "Current"'
        self.assertEqual(focus_interaction_snapshot(tree), tree)

    def test_nested_menu_is_not_duplicated(self):
        tree = '- dialog "Editor":\n  - menu "Actions":\n    - menuitem "Save"\n- button "Outside"'
        result = focus_interaction_snapshot(tree)
        self.assertEqual(result.count('menu "Actions"'), 1)
        self.assertIn('button "Outside"', result)

    def test_independent_surfaces_are_preserved(self):
        result = focus_interaction_snapshot('- menu "Actions":\n  - menuitem "Save"\n- listbox "Choices"')
        self.assertIn('menu "Actions"', result)
        self.assertIn('listbox "Choices"', result)
