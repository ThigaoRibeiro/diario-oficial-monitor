"""
main.py — Orquestrador multi-prefeitura do Diário Oficial Monitor.

Para cada prefeitura ativa em config/prefeituras.json:
  1. Baixa PDF da edição mais recente
  2. Extrai texto e seções de convocação
  3. Extrai dados dos convocados
  4. Salva em data/<prefeitura-id>/YYYY-MM-DD.json
  5. Atualiza data/<prefeitura-id>/index.json
  6. Atualiza data/global-index.json (usado pelo frontend)
"""

import json
import logging
import os
import re
import sys
import unicodedata
from datetime import date, datetime
from html import escape
from pathlib import Path

from fetcher import fetch_prefeitura, _extract_date_from_pdf_url
from parser import parse_pdf
from extractor import extract_convocados

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

ROOT       = Path(__file__).parent.parent
DATA_DIR   = ROOT / "data"
CONFIG_DIR = ROOT / "config"
TMP_DIR    = ROOT / "tmp"

DATA_DIR.mkdir(exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)


def edition_json_name(iso_date: str, edition_id: int | str) -> str:
    return f"{iso_date}_{edition_id}.json"


def date_display_to_iso(date_display: str) -> str:
    return datetime.strptime(date_display, "%d/%m/%Y").strftime("%Y-%m-%d")


def normalize_index_entry(entry: dict) -> dict:
    normalized = dict(entry)
    original_date = normalized.get("date")

    if original_date and not normalized.get("json_path"):
        normalized["json_path"] = f"{original_date}.json"

    pdf_date = _extract_date_from_pdf_url(normalized.get("pdf_url", ""))
    if pdf_date:
        normalized["date_display"] = pdf_date
        normalized["date"] = date_display_to_iso(pdf_date)

    return normalized


# ── Monitoramento de Nomes ────────────────────────────────────

def load_watched_names() -> list[str]:
    """Carrega lista de nomes monitorados do config/monitorados.json e da env WATCH_NAMES."""
    names = []
    
    # 1. Carrega do JSON
    json_path = CONFIG_DIR / "monitorados.json"
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                names.extend([str(n).strip().upper() for n in data if n])
            elif isinstance(data, dict) and "names" in data:
                names.extend([str(n).strip().upper() for n in data["names"] if n])
        except Exception as e:
            log.warning("Falha ao ler config/monitorados.json: %s", e)
            
    # 2. Carrega da Env Var (separado por vírgula)
    env_val = os.environ.get("WATCH_NAMES", "")
    if env_val:
        for val in env_val.split(","):
            val_clean = val.strip().upper()
            if val_clean and val_clean not in names:
                names.append(val_clean)
                
    # Remove duplicados e vazios
    names = [n for n in names if n]
    log.info("Nomes monitorados carregados: %s", names)
    return names


def normalize_for_match(text: str) -> str:
    """Uppercase, remove accents and collapse whitespace for robust name matching."""
    normalized = unicodedata.normalize("NFKD", str(text or "").upper())
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(without_accents.split())


def _watched_name_pattern(normalized_name: str) -> str:
    """Padrão de busca seguro para um nome monitorado já normalizado.

    Nomes de uma palavra só (ex.: "ESTER") exigem \\b nas duas pontas,
    qualquer que seja o tamanho, pois podem aparecer como substring de
    palavras não relacionadas (ex.: "BALESTEROS", "POLIÉSTER",
    "ESTERILIZAÇÃO"). Nomes completos (com espaço, ex.: "ESTER DA SILVA")
    já são específicos o suficiente para busca direta por substring.
    """
    if " " in normalized_name:
        return re.escape(normalized_name)
    return rf"\b{re.escape(normalized_name)}\b"


def _is_watched_name_in(name: str, text: str) -> bool:
    normalized_name = normalize_for_match(name)
    if not normalized_name:
        return False
    return re.search(_watched_name_pattern(normalized_name), normalize_for_match(text)) is not None


def check_watched_matches(convocados: list[dict], full_text: str, watched_names: list[str]) -> list[str]:
    """Retorna a lista de nomes monitorados que foram encontrados."""
    matched = []
    if not watched_names:
        return matched

    normalized_text = normalize_for_match(full_text)

    for name in watched_names:
        normalized_name = normalize_for_match(name)
        if not normalized_name:
            continue

        pattern = _watched_name_pattern(normalized_name)

        # 1. Verifica nos convocados estruturados
        struct_match = any(
            re.search(pattern, normalize_for_match(c.get("nome", "")))
            for c in convocados
        )

        # 2. Fail-safe: busca no texto bruto do PDF
        if struct_match or re.search(pattern, normalized_text):
            matched.append(name)

    return matched


# ── Índice ────────────────────────────────────────────────────

def load_prefeitura_index(prefeitura_id: str) -> list[dict]:
    path = DATA_DIR / prefeitura_id / "index.json"
    if not path.exists():
        return []

    entries = json.loads(path.read_text(encoding="utf-8"))
    enriched = []
    for entry in entries:
        item = dict(entry)
        original_date = item.get("date")
        json_path = item.get("json_path") or (f"{original_date}.json" if original_date else None)
        detail_path = path.parent / json_path if json_path else None

        if detail_path and detail_path.exists():
            try:
                detail = json.loads(detail_path.read_text(encoding="utf-8"))
                for key in ("edition_id", "pdf_url", "date_display", "convocados_count", "has_convocacoes"):
                    if key in detail:
                        item[key] = detail[key]
                item["json_path"] = json_path
            except Exception as e:
                log.warning("[%s] Falha ao enriquecer indice com %s: %s", prefeitura_id, detail_path.name, e)

        enriched.append(normalize_index_entry(item))

    return enriched


def save_prefeitura_index(prefeitura_id: str, index: list[dict]) -> None:
    path = DATA_DIR / prefeitura_id / "index.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    deduped = {}
    for entry in index:
        key = str(entry.get("edition_id") or entry.get("date"))
        current = deduped.get(key)
        entry_priority = (1 if entry.get("json_path") else 0, entry.get("date", ""))
        current_priority = (1 if current and current.get("json_path") else 0, current.get("date", "") if current else "")
        if current is None or entry_priority > current_priority:
            deduped[key] = entry

    index = list(deduped.values())
    index.sort(key=lambda x: (x["date"], str(x.get("edition_id", ""))), reverse=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def rebuild_global_index(prefeituras: list[dict]) -> None:
    """Reconstrói o índice global lido pelo frontend."""
    global_index = []

    for pref in prefeituras:
        pid = pref["id"]
        local_index = load_prefeitura_index(pid)
        for entry in local_index:
            global_index.append({**entry, "prefeitura_id": pid, "prefeitura_nome": pref["nome"], "prefeitura_estado": pref["estado"]})

    global_index.sort(key=lambda x: (x["date"], x["prefeitura_id"]), reverse=True)

    out = DATA_DIR / "global-index.json"
    out.write_text(json.dumps(global_index, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Índice global: %d entradas", len(global_index))


# ── GitHub Actions outputs ────────────────────────────────────

# Regex que captura QUALQUER tipo de quebra de linha, incluindo Unicode.
_LINE_BREAK_RE = re.compile(r"[\r\n\x0b\x0c\x85\u2028\u2029]+")


def _sanitize_output(text: str) -> str:
    """Remove toda quebra de linha e espaço excessivo — garante valor de uma linha."""
    return " ".join(_LINE_BREAK_RE.sub(" ", str(text)).split())


def set_output(key: str, value: str) -> None:
    # Sempre sanitiza para evitar quebra de formato no GITHUB_OUTPUT.
    safe_value = _sanitize_output(value)
    f = os.environ.get("GITHUB_OUTPUT")
    if f:
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={safe_value}\n")
    log.info("OUTPUT %s=%s", key, safe_value)


def single_line(text: str) -> str:
    """Normaliza texto para uma única linha (evita quebrar GITHUB_OUTPUT)."""
    return _sanitize_output(text)


# ── Pipeline por prefeitura ───────────────────────────────────

def process_prefeitura(pref: dict, watched_names: list[str]) -> dict:
    pid = pref["id"]
    result = {"prefeitura_id": pid, "convocados": [], "error": None, "skipped": False, "matched_watched": []}

    # Baixa PDF
    try:
        meta = fetch_prefeitura(pref, TMP_DIR)
    except Exception as e:
        log.error("[%s] Falha no download: %s", pid, e)
        result["error"] = str(e)
        return result

    iso_date = meta["date"]
    pdf_path = Path(meta["pdf_local"])

    # Verifica se já processamos hoje (pode ser ignorado via FORCE_REPROCESS)
    json_name = edition_json_name(iso_date, meta["edition_id"])
    output_path = DATA_DIR / pid / json_name
    force = os.environ.get("FORCE_REPROCESS", "false").lower() == "true"
    if output_path.exists() and not force:
        log.info("[%s] Edição %s já processada. Use FORCE_REPROCESS=true para reprocessar.", pid, iso_date)
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        result["convocados"] = existing.get("convocados", [])
        result["skipped"]    = True
        result["date"]       = iso_date
        result["date_display"] = meta["date_display"]
        result["edition_id"] = meta["edition_id"]
        result["pdf_url"]    = meta["pdf_url"]
        result["json_path"]  = json_name

        full_text = ""
        if watched_names:
            try:
                parsed = parse_pdf(pdf_path)
                full_text = parsed["full_text"]
            except Exception as e:
                log.warning("[%s] Falha ao revalidar PDF ja processado para nomes monitorados: %s", pid, e)

        result["matched_watched"] = check_watched_matches(result["convocados"], full_text, watched_names)

        idx = load_prefeitura_index(pid)
        for entry in idx:
            if str(entry.get("edition_id")) == str(meta["edition_id"]):
                entry.update({
                    "date_display": meta["date_display"],
                    "edition_id": meta["edition_id"],
                    "pdf_url": meta["pdf_url"],
                    "json_path": json_name,
                })
                break
        else:
            idx.append({
                "date": iso_date,
                "date_display": meta["date_display"],
                "edition_id": meta["edition_id"],
                "pdf_url": meta["pdf_url"],
                "json_path": json_name,
                "convocados_count": len(result["convocados"]),
                "has_convocacoes": len(result["convocados"]) > 0,
            })
        save_prefeitura_index(pid, idx)

        return result
    elif output_path.exists() and force:
        log.info("[%s] Reprocessando edição %s (FORCE_REPROCESS=true).", pid, iso_date)

    # Extrai texto
    try:
        parsed = parse_pdf(pdf_path)
    except Exception as e:
        log.error("[%s] Falha no parse: %s", pid, e)
        result["error"] = str(e)
        return result

    # Extrai convocados
    convocados = extract_convocados(parsed["relevant_sections"]) if parsed["has_convocacoes"] else []

    # Faz a busca de nomes monitorados (estruturado + fail-safe texto bruto)
    matched = check_watched_matches(convocados, parsed["full_text"], watched_names)

    # Salva JSON da data
    entry = {
        "date":             iso_date,
        "date_display":     meta["date_display"],
        "prefeitura_id":    pid,
        "prefeitura_nome":  pref["nome"],
        "prefeitura_estado": pref["estado"],
        "edition_id":       meta["edition_id"],
        "pdf_url":          meta["pdf_url"],
        "json_path":        json_name,
        "convocados_count": len(convocados),
        "has_convocacoes":  len(convocados) > 0,
        "convocados":       convocados,
        "sections_found":   [s["title"] for s in parsed["relevant_sections"]],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("[%s] Salvo: %s (%d convocados, %d monitorados encontrados)", pid, output_path, len(convocados), len(matched))

    # Atualiza índice da prefeitura
    idx = load_prefeitura_index(pid)
    idx = [e for e in idx if str(e.get("edition_id")) != str(meta["edition_id"])]
    idx.append({
        "date":             iso_date,
        "date_display":     meta["date_display"],
        "edition_id":       meta["edition_id"],
        "pdf_url":          meta["pdf_url"],
        "json_path":        json_name,
        "convocados_count": len(convocados),
        "has_convocacoes":  len(convocados) > 0,
    })
    save_prefeitura_index(pid, idx)

    # O PDF é mantido em tmp/ para ser enviado como anexo no email

    result.update({
        "date": iso_date,
        "date_display": meta["date_display"],
        "edition_id": meta["edition_id"],
        "pdf_url": meta["pdf_url"],
        "json_path": json_name,
        "convocados": convocados,
        "matched_watched": matched
    })
    return result


# ── Main ──────────────────────────────────────────────────────

def run() -> None:
    log.info("=== Diário Oficial Monitor — Multi-Prefeitura ===")

    config_path = CONFIG_DIR / "prefeituras.json"
    if not config_path.exists():
        log.error("Arquivo config/prefeituras.json não encontrado!")
        sys.exit(1)

    all_prefeituras: list[dict] = json.loads(config_path.read_text(encoding="utf-8"))
    active = [p for p in all_prefeituras if p.get("ativo", False)]

    if not active:
        log.warning("Nenhuma prefeitura ativa em config/prefeituras.json")
        set_output("convocados_count", "0")
        set_output("has_convocacoes", "false")
        set_output("has_watched_match", "false")
        set_output("has_errors", "false")
        return

    log.info("Prefeituras ativas: %s", [p["id"] for p in active])

    watched_names = load_watched_names()
    all_matched_watched = []
    had_errors = False
    latest_edition = None

    total_convocados = []
    summary_lines    = []
    summary_html     = []

    for pref in active:
        r = process_prefeitura(pref, watched_names)
        if r.get("error"):
            had_errors = True
            error_msg = single_line(r["error"])
            summary_lines.append(f"❌ {pref['nome']}: Erro — {error_msg}")
            summary_html.append(
                f"<div><strong>❌ {escape(pref['nome'])}</strong>: Erro — {escape(error_msg)}</div>"
            )
            continue

        if r.get("date") and (latest_edition is None or r["date"] > latest_edition["date"]):
            latest_edition = {
                "date": r["date"],
                "date_display": r.get("date_display") or r["date"],
            }

        count = len(r.get("convocados", []))
        total_convocados.extend(r.get("convocados", []))
        
        # Agrega matches de nomes monitorados
        pref_matched = r.get("matched_watched", [])
        for name in pref_matched:
            if name not in all_matched_watched:
                all_matched_watched.append(name)

        if count > 0:
            summary_lines.append(f"✅ {pref['nome']} — {count} convocado(s)")
            summary_html.append(
                f"<div><strong>✅ {escape(pref['nome'])} — {count} convocado(s)</strong></div>"
            )
            
            # Se houver matches monitorados nesta prefeitura, destaca-os no resumo
            if pref_matched:
                summary_lines.append(f"   🎯 MONITORADO(S) ENCONTRADO(S): {', '.join(pref_matched)}")
                summary_html.append(
                    f"<div style=\"padding-left: 16px; color: #ef4444; font-weight: bold;\">🎯 MONITORADO(S) ENCONTRADO(S): {escape(', '.join(pref_matched))}</div>"
                )

            nomes = [c["nome"] for c in r["convocados"][:5]]
            for n in nomes:
                n_clean = single_line(n)
                # Destaca o nome na lista se for monitorado
                is_monitored = any(_is_watched_name_in(m, n_clean) for m in watched_names)
                bullet = "🎯" if is_monitored else "•"
                style = "color: #ef4444; font-weight: bold;" if is_monitored else ""
                
                summary_lines.append(f"   {bullet} {n_clean}")
                summary_html.append(
                    f"<div style=\"padding-left: 16px; {style}\">{bullet} {escape(n_clean)}</div>"
                )
            if count > 5:
                summary_lines.append(f"   ... e mais {count - 5}")
                summary_html.append(
                    f"<div style=\"padding-left: 16px;\">... e mais {count - 5}</div>"
                )
        else:
            if pref_matched:
                summary_lines.append(f"🎯 {pref['nome']} — nome monitorado encontrado no texto do diário: {', '.join(pref_matched)}")
                summary_html.append(
                    f"<div style=\"color: #ef4444; font-weight: bold;\">🎯 {escape(pref['nome'])} — nome monitorado encontrado no texto do diário: {escape(', '.join(pref_matched))}</div>"
                )
            else:
                summary_lines.append(f"📭 {pref['nome']} — sem convocações")
                summary_html.append(f"<div>📭 {escape(pref['nome'])} — sem convocações</div>")

    # Reconstrói índice global
    rebuild_global_index(active)

    # Outputs para GitHub Actions
    total = len(total_convocados)
    edition_date = latest_edition["date_display"] if latest_edition else date.today().strftime("%d/%m/%Y")
    
    set_output("convocados_count",  str(total))
    set_output("has_convocacoes",   "true" if total > 0 else "false")
    set_output("has_errors",        "true" if had_errors else "false")
    set_output("email_summary",     " | ".join(summary_lines))
    set_output("email_summary_html", "".join(summary_html))
    set_output("prefeituras_count", str(len(active)))
    set_output("edition_date",      edition_date)   # usado no subject/commit do workflow
    
    # Outputs de monitoramento
    set_output("has_watched_match", "true" if all_matched_watched else "false")
    set_output("watched_matched_names", ", ".join(all_matched_watched))

    log.info("=== Concluído: %d convocados em %d prefeitura(s) ===", total, len(active))


if __name__ == "__main__":
    run()
