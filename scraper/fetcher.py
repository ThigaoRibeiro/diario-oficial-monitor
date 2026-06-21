"""
fetcher.py - Baixa a edicao mais recente do Diario Oficial.

Suporta prefeituras que usam o sistema doweb, como Nova Iguacu.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import httpx
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

DATE_BR_RE = re.compile(r"(?<!\d)(\d{2})/(\d{2})/(\d{4})(?!\d)")
DATE_FILE_RE = re.compile(r"(?<!\d)(\d{2})[-_](\d{2})[-_](\d{4})(?!\d)")


def _valid_date_display(date_str: str) -> bool:
    try:
        datetime.strptime(date_str, "%d/%m/%Y")
        return True
    except ValueError:
        return False


def _extract_date_from_text(text: str) -> str | None:
    for match in DATE_BR_RE.finditer(text or ""):
        date_str = match.group(0)
        if _valid_date_display(date_str):
            return date_str
    return None


def _extract_date_from_pdf_url(pdf_url: str) -> str | None:
    match = DATE_FILE_RE.search(pdf_url or "")
    if not match:
        return None

    day, month, year = match.groups()
    date_str = f"{day}/{month}/{year}"
    return date_str if _valid_date_display(date_str) else None


def _unique_edition_links(soup: BeautifulSoup) -> list:
    links = []
    seen = set()
    for a in soup.find_all("a", href=re.compile(r"/portal/diario-oficial/ver/(\d+)")):
        href = a.get("href", "").strip()
        match = re.search(r"/ver/(\d+)", href)
        if not match:
            continue

        edition_id = int(match.group(1))
        if edition_id in seen:
            continue

        seen.add(edition_id)
        links.append(a)
    return links


def _get_latest_edition_doweb(prefeitura: dict) -> tuple[int, str | None]:
    """Extracts latest edition id and best-effort date from a doweb listing."""
    listing_url = prefeitura["listing_url"]
    log.info("[%s] Buscando lista em %s", prefeitura["id"], listing_url)

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        resp = client.get(listing_url)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    links = _unique_edition_links(soup)
    if not links:
        raise RuntimeError(f"[{prefeitura['id']}] Nenhuma edicao encontrada")

    first = links[0]
    href = first.get("href", "")
    edition_id = int(re.search(r"/ver/(\d+)", href).group(1))

    candidates = [first.get_text(separator=" ", strip=True)]
    parent = first
    for _ in range(4):
        parent = parent.find_parent()
        if not parent:
            break
        candidates.append(parent.get_text(separator=" ", strip=True))
    candidates.append(soup.get_text(separator=" ", strip=True))

    date_str = None
    for text in candidates:
        date_str = _extract_date_from_text(text)
        if date_str:
            break

    log.info(
        "[%s] Edicao mais recente: ID=%d data=%s",
        prefeitura["id"],
        edition_id,
        date_str or "desconhecida",
    )
    return edition_id, date_str


def _get_pdf_url_doweb(prefeitura: dict, edition_id: int) -> tuple[str, str | None]:
    """Extracts PDF URL and best known edition date from a doweb edition page."""
    base_url = prefeitura["portal_url"]
    view_url = f"{base_url}/portal/diario-oficial/ver/{edition_id}"
    log.info("[%s] Acessando edicao: %s", prefeitura["id"], view_url)

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        resp = client.get(view_url)
        resp.raise_for_status()

    match = re.search(r'["\']((?:https?://[^"\']+)?/uploads/[^"\']+\.pdf)["\']', resp.text)
    if not match:
        match = re.search(r"(/uploads/[^\s\"']+\.pdf)", resp.text)

    if match:
        pdf_url = urljoin(base_url, match.group(1))
    else:
        soup = BeautifulSoup(resp.text, "html.parser")
        link = soup.find("a", href=re.compile(r"\.pdf(?:$|\?)", re.IGNORECASE))
        if not link:
            raise RuntimeError(f"[{prefeitura['id']}] PDF nao encontrado na edicao {edition_id}")
        pdf_url = urljoin(base_url, link["href"])

    page_text = BeautifulSoup(resp.text, "html.parser").get_text(separator=" ", strip=True)
    page_date = _extract_date_from_text(page_text)
    pdf_date = _extract_date_from_pdf_url(pdf_url)

    if page_date and pdf_date and page_date != pdf_date:
        log.warning(
            "[%s] Data da pagina (%s) difere da data do PDF (%s); usando data do PDF.",
            prefeitura["id"],
            page_date,
            pdf_date,
        )

    return pdf_url, pdf_date or page_date


def download_pdf(pdf_url: str, dest_path: Path) -> Path:
    """Downloads and validates the PDF."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    log.info("Baixando PDF -> %s", dest_path)

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=120) as client:
        with client.stream("GET", pdf_url) as resp:
            resp.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

    size = dest_path.stat().st_size
    if size < 1024:
        dest_path.unlink(missing_ok=True)
        raise RuntimeError(f"PDF baixado parece invalido: {size} bytes")

    with open(dest_path, "rb") as f:
        header = f.read(5)
    if header != b"%PDF-":
        dest_path.unlink(missing_ok=True)
        raise RuntimeError("Arquivo baixado nao tem assinatura de PDF")

    log.info("Download OK: %.1f KB", size / 1024)
    return dest_path


def fetch_prefeitura(prefeitura: dict, output_dir: Path) -> dict:
    """
    Fluxo completo para uma prefeitura.
    Retorna metadados da edicao baixada.
    """
    tipo = prefeitura.get("tipo", "doweb")

    if tipo == "doweb":
        edition_id, listing_date = _get_latest_edition_doweb(prefeitura)
        pdf_url, edition_date = _get_pdf_url_doweb(prefeitura, edition_id)
    else:
        raise NotImplementedError(f"Tipo '{tipo}' ainda nao suportado para {prefeitura['id']}")

    date_str = edition_date or listing_date
    if not date_str:
        raise RuntimeError(f"[{prefeitura['id']}] Nao foi possivel identificar a data real da edicao {edition_id}")

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
