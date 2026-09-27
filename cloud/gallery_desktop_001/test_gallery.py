"""Regression checks for exact integration, photo order and unrelated-content safety."""
import ast
import json
from pathlib import Path
import unittest

from build_candidate import LEGACY, patch_source, upgrade_card
from ua_gallery import JS, MARKER, render_viewer


def legacy_viewer(urls):
    return ("<div id='lupa'><img id='bolshoe' src='' alt=''></div><div id='lupaschet'></div>"
            '<script>var kadry=' + json.dumps(urls) + ';var tek=0;' + LEGACY + '</script>')


def legacy_function(name='sobrat_kartochku'):
    return ('def ' + name + '(m, kadry):\n'
            '    c = ["unchanged photo rail and vehicle data"]\n'
            '    if kadry:\n'
            '        c.append("legacy markup")\n'
            '        c.append("legacy source array")\n'
            '        c.append(' + repr(LEGACY) + ')\n'
            '        c.append("</script>")\n'
            '    return "".join(c)\n')


class GalleryRegressionTests(unittest.TestCase):
    def test_photo_order_and_urls_are_preserved(self):
        urls = ['foto/UA-0018/003.jpg', 'foto/UA-0018/007.jpg']
        result = upgrade_card('PREFIX VIN price status' + legacy_viewer(urls) + 'SUFFIX video specs')
        self.assertEqual(result, 'PREFIX VIN price status' + render_viewer(urls) + 'SUFFIX video specs')

    def test_upgrading_twice_does_not_duplicate_controls(self):
        result = upgrade_card(legacy_viewer(['1.jpg']))
        self.assertEqual(upgrade_card(result), result)
        self.assertEqual(result.count('<!--' + MARKER + '-->'), 1)

    def test_unknown_script_fails_without_partial_output(self):
        with self.assertRaisesRegex(ValueError, 'SCRIPT_DRIFT'):
            upgrade_card(legacy_viewer(['1.jpg']).replace('var x0=null;', 'var x0=7;'))

    def test_duplicate_viewer_fails(self):
        with self.assertRaisesRegex(ValueError, 'HTML_ANCHOR'):
            upgrade_card(legacy_viewer(['1.jpg']) * 2)

    def test_diagnostics_and_wrappers_remain_byte_identical(self):
        diagnostic = legacy_function('sobrat_diagnostiku')
        wrapper = '\ndef sobrat_kartochku(m, kadry):\n    return original(m, kadry)\n'
        source = diagnostic + '\n' + legacy_function() + wrapper
        result = patch_source(source)
        self.assertTrue(result.startswith(diagnostic))
        self.assertTrue(result.endswith(wrapper))
        self.assertEqual(result.count('from ua_gallery import render_viewer'), 1)
        compile(result, 'candidate', 'exec')

    def test_other_statements_in_block_are_not_deleted(self):
        with self.assertRaisesRegex(ValueError, 'STATEMENT_COUNT'):
            patch_source(legacy_function().replace('    return', '        audit()\n    return'))

    def test_ambiguous_source_fails(self):
        with self.assertRaisesRegex(ValueError, 'FUNCTION_ANCHOR'):
            patch_source(legacy_function() * 2)

    def test_empty_gallery_has_no_broken_viewer(self):
        self.assertEqual(render_viewer([]), '')

    def test_source_url_cannot_break_out_of_script(self):
        result = render_viewer(['x</script><script>alert(1)</script>'])
        self.assertEqual(result.count('</script>'), 1)
        self.assertIn('\\u003c/script>', result)

    def test_new_card_passes_original_photo_list_to_shared_viewer(self):
        function = ast.parse(patch_source(legacy_function())).body[0]
        block = next(node for node in function.body if isinstance(node, ast.If))
        self.assertEqual(ast.dump(block.test), ast.dump(ast.Name(id='kadry', ctx=ast.Load())))
        self.assertIsInstance(block.body[0], ast.ImportFrom)
        self.assertEqual(block.body[0].module, 'ua_gallery')
        append = block.body[1].value
        self.assertEqual(append.func.value.id, 'c')
        self.assertEqual(append.func.attr, 'append')
        self.assertEqual(append.args[0].func.id, 'render_viewer')
        self.assertEqual(append.args[0].args[0].id, 'kadry')


if __name__ == '__main__':
    unittest.main()
