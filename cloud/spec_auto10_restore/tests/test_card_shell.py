"""Semantic safety tests; no production files, application imports, or network."""
import importlib.util
from pathlib import Path
import unittest


RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
spec = importlib.util.spec_from_file_location("card_shell_test", RUNTIME / "card_shell.py")
shell = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shell)

VIN = "WDDZF0EB7HA053001"
FOREIGN = "WDD2452322J561014"
UID = "UA-0001"
MAIN = "<table><tr><td class='k'>Год</td><td>2017</td></tr><tr><td class='k'>VIN</td><td>" + VIN + "</td></tr></table>"
PANEL = (shell.VIN_MARKERS[0][0] + '<div class="blok ua-clean-vin" data-ua-clean-vin="1" '
         'data-ua-card="UA-0001" data-ua-stage="2" data-ua-video-count="3">'
         '<div class="zag">VIN</div><div class="ua-vin-value">' + VIN + '</div></div>' + shell.VIN_MARKERS[0][1])
OTHER = ('<style>.kept {color:red}</style><section id="route">Паром</section>'
         '<a href="UA-0001-diag.html">Диагностика</a><video src="movie.mp4"></video>'
         '<script type="application/ld+json">{"vehicleIdentificationNumber":"' + VIN + '"}</script>'
         '<script>window.vin="' + VIN + '";</script>'
         '<div data-vin="' + VIN + '">Описание &amp; фотографии</div>')


def page(extra="", panel=PANEL):
    return '<!doctype html><html><head><title>' + VIN + '</title></head><body>' + MAIN + panel + OTHER + extra + '</body></html>'


class CardShellTests(unittest.TestCase):
    def test_exact_panel_removal_retains_technical_vin_and_every_other_byte(self):
        source = page()
        after = shell.normalize_html(source, UID)
        self.assertEqual(after, source.replace(PANEL, "", 1))
        self.assertIn(MAIN, after)
        self.assertIn(OTHER, after)
        self.assertEqual(shell.validate_one_visible_vin(after, UID)["visible_vin_count"], 1)
        delta = shell.permitted_delta(source, after, UID)
        self.assertEqual(delta["outside_permitted_regions_byte_changes"], 0)
        self.assertEqual([row["reason"] for row in delta["permitted_removals"]], ["marked_duplicate_vin_block"])

    def test_normalization_is_byte_idempotent(self):
        once = shell.normalize_html(page(), UID)
        self.assertEqual(once, shell.normalize_html(once, UID))
        self.assertEqual(shell.permitted_delta(once, once, UID)["permitted_removals"], [])

    def test_matching_legacy_compact_wrapper_is_supported_without_general_regex_deletion(self):
        panel = PANEL.replace(shell.VIN_MARKERS[0][0], shell.VIN_MARKERS[1][0]).replace(shell.VIN_MARKERS[0][1], shell.VIN_MARKERS[1][1]).replace('"', "'")
        source = page(panel=panel)
        self.assertEqual(shell.normalize_html(source, UID), source.replace(panel, ""))

    def test_known_description_br_line_is_removed_without_rewriting_neighbors(self):
        extra = "<div class='tehtekst'>Цвет — белый<br>VIN: " + VIN + "<br>Следующее предложение</div>"
        after = shell.normalize_html(page(extra), UID)
        self.assertIn("<div class='tehtekst'>Цвет — белый<br>Следующее предложение</div>", after)
        self.assertEqual(len(shell.permitted_delta(page(extra), after, UID)["permitted_removals"]), 2)

    def test_known_description_bullet_removed_but_other_bullets_retained(self):
        row = "<div class='tehstr'><div class='m'>•</div><div>VIN: " + VIN + "</div></div>"
        other = "<div class='tehstr'><div class='m'>•</div><div>Пробег 178 000 км</div></div>"
        source = page(other + row + other)
        self.assertEqual(shell.normalize_html(source, UID), source.replace(PANEL, "").replace(row, ""))

    def test_known_description_clause_preserves_whole_remaining_sentence(self):
        phrase = "VIN проверен: " + VIN + ". "
        extra = "<div class='tehstr'><div class='m'>•</div><div>Автомобиль уже выкуплен и отправлен паромом. " + phrase + "По данным карточки, пробег составляет всего 342 км.</div></div>"
        source = page(extra)
        after = shell.normalize_html(source, UID)
        self.assertEqual(after, source.replace(PANEL, "").replace(phrase, ""))
        self.assertIn("Автомобиль уже выкуплен и отправлен паромом. По данным карточки, пробег составляет всего 342 км.", after)

    def test_unknown_description_repetitions_fail_instead_of_erasing_prose(self):
        for extra in ("<p>Проверенный VIN: " + VIN + "</p>", "<p>VIN " + FOREIGN + "</p>",
                      "<p>VIN: <strong>" + VIN[:8] + "</strong>" + VIN[8:] + "</p>"):
            with self.subTest(extra=extra), self.assertRaisesRegex(shell.ShellError, "VISIBLE_VIN_COUNT_OR_IDENTITY"):
                shell.normalize_html(page(extra), UID)

    def test_unknown_marker_structure_content_identity_or_extra_panel_fails(self):
        variants = [
            PANEL.replace('data-ua-card="UA-0001"', 'data-ua-card="UA-0002"'),
            PANEL.replace(VIN, FOREIGN),
            PANEL.replace('class="ua-vin-value"', 'class="ua-vin-value" onclick="bad()"'),
            PANEL.replace("</div></div>", "</div><a href='report'>Extra</a></div>"),
            PANEL.replace('data-ua-stage="2"', 'data-ua-stage="2" data-ua-stage="2"'),
            PANEL.replace('class="zag"', 'class="zag"><script></script><div class="zag"'),
            PANEL.replace(shell.VIN_MARKERS[0][0], ""),
            PANEL.replace(shell.VIN_MARKERS[0][1], ""),
            PANEL + PANEL,
        ]
        for panel in variants:
            with self.subTest(panel=panel), self.assertRaises(shell.ShellError):
                shell.normalize_html(page(panel=panel), UID)

    def test_unmarked_or_malformed_main_table_fails(self):
        for source in (page().replace(MAIN, ""), page().replace(MAIN, MAIN + MAIN),
                       page().replace("class='k'>VIN", "class='unknown'>VIN"),
                       page().replace("<td>" + VIN, "<td><b>" + VIN),
                       page().replace("<table>", "<table hidden>")):
            with self.subTest(source=source), self.assertRaises(shell.ShellError):
                shell.normalize_html(source, UID)

    def test_script_schema_attributes_and_explicit_hidden_text_are_untouched(self):
        extra = ('<div hidden>' + VIN + '</div><div style="display:none">' + VIN + '</div>'
                 '<template><div>' + FOREIGN + '</div></template>')
        source = page(extra)
        self.assertEqual(shell.normalize_html(source, UID), source.replace(PANEL, ""))
        # aria-hidden affects accessibility, not screen visibility; it is not a hiding exemption.
        with self.assertRaises(shell.ShellError):
            shell.normalize_html(page('<div aria-hidden="true">' + VIN + '</div>'), UID)

    def test_description_row_with_unexpected_script_or_comment_cannot_be_removed(self):
        for hidden in ("<script></script>", "<!--keep-me-->"):
            extra = "<div class='tehstr'><div class='m'>•" + hidden + "</div><div>VIN: " + VIN + "</div></div>"
            with self.assertRaises(shell.ShellError):
                shell.normalize_html(page(extra), UID)

    def test_shell_contract_allows_only_spec_region_and_proven_removals(self):
        before = page()
        after = shell.normalize_html(before, UID)
        block = shell.SPEC_MARKERS[0] + '<details><summary>Дополнительная спецификация</summary></details>' + shell.SPEC_MARKERS[1]
        candidate = after.replace(MAIN, MAIN + block)
        self.assertEqual(shell.permitted_delta(before, candidate, UID)["status"], "PASS")
        for old, new in (("color:red", "color:blue"), ("Паром", "Киев"), ("movie.mp4", "other.mp4"),
                         ("2017", "2018"), ("Описание &amp; фотографии", "Удалено"),
                         ('window.vin="', 'window.changed="')):
            with self.subTest(old=old), self.assertRaisesRegex(shell.ShellError, "UNAUTHORIZED_NON_SPEC_CHANGE"):
                shell.permitted_delta(before, candidate.replace(old, new), UID)

    def test_contract_rejects_reintroduced_duplicates_and_malformed_spec_markers(self):
        normalized = shell.normalize_html(page(), UID)
        with self.assertRaises(shell.ShellError):
            shell.permitted_delta(page(), page(), UID)
        for changed in (normalized + shell.SPEC_MARKERS[0], normalized + shell.SPEC_MARKERS[1],
                        normalized + (shell.SPEC_MARKERS[0] + shell.SPEC_MARKERS[1]) * 2):
            with self.assertRaises(shell.ShellError):
                shell.permitted_delta(page(), changed, UID)

    def test_static_asset_contract_allows_vehicle_data_and_spec_style_changes(self):
        before = page('<link rel="stylesheet" href="card.css"><script src="card.js" defer></script>')
        after = shell.normalize_html(before, UID).replace("2017", "2018").replace('window.vin="', 'window.newGalleryData="')
        block = shell.SPEC_MARKERS[0] + '<style>.ua-additional-spec{color:gold}</style><details>Specs</details>' + shell.SPEC_MARKERS[1]
        after = after.replace(MAIN.replace("2017", "2018"), MAIN.replace("2017", "2018") + block)
        result = shell.validate_shell_assets(before, after)
        self.assertEqual(result["static_asset_count"], 3)
        self.assertEqual(result["style_count"], 1)
        self.assertEqual(result["stylesheet_link_count"], 1)
        self.assertEqual(result["external_script_count"], 1)

    def test_static_asset_contract_blocks_restyle_asset_changes_order_and_unknown_baseline(self):
        before = page('<link rel="stylesheet" href="card.css"><script src="card.js" defer></script>')
        changes = [before.replace("color:red", "color:blue"), before.replace("card.css", "changed.css"),
                   before.replace("card.js", "changed.js"), before.replace(" defer", " async"),
                   before + '<script src="extra.js"></script>', before.replace('<style>.kept {color:red}</style>', ''),
                   before.replace('<link rel="stylesheet" href="card.css"><script src="card.js" defer></script>',
                                  '<script src="card.js" defer></script><link rel="stylesheet" href="card.css">')]
        for after in changes:
            with self.subTest(after=after), self.assertRaisesRegex(shell.ShellError, "STATIC_ASSETS_CHANGED"):
                shell.validate_shell_assets(before, after)
        with self.assertRaisesRegex(shell.ShellError, "MISSING_ASSET_BASELINE"):
            shell.validate_shell_assets('<html></html>', '<html></html>')


if __name__ == "__main__":
    unittest.main()
