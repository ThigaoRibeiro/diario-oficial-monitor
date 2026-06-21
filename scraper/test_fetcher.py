import unittest

from bs4 import BeautifulSoup

from fetcher import (
    _extract_date_from_pdf_url,
    _extract_date_from_text,
    _unique_edition_links,
)
from main import check_watched_matches, normalize_for_match


class FetcherDateTests(unittest.TestCase):
    def test_extracts_date_from_pdf_url(self):
        url = "https://doweb.novaiguacu.rj.gov.br/uploads/pmni_de_19-06-2026_-_sexta-feira.pdf"

        self.assertEqual(_extract_date_from_pdf_url(url), "19/06/2026")

    def test_extracts_date_from_listing_text(self):
        text = "Ultima Edicao Diario Oficial - Edicao No *19/06/2026 Postagem 19/06/2026"

        self.assertEqual(_extract_date_from_text(text), "19/06/2026")

    def test_edition_links_are_deduplicated(self):
        soup = BeautifulSoup(
            """
            <a href="/portal/diario-oficial/ver/2310">Ler online</a>
            <a href="/portal/diario-oficial/ver/2310">Baixar</a>
            <a href="/portal/diario-oficial/ver/2309">Anterior</a>
            """,
            "html.parser",
        )

        links = _unique_edition_links(soup)

        self.assertEqual(len(links), 2)
        self.assertIn("/2310", links[0]["href"])


class WatchedNameTests(unittest.TestCase):
    def test_name_matching_ignores_accents_and_extra_spaces(self):
        text = "A candidata ESTER   DA SILVA devera comparecer ao setor responsavel."

        self.assertEqual(normalize_for_match("\u00c9ster da Silva"), "ESTER DA SILVA")
        self.assertEqual(check_watched_matches([], text, ["\u00c9STER DA SILVA"]), ["\u00c9STER DA SILVA"])


if __name__ == "__main__":
    unittest.main()
