"""
fetcher.py — Baixa a edição mais recente do Diário Oficial.

Suporta prefeituras que usam o sistema "doweb" (ex: Nova Iguaçu).
"""

import httpx
import re
import json
import logging
from datetime import date, datetime
from pathlib import Path
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


def _get_latest_edition_doweb(prefeitura: dict) -> tuple[int, str]:
    """Extrai ID e data da edição mais recente de um portal doweb."""
    listing_url = prefeitura["listing_url"]
    base_url    = prefeitura["portal_url"]
    log.info("[%s] Buscando lista em %s", prefeitura["id"], listing_url)

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        resp = client.get(listing_url)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    links = soup.find_all("a", href=re.compile(r"/portal/diario-oficial/ver/(\d+)"))

    if not links:
        raise RuntimeError(f"[{prefeitura['id']}] Nenhuma edição encontrada")

    first = links[0]
    href  = first["href"]
    edition_id = int(re.search(r"/ver/(\d+)", href).group(1))

    text = first.get_text(separator=" ", strip=True)
    date_match = re.search(r"(\d{2}/\d{2}/\d{4})", text)
    date_str = date_match.group(1) if date_match else date.today().strftime("%d/%m/%Y")

    log.info("[%s] Edição mais recente: ID=%d  data=%s", prefeitura["id"], edition_id, date_str)
    return edition_id, date_str


def _get_pdf_url_doweb(prefeitura: dict, edition_id: int) -> str:
    """Extrai URL do PDF de uma página de edição doweb."""
    base_url = prefeitura["portal_url"]
    view_url = f"{base_url}/portal/diario-oficial/ver/{edition_id}"
    log.info("[%s] Acessando edição: %s", prefeitura["id"], view_url)

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        resp = client.get(view_url)
        resp.raise_for_status()

    match = re.search(r'"(/uploads/[^"]+\.pdf)"', resp.text)
    if not match:
        match = re.search(r"(/uploads/[^\s\"']+\.pdf)", resp.text)

    if not match:
        raise RuntimeError(f"[{prefeitura['id']}] PDF não encontrado na edição {edition_id}")

    return base_url + match.group(1)


def download_pdf(pdf_url: str, dest_path: Path) -> Path:
    """Baixa o PDF para dest_path."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    log.info("Baixando PDF → %s", dest_path)

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=120) as client:
        with client.stream("GET", pdf_url) as resp:
            resp.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)

    log.info("Download OK: %.1f KB", dest_path.stat().st_size / 1024)
    return dest_path


def fetch_prefeitura(prefeitura: dict, output_dir: Path) -> dict:
    """
    Fluxo completo para uma prefeitura.
    Retorna metadados da edição baixada.
    """
    tipo = prefeitura.get("tipo", "doweb")

    if tipo == "doweb":
        edition_id, date_str = _get_latest_edition_doweb(prefeitura)
        pdf_url = _get_pdf_url_doweb(prefeitura, edition_id)
    else:
        raise NotImplementedError(f"Tipo '{tipo}' ainda não suportado para {prefeitura['id']}")

    d = datetime.strptime(date_str, "%d/%m/%Y")
    iso_date = d.strftime("%Y-%m-%d")

    pdf_dest = output_dir / f"{prefeitura['id']}_{iso_date}.pdf"
    download_pdf(pdf_url, pdf_dest)

    return {
        "prefeitura_id": prefeitura["id"],
        "edition_id": edition_id,
        "date": iso_date,
        "date_display": date_str,
        "pdf_url": pdf_url,
        "pdf_local": str(pdf_dest),
    }
