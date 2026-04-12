"""
parser.py — Extrai texto do PDF do Diário Oficial e identifica seções relevantes.

Usa pdfplumber para leitura robusta de PDFs com layout variado.
"""

import pdfplumber
import re
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Palavras-chave que indicam seções de convocação/aprovação em concurso público
SECTION_KEYWORDS = [
    r"CONVOCA[\xc7C][\xc3A]O",          # CONVOCAÇÃO
    r"CONVOCADOS?",
    r"APROVADOS?\s+E\s+CONVOCADOS?",
    r"LISTA\s+DE\s+APROVADOS?",
    r"RESULTADO\s+FINAL\s+DO\s+CONCURSO",
    r"RESULTADO\s+FINAL\s+DO\s+PROCESSO\s+SELETIVO",
    r"CHAMAMENTO\s+P[\xdaU]BLICO.*CONVOCA",  # chamamento que CONVOCA (raro)
]

# Palavras que indicam que a seção NÃO é de convocação de concurso
FALSE_POSITIVE_KEYWORDS = re.compile(
    r"CHAMAMENTO\s+P[\xdaU]BLICO|AGENTES\s+CULTURAIS|CADASTRAMENTO|INSCRI[\xc7C][\xd5O][\xd5O]ES|RESULTADO\s+PRELIMINAR",
    re.IGNORECASE | re.UNICODE,
)

SECTION_PATTERN = re.compile(
    "|".join(SECTION_KEYWORDS),
    re.IGNORECASE | re.UNICODE,
)


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extrai todo o texto do PDF, página por página."""
    log.info("Extraindo texto de: %s", pdf_path)
    pages_text = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        total = len(pdf.pages)
        log.info("Total de páginas: %d", total)

        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            # Remove ruído de caracteres especiais desnecessários mas mantém acentos
            text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
            pages_text.append(f"[PÁGINA {i}/{total}]\n{text}")

    full_text = "\n\n".join(pages_text)
    log.info("Texto extraído: %d caracteres", len(full_text))
    return full_text


def find_relevant_sections(full_text: str) -> list[dict]:
    """
    Localiza seções do texto que contêm convocações.
    Retorna lista de dicionários com título e conteúdo de cada seção.
    """
    sections = []
    lines = full_text.split("\n")

    current_section = None
    current_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_section and current_lines:
                current_lines.append("")
            continue

        # Detecta início de nova seção relevante
        if SECTION_PATTERN.search(stripped):
            # Salva seção anterior se existir
            if current_section and current_lines:
                sections.append({
                    "title": current_section,
                    "content": "\n".join(current_lines).strip(),
                })
            current_section = stripped
            current_lines = [stripped]

        elif current_section:
            # Detecta fim da seção (nova seção não relacionada em caixa alta sem números)
            if (
                len(stripped) > 10
                and stripped.isupper()
                and not any(c.isdigit() for c in stripped[:5])
                and not SECTION_PATTERN.search(stripped)
                and not re.search(r"MUNICÍPIO|PREFEITURA|SECRETARIA|DECRETO|PORTARIA", stripped)
            ):
                # Continua colhendo contexto por 5 linhas após o fim provável
                current_lines.append(stripped)
            else:
                current_lines.append(stripped)

    # Última seção
    if current_section and current_lines:
        sections.append({
            "title": current_section,
            "content": "\n".join(current_lines).strip(),
        })

    log.info("Seções relevantes brutas: %d", len(sections))

    # Filtra falsos positivos (chamamentos culturais, inscrições, etc.)
    filtered = []
    for s in sections:
        combined = s["title"] + " " + s["content"][:500]
        if FALSE_POSITIVE_KEYWORDS.search(combined):
            log.info("Seção ignorada (falso positivo): %s", s["title"][:80])
            continue
        filtered.append(s)

    log.info("Seções relevantes após filtro: %d", len(filtered))
    return filtered


def parse_pdf(pdf_path: Path) -> dict:
    """
    Extrai texto e seções relevantes do PDF.
    Retorna estrutura com texto completo e seções filtradas.
    """
    full_text = extract_text_from_pdf(pdf_path)
    sections = find_relevant_sections(full_text)

    return {
        "full_text": full_text,
        "relevant_sections": sections,
        "has_convocacoes": len(sections) > 0,
    }
