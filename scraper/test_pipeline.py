"""
test_pipeline.py — Testa o pipeline completo localmente.

Uso:
  cd scraper
  python test_pipeline.py              # testa tudo
  python test_pipeline.py --fetch      # apenas download do PDF
  python test_pipeline.py --parse      # apenas parse (usa o último PDF baixado)
  python test_pipeline.py --full       # pipeline completo (igual ao GitHub Actions)
"""

import argparse
import json
import logging
import sys
import os
import tempfile
from pathlib import Path
from datetime import datetime

# Garante que o diretório do scraper está no path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("test")

ROOT       = Path(__file__).parent.parent
CONFIG_DIR = ROOT / "config"
TMP_DIR    = ROOT / "tmp"
TMP_DIR.mkdir(exist_ok=True)


def test_config():
    """Verifica configuração."""
    log.info("── Teste 1: Configuração ──────────────────────")
    config_path = CONFIG_DIR / "prefeituras.json"
    assert config_path.exists(), f"config/prefeituras.json não encontrado em {config_path}"
    prefeituras = json.loads(config_path.read_text(encoding="utf-8"))
    active = [p for p in prefeituras if p.get("ativo")]
    log.info("✅ Config OK — %d prefeitura(s) no total, %d ativa(s)", len(prefeituras), len(active))
    for p in active:
        log.info("   → %s (%s) | tipo=%s", p["nome"], p["estado"], p.get("tipo", "doweb"))
    return active


def test_fetch(pref: dict):
    """Testa o download do PDF."""
    log.info("── Teste 2: Download do PDF (%s) ─────────────", pref["nome"])
    from fetcher import fetch_prefeitura
    try:
        meta = fetch_prefeitura(pref, TMP_DIR)
        log.info("✅ Download OK")
        log.info("   Edição:  %s (ID: %s)", meta["date_display"], meta["edition_id"])
        log.info("   PDF URL: %s", meta["pdf_url"])
        log.info("   Salvo:   %s (%.1f KB)", meta["pdf_local"],
                 Path(meta["pdf_local"]).stat().st_size / 1024)
        return meta
    except Exception as e:
        log.error("❌ Falha no download: %s", e)
        sys.exit(1)


def test_parse(pdf_path: Path):
    """Testa a extração de texto do PDF."""
    log.info("── Teste 3: Parse do PDF ──────────────────────")
    from parser import parse_pdf
    try:
        result = parse_pdf(pdf_path)
        log.info("✅ Parse OK")
        log.info("   Texto extraído: %d caracteres", len(result["full_text"]))
        log.info("   Seções de convocação encontradas: %d", len(result["relevant_sections"]))
        if result["relevant_sections"]:
            for s in result["relevant_sections"]:
                preview = s["content"][:120].replace("\n", " ")
                log.info("   → [%s] %s...", s["title"][:50], preview)
        return result
    except Exception as e:
        log.error("❌ Falha no parse: %s", e)
        raise


def test_extract(parsed: dict):
    """Testa a extração de convocados."""
    log.info("── Teste 4: Extração de convocados ────────────")
    from extractor import extract_convocados
    if not parsed["has_convocacoes"]:
        log.info("📭 Nenhuma seção de convocação encontrada no PDF.")
        return []
    try:
        convocados = extract_convocados(parsed["relevant_sections"])
        log.info("✅ Extração OK — %d convocado(s) encontrado(s)", len(convocados))
        for i, c in enumerate(convocados[:10], 1):
            log.info("   %2d. %-40s | %s", i, c["nome"], c["cargo"])
        if len(convocados) > 10:
            log.info("   ... e mais %d", len(convocados) - 10)
        return convocados
    except Exception as e:
        log.error("❌ Falha na extração: %s", e)
        raise


def test_outputs(convocados: list, pref: dict, date_str: str):
    """Simula os outputs do GitHub Actions."""
    log.info("── Teste 5: Simulação de Outputs ──────────────")
    total = len(convocados)
    summary = []
    if total > 0:
        summary.append(f"✅ {pref['nome']} — {total} convocado(s)")
        for c in convocados[:5]:
            summary.append(f"   • {c['nome']}")
        if total > 5:
            summary.append(f"   ... e mais {total - 5}")
    else:
        summary.append(f"📭 {pref['nome']} — sem convocações")

    log.info("   convocados_count = %d", total)
    log.info("   has_convocacoes  = %s", "true" if total > 0 else "false")
    log.info("   edition_date     = %s", date_str)
    log.info("   email_subject    = %s",
             f"🔔 Diário Oficial — {total} convocados em {date_str}" if total > 0
             else f"📭 Diário Oficial {date_str} — sem convocações")
    log.info("   email_summary:\n%s", "\n".join(summary))
    log.info("✅ Outputs OK")


def run_full_pipeline():
    """Roda o pipeline completo (equivalente ao GitHub Actions)."""
    log.info("── Pipeline Completo (modo GitHub Actions) ────")
    os.environ.setdefault("FORCE_REPROCESS", "false")
    # Simula o GITHUB_OUTPUT
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        tmp_output = f.name
    os.environ["GITHUB_OUTPUT"] = tmp_output

    try:
        import main
        main.run()
        log.info("\n── Outputs capturados ─────────────────────────")
        outputs = {}
        for line in Path(tmp_output).read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                outputs[k] = v
                log.info("   %s = %s", k, v[:200])
        log.info("✅ Pipeline completo OK")
    finally:
        Path(tmp_output).unlink(missing_ok=True)
        os.environ.pop("GITHUB_OUTPUT", None)


def main():
    parser = argparse.ArgumentParser(description="Testa o pipeline do Diário Oficial Monitor")
    parser.add_argument("--fetch",  action="store_true", help="Apenas testa download do PDF")
    parser.add_argument("--parse",  action="store_true", help="Apenas testa parse (usa PDF em tmp/)")
    parser.add_argument("--full",   action="store_true", help="Pipeline completo (como GitHub Actions)")
    args = parser.parse_args()

    log.info("══════════════════════════════════════════════")
    log.info("  Diário Oficial Monitor — Teste Local")
    log.info("  %s", datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    log.info("══════════════════════════════════════════════")

    # Se não houver argumento específico, roda tudo
    run_all = not (args.fetch or args.parse or args.full)

    if args.full:
        run_full_pipeline()
        return

    # Teste de configuração (sempre)
    active = test_config()
    if not active:
        log.error("❌ Nenhuma prefeitura ativa! Edite config/prefeituras.json")
        sys.exit(1)

    pref = active[0]  # usa a primeira prefeitura ativa

    if args.fetch or run_all:
        meta = test_fetch(pref)
        pdf_path = Path(meta["pdf_local"])
        date_str = meta["date_display"]
    elif args.parse:
        # Busca o PDF mais recente em tmp/
        pdfs = sorted(TMP_DIR.glob(f"{pref['id']}_*.pdf"), reverse=True)
        if not pdfs:
            log.error("❌ Nenhum PDF encontrado em tmp/. Rode com --fetch primeiro.")
            sys.exit(1)
        pdf_path = pdfs[0]
        date_str = datetime.today().strftime("%d/%m/%Y")
        log.info("Usando PDF existente: %s", pdf_path)

    if args.parse or run_all:
        parsed = test_parse(pdf_path)
        convocados = test_extract(parsed)
        test_outputs(convocados, pref, date_str)

    log.info("══════════════════════════════════════════════")
    log.info("  ✅ Todos os testes passaram!")
    log.info("══════════════════════════════════════════════")


if __name__ == "__main__":
    main()
