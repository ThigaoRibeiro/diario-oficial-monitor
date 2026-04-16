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
import sys
from datetime import date
from html import escape
from pathlib import Path
from uuid import uuid4

from fetcher import fetch_prefeitura
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


# ── Índice ────────────────────────────────────────────────────

def load_prefeitura_index(prefeitura_id: str) -> list[dict]:
    path = DATA_DIR / prefeitura_id / "index.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def save_prefeitura_index(prefeitura_id: str, index: list[dict]) -> None:
    path = DATA_DIR / prefeitura_id / "index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    index.sort(key=lambda x: x["date"], reverse=True)
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

def set_output(key: str, value: str) -> None:
    f = os.environ.get("GITHUB_OUTPUT")
    if f:
        with open(f, "a", encoding="utf-8") as fh:
            if "\n" in value:
                # Usa delimitador dinâmico para evitar colisão com o conteúdo.
                delimiter = f"EOF_{uuid4().hex}"
                fh.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")
            else:
                fh.write(f"{key}={value}\n")
    log.info("OUTPUT %s=%s", key, value)


def single_line(text: str) -> str:
    """Normaliza texto para uma única linha (evita quebrar GITHUB_OUTPUT)."""
    return " ".join(str(text).split())


# ── Pipeline por prefeitura ───────────────────────────────────

def process_prefeitura(pref: dict) -> dict:
    pid = pref["id"]
    result = {"prefeitura_id": pid, "convocados": [], "error": None, "skipped": False}

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
    output_path = DATA_DIR / pid / f"{iso_date}.json"
    force = os.environ.get("FORCE_REPROCESS", "false").lower() == "true"
    if output_path.exists() and not force:
        log.info("[%s] Edição %s já processada. Use FORCE_REPROCESS=true para reprocessar.", pid, iso_date)
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        result["convocados"] = existing.get("convocados", [])
        result["skipped"]    = True
        result["date"]       = iso_date
        result["edition_id"] = meta["edition_id"]
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

    # Salva JSON da data
    entry = {
        "date":             iso_date,
        "date_display":     meta["date_display"],
        "prefeitura_id":    pid,
        "prefeitura_nome":  pref["nome"],
        "prefeitura_estado": pref["estado"],
        "edition_id":       meta["edition_id"],
        "pdf_url":          meta["pdf_url"],
        "convocados_count": len(convocados),
        "has_convocacoes":  len(convocados) > 0,
        "convocados":       convocados,
        "sections_found":   [s["title"] for s in parsed["relevant_sections"]],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("[%s] Salvo: %s (%d convocados)", pid, output_path, len(convocados))

    # Atualiza índice da prefeitura
    idx = load_prefeitura_index(pid)
    idx = [e for e in idx if e["date"] != iso_date]
    idx.append({
        "date":             iso_date,
        "date_display":     meta["date_display"],
        "edition_id":       meta["edition_id"],
        "convocados_count": len(convocados),
        "has_convocacoes":  len(convocados) > 0,
    })
    save_prefeitura_index(pid, idx)

    # O PDF é mantido em tmp/ para ser enviado como anexo no email

    result.update({"date": iso_date, "edition_id": meta["edition_id"], "convocados": convocados})
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
        return

    log.info("Prefeituras ativas: %s", [p["id"] for p in active])

    total_convocados = []
    summary_lines    = []
    summary_html     = []

    for pref in active:
        r = process_prefeitura(pref)
        if r.get("error"):
            error_msg = single_line(r["error"])
            summary_lines.append(f"❌ {pref['nome']}: Erro — {error_msg}")
            summary_html.append(
                f"<div><strong>❌ {escape(pref['nome'])}</strong>: Erro — {escape(error_msg)}</div>"
            )
            continue

        count = len(r.get("convocados", []))
        total_convocados.extend(r.get("convocados", []))

        if count > 0:
            summary_lines.append(f"✅ {pref['nome']} — {count} convocado(s)")
            summary_html.append(
                f"<div><strong>✅ {escape(pref['nome'])} — {count} convocado(s)</strong></div>"
            )
            nomes = [c["nome"] for c in r["convocados"][:5]]
            for n in nomes:
                n_clean = single_line(n)
                summary_lines.append(f"   • {n_clean}")
                summary_html.append(
                    f"<div style=\"padding-left: 16px;\">&bull; {escape(n_clean)}</div>"
                )
            if count > 5:
                summary_lines.append(f"   ... e mais {count - 5}")
                summary_html.append(
                    f"<div style=\"padding-left: 16px;\">... e mais {count - 5}</div>"
                )
        else:
            summary_lines.append(f"📭 {pref['nome']} — sem convocações")
            summary_html.append(f"<div>📭 {escape(pref['nome'])} — sem convocações</div>")

    # Reconstrói índice global
    rebuild_global_index(active)

    # Outputs para GitHub Actions
    total = len(total_convocados)
    today_str = date.today().strftime("%d/%m/%Y")
    set_output("convocados_count",  str(total))
    set_output("has_convocacoes",   "true" if total > 0 else "false")
    set_output("email_summary",     single_line(" | ".join(summary_lines)))
    set_output("email_summary_html", "".join(summary_html))
    set_output("prefeituras_count", str(len(active)))
    set_output("edition_date",      today_str)   # usado no subject/commit do workflow

    log.info("=== Concluído: %d convocados em %d prefeitura(s) ===", total, len(active))


if __name__ == "__main__":
    run()
