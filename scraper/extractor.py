"""
extractor.py — Extrai dados estruturados de convocados/aprovados
               a partir das seções relevantes do Diário Oficial.

Padrões comuns nos editais de Nova Iguaçu:
  - Número de classificação + Nome + Cargo
  - Tabelas: Nº | NOME | CARGO | NOTA
  - Blocos de texto corrido com listas de nomes
"""

import re
import logging
from dataclasses import dataclass, asdict
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Estrutura de dados
# ---------------------------------------------------------------------------

@dataclass
class Convocado:
    nome: str
    cargo: str
    classificacao: Optional[int]
    edital: Optional[str]
    prazo: Optional[str]
    local: Optional[str]
    observacao: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Padrões regex
# ---------------------------------------------------------------------------

# Linha com número de classificação e nome: "1. FULANO DE TAL" ou "1º FULANO DE TAL"
CLASSIF_NAME_PATTERN = re.compile(
    r"^\s*(\d{1,4})[.ºª°\-–]?\s+([A-ZÁÉÍÓÚÂÊÎÔÛÀÃÕÇ][A-ZÁÉÍÓÚÂÊÎÔÛÀÃÕÇ\s]{4,60})\s*$",
    re.UNICODE,
)

# Linha de tabela: número | nome | cargo (separados por 2+ espaços ou tab)
TABLE_ROW_PATTERN = re.compile(
    r"^\s*(\d{1,4})\s{2,}([A-ZÁÉÍÓÚÂÊÎÔÛÀÃÕÇ][A-ZÁÉÍÓÚÂÊÎÔÛÀÃÕÇ\s]{4,60})\s{2,}(.+?)\s*$",
    re.UNICODE,
)

# Extrai cargo da mesma linha ou linha seguinte
CARGO_INLINE_PATTERN = re.compile(
    r"(?:CARGO[:\s]+|FUNÇÃO[:\s]+|VAGA[:\s]+)([A-ZÁÉÍÓÚÂÊÎÔÛÀÃÕÇ][^\n]{3,60})",
    re.IGNORECASE | re.UNICODE,
)

# Número do edital
EDITAL_PATTERN = re.compile(
    r"(?:EDITAL|CONCURSO|PROCESSO SELETIVO)\s+(?:Nº?\.?\s*)?(\d+[/\-]\d{4})",
    re.IGNORECASE,
)

# Prazo de apresentação
PRAZO_PATTERN = re.compile(
    r"(?:PRAZO|APRESENTAR[- ]SE|COMPARECER)\s+[^\d]*(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)

# Local de apresentação
LOCAL_PATTERN = re.compile(
    r"(?:LOCAL|ENDEREÇO|SECRETARIA)[:\s]+([^\n]{5,80})",
    re.IGNORECASE,
)

# Nomes completos em caixa alta (mínimo 2 palavras, cada uma com 2+ chars)
NOME_PATTERN = re.compile(
    r"(?<!\d\s)(?<!\d\.\s)\b([A-ZÁÉÍÓÚÂÊÎÔÛÀÃÕÇ]{2,}(?:\s+(?:DE|DA|DO|DOS|DAS|E)\s+)?[A-ZÁÉÍÓÚÂÊÎÔÛÀÃÕÇ]{2,}"
    r"(?:\s+[A-ZÁÉÍÓÚÂÊÎÔÛÀÃÕÇ]{2,}){0,5})\b",
    re.UNICODE,
)

# Palavras a ignorar (não são nomes)
STOPWORDS = {
    "PREFEITURA", "MUNICIPAL", "NOVA", "IGUAÇU", "SECRETARIA", "ESTADO",
    "RIO", "JANEIRO", "CONVOCAÇÃO", "CONVOCADOS", "EDITAL", "CONCURSO",
    "CARGO", "FUNÇÃO", "APROVADOS", "LISTA", "RESULTADO", "FINAL",
    "HOMOLOGAÇÃO", "DECRETO", "PORTARIA", "RESOLUÇÃO", "PÁGINA",
    "DIÁRIO", "OFICIAL", "PUBLICAÇÃO", "DATA", "ASSINATURA",
}


# ---------------------------------------------------------------------------
# Funções de extração
# ---------------------------------------------------------------------------

def _is_likely_name(text: str) -> bool:
    """Verifica se o texto é provavelmente um nome de pessoa."""
    words = text.strip().split()
    if len(words) < 2 or len(words) > 8:
        return False
    if any(w.upper() in STOPWORDS for w in words):
        return False
    if any(w.isdigit() for w in words):
        return False
    if len(text) < 8 or len(text) > 70:
        return False
    return True


def _extract_edital(text: str) -> Optional[str]:
    m = EDITAL_PATTERN.search(text)
    return m.group(0).strip() if m else None


def _extract_prazo(text: str) -> Optional[str]:
    m = PRAZO_PATTERN.search(text)
    return m.group(1) if m else None


def _extract_local(text: str) -> Optional[str]:
    m = LOCAL_PATTERN.search(text)
    return m.group(1).strip() if m else None


def extract_from_table_section(section_text: str, cargo_context: str) -> list[Convocado]:
    """Extrai convocados de uma seção com formato tabular."""
    convocados = []
    edital = _extract_edital(section_text)
    prazo = _extract_prazo(section_text)
    local = _extract_local(section_text)

    for line in section_text.split("\n"):
        # Formato tabela: nº  NOME  CARGO
        m = TABLE_ROW_PATTERN.match(line)
        if m:
            classif = int(m.group(1))
            nome = m.group(2).strip()
            cargo = m.group(3).strip()
            if _is_likely_name(nome):
                convocados.append(Convocado(
                    nome=nome,
                    cargo=cargo or cargo_context,
                    classificacao=classif,
                    edital=edital,
                    prazo=prazo,
                    local=local,
                    observacao=None,
                ))
            continue

        # Formato lista numerada: nº. NOME
        m2 = CLASSIF_NAME_PATTERN.match(line)
        if m2:
            classif = int(m2.group(1))
            nome = m2.group(2).strip()
            if _is_likely_name(nome):
                convocados.append(Convocado(
                    nome=nome,
                    cargo=cargo_context,
                    classificacao=classif,
                    edital=edital,
                    prazo=prazo,
                    local=local,
                    observacao=None,
                ))

    return convocados


def extract_from_text_section(section_text: str, cargo_context: str) -> list[Convocado]:
    """
    Extrai convocados de texto corrido.
    Busca nomes em maiúsculas dentro do contexto de convocação.
    """
    convocados = []
    edital = _extract_edital(section_text)
    prazo = _extract_prazo(section_text)
    local = _extract_local(section_text)

    # Tenta identificar cargo no contexto
    cargo_match = CARGO_INLINE_PATTERN.search(section_text)
    cargo = cargo_match.group(1).strip() if cargo_match else cargo_context

    # Busca nomes em maiúsculas
    for line in section_text.split("\n"):
        line = line.strip()

        # Pula cabeçalhos e linhas curtas
        if len(line) < 6 or line.startswith("[PÁGINA"):
            continue

        # Linha com número + nome inline
        m = CLASSIF_NAME_PATTERN.match(line)
        if m:
            nome = m.group(2).strip()
            classif = int(m.group(1))
            if _is_likely_name(nome):
                convocados.append(Convocado(
                    nome=nome,
                    cargo=cargo,
                    classificacao=classif,
                    edital=edital,
                    prazo=prazo,
                    local=local,
                    observacao=None,
                ))

    return convocados


def extract_convocados(sections: list[dict]) -> list[dict]:
    """
    Recebe lista de seções relevantes e retorna lista de convocados estruturados.
    """
    all_convocados = []
    seen_names = set()

    for section in sections:
        title = section.get("title", "")
        content = section.get("content", "")

        # Determina cargo pelo título da seção quando possível
        cargo_context = "Não especificado"
        cargo_m = CARGO_INLINE_PATTERN.search(title)
        if cargo_m:
            cargo_context = cargo_m.group(1).strip()

        # Tenta extração tabular primeiro (mais precisa)
        found = extract_from_table_section(content, cargo_context)

        # Se tabular não encontrou, tenta texto corrido
        if not found:
            found = extract_from_text_section(content, cargo_context)

        # Deduplica por nome
        for c in found:
            key = re.sub(r"\s+", " ", c.nome.strip().upper())
            if key not in seen_names:
                seen_names.add(key)
                all_convocados.append(c.to_dict())

    log.info("Total de convocados extraídos: %d", len(all_convocados))
    return all_convocados
