#!/usr/bin/env python3
"""
Scraper universel - Annuaire des entreprises industrielles tunisiennes
Source: https://www.tunisieindustrie.nat.tn/fr/dbi.asp

CORRECTIONS APPLIQUÉES :
  1. CODES SECTEURS CORRIGÉS — les codes originaux étaient tous faux.
     Le site utilise : 01=Mécaniques, 02=Textile, 03=Matériaux,
     04=Chimiques, 05=Agro-alimentaires, 06=Cuir, 07=Bois,
     08=Électriques/Électroniques, 09=Diverses.
  2. get_session() : POST initial pour initialiser la session ASP.NET.
  3. fetch_list_page() : page 1 toujours en POST pour tous les secteurs.
  4. Re-tentatives automatiques sur les requêtes en échec.
"""

import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime
import time, re, os, sys

# ── Output ─────────────────────────────────────────────────────────────────────
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "entreprises_industrielles_ALL.xlsx")

LIST_URL    = "https://www.tunisieindustrie.nat.tn/fr/dbi.asp"
DETAIL_BASE = "https://www.tunisieindustrie.nat.tn/fr/"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Referer":         LIST_URL,
}

# ── SECTORS — codes verified directly from the site's HTML form ───────────────
# Format: (code, sheet_name, label, header_color, alt_row_color)
#
# REAL codes extracted from dbi.asp HTML (confirmed via debug_06.html):
#   01 = Industries mécaniques et métallurgiques
#   02 = Industries textiles et habillement
#   03 = Industries des matériaux de construction, céramique et verre
#   04 = Industries chimiques
#   05 = Industries agro-alimentaires
#   06 = Industries du cuir et de la chaussure
#   07 = Industries du bois, du liège et de l'ameublement
#   08 = Industries électriques, électroniques et de l'électroménager
#   09 = Industries diverses
SECTORS = [
    ("01", "Ind. Mécaniques",        "Industries mécaniques et métallurgiques",                       "1F4E79", "EBF3FB"),
    ("02", "Ind. Textile",           "Industries textiles et habillement",                            "6C3483", "F5EEF8"),
    ("03", "Matériaux Construction", "Industries des matériaux de construction, céramique et verre",  "7B3F00", "FDF3E7"),
    ("04", "Ind. Chimiques",         "Industries chimiques",                                          "145A32", "EAFAF1"),
    ("05", "Agro-Alimentaires",      "Industries agro-alimentaires",                                  "922B21", "FDEDEC"),
    ("06", "Ind. Cuir-Chaussures",   "Industries du cuir et de la chaussure",                         "515A5A", "F2F3F4"),
    ("07", "Ind. Bois-Liège",        "Industries du bois, du liège et de l'ameublement",              "784212", "FEF9E7"),
    ("08", "Ind. Électriques",       "Industries électriques, électroniques et de l'électroménager",  "1A5276", "EAF2FF"),
    ("09", "Ind. Diverses",          "Industries diverses",                                           "4D5656", "F2F3F4"),
]

FIELDS = [
    "Dénomination", "Raison Sociale", "Responsable", "Secteur",
    "Activités", "Produits", "Adresse usine", "District",
    "Gouvernorat", "Délégation", "Téléphone siège/usine", "Fax siège/usine",
    "E-mail", "URL", "Régime", "Pays du Participant Etranger",
    "Entrée en production", "Capital en DT", "Emploi",
]
COLUMNS    = FIELDS + ["source_url"]
COL_LABELS = {
    "Dénomination":                 "Dénomination",
    "Raison Sociale":               "Raison Sociale",
    "Responsable":                  "Responsable",
    "Secteur":                      "Secteur",
    "Activités":                    "Activités",
    "Produits":                     "Produits",
    "Adresse usine":                "Adresse Usine",
    "District":                     "District",
    "Gouvernorat":                  "Gouvernorat",
    "Délégation":                   "Délégation",
    "Téléphone siège/usine":        "Téléphone",
    "Fax siège/usine":              "Fax",
    "E-mail":                       "E-mail",
    "URL":                          "Site Web",
    "Régime":                       "Régime",
    "Pays du Participant Etranger": "Pays Participant Étranger",
    "Entrée en production":         "Entrée en Production",
    "Capital en DT":                "Capital (DT)",
    "Emploi":                       "Emploi",
    "source_url":                   "Source URL",
}
COL_WIDTHS = [25, 28, 25, 28, 35, 40, 40, 35, 18, 18, 25, 18, 32, 32, 22, 28, 20, 15, 10, 45]


def _post_payload(code):
    return {
        "secteur":      code,
        "branche":      "",
        "produit":      "",
        "Denomination": "",
        "District":     "",
        "Gouvernorat":  "",
        "delegation":   "",
        "pays":         "",
        "regime":       "",
        "sex":          "",
        "ent_prd":      "",
        "cap1":         "",
        "cap2":         "",
        "emp1":         "",
        "emp2":         "",
        "action":       "search",
        "order":        "denom",
        "sens":         "asc",
    }


# ══════════════════════════════════════════════════════════════════════════════
#  HTTP helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get(LIST_URL, timeout=30)
    try:
        s.post(LIST_URL, data=_post_payload("01"), timeout=30)
    except Exception as e:
        print(f"  [WARN] Session init POST failed: {e}")
    return s


def _safe_request(fn, retries=3, wait=4):
    for attempt in range(1, retries + 1):
        try:
            resp = fn()
            resp.raise_for_status()
            return resp
        except Exception as e:
            print(f"    [WARN] Attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(wait)
    return None


def fetch_list_page(session, code, page):
    try:
        if page == 1:
            resp = _safe_request(
                lambda: session.post(LIST_URL, data=_post_payload(code), timeout=30)
            )
        else:
            resp = _safe_request(
                lambda: session.get(
                    LIST_URL,
                    params={"action": "search", "pagenum": page},
                    timeout=30,
                )
            )
        if resp is None:
            return None
        resp.encoding = "windows-1252"
        return resp.text
    except Exception as e:
        print(f"    [ERROR] page {page}: {e}")
        return None


def parse_list_page(html):
    soup     = BeautifulSoup(html, "html.parser")
    links    = []
    ident_re = re.compile(r"dbi\.asp\?action=result&(?:amp;)?ident=(\d+)", re.IGNORECASE)

    for tr in soup.find_all("tr", onclick=True):
        m = ident_re.search(tr["onclick"])
        if m:
            url = f"{DETAIL_BASE}dbi.asp?action=result&ident={m.group(1)}"
            if url not in links:
                links.append(url)

    for a in soup.find_all("a", href=True):
        m = ident_re.search(a["href"])
        if m:
            url = f"{DETAIL_BASE}dbi.asp?action=result&ident={m.group(1)}"
            if url not in links:
                links.append(url)

    total_pages = 1
    m = re.search(r'[Pp]age\s+\d+\s+de\s+(\d+)', soup.get_text(" "))
    if m:
        total_pages = int(m.group(1))

    return links, total_pages


def fetch_company(session, url):
    try:
        resp = _safe_request(lambda: session.get(url, timeout=30))
        if resp is None:
            return None
        resp.encoding = "windows-1252"
        return parse_detail(resp.text, url)
    except Exception as e:
        print(f"    [ERROR] {url}: {e}")
        return None


def parse_detail(html, url=""):
    soup = BeautifulSoup(html, "html.parser")
    data = {"source_url": url}

    table = soup.find("table", class_="one")
    if not table:
        for t in soup.find_all("table"):
            if "nomination" in t.get_text().lower():
                table = t
                break
    if not table:
        return data

    for row in table.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 2:
            continue
        key = cols[0].get_text(" ", strip=True).replace("\xa0", " ").strip().rstrip(":")
        td  = cols[1]
        a   = td.find("a")
        if a:
            href = a.get("href", "").strip()
            value = (
                a.get_text(strip=True) if href.startswith("mailto:")
                else (href if href and href != "#" else a.get_text(strip=True))
            )
        else:
            value = td.get_text(" ", strip=True).replace("\xa0", " ").strip()
        data[key] = value

    return data


def normalize(raw):
    record = {}
    lower  = {k.lower(): v for k, v in raw.items()}
    for f in FIELDS:
        if f in raw:
            record[f] = raw[f]
        else:
            fl = f.lower()
            record[f] = next((v for k, v in lower.items() if fl in k or k in fl), "")
    record["source_url"] = raw.get("source_url", "")
    return record


# ══════════════════════════════════════════════════════════════════════════════
#  Scrape one sector
# ══════════════════════════════════════════════════════════════════════════════

def scrape_sector(code, label, delay=1.2):
    session = get_session()

    print(f"\n  Fetching page 1 …")
    html = fetch_list_page(session, code, 1)
    if not html:
        print("  [ERROR] Impossible de contacter le site.")
        return []

    links, total_pages = parse_list_page(html)
    print(f"  → {total_pages} page(s), {len(links)} entreprise(s) page 1")

    if not links:
        debug = f"debug_{code}.html"
        with open(debug, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  ⚠ Aucun lien trouvé → {debug}")
        return []

    all_links = list(links)
    for page in range(2, total_pages + 1):
        print(f"  Page {page}/{total_pages} …", end=" ", flush=True)
        time.sleep(delay)
        html = fetch_list_page(session, code, page)
        if html:
            pl, _ = parse_list_page(html)
            all_links.extend(pl)
            print(f"+{len(pl)}")
        else:
            print("SKIP")

    all_links = list(dict.fromkeys(all_links))
    print(f"  Total unique : {len(all_links)} entreprises")

    records = []
    for i, url in enumerate(all_links, 1):
        print(f"  [{i}/{len(all_links)}] {url}")
        raw = fetch_company(session, url)
        if raw:
            records.append(normalize(raw))
        time.sleep(delay)

    return records


# ══════════════════════════════════════════════════════════════════════════════
#  Excel
# ══════════════════════════════════════════════════════════════════════════════

def _write_data_sheet(ws, records, hdr_color, alt_color):
    hdr_font  = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    hdr_fill  = PatternFill("solid", start_color=hdr_color)
    hdr_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell_font = Font(name="Arial", size=10)
    alt_fill  = PatternFill("solid", start_color=alt_color)
    thin      = Side(style="thin", color="CCCCCC")
    border    = Border(left=thin, right=thin, top=thin, bottom=thin)

    for ci, col in enumerate(COLUMNS, 1):
        c = ws.cell(1, ci, COL_LABELS.get(col, col))
        c.font, c.fill, c.alignment, c.border = hdr_font, hdr_fill, hdr_align, border
    ws.row_dimensions[1].height = 35

    for ri, rec in enumerate(records, 2):
        fill = alt_fill if ri % 2 == 0 else None
        for ci, col in enumerate(COLUMNS, 1):
            c = ws.cell(ri, ci, rec.get(col, ""))
            c.font      = cell_font
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border    = border
            if fill:
                c.fill = fill

    for ci, w in enumerate(COL_WIDTHS, 1):
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.freeze_panes = "A2"


def build_summary_sheet(wb, summary_data):
    name = "📊 Résumé Global"
    if name in wb.sheetnames:
        del wb[name]
    ws = wb.create_sheet(name, 0)

    ws.merge_cells("A1:E1")
    t = ws["A1"]
    t.value     = "Annuaire des Entreprises Industrielles — Tunisie"
    t.font      = Font(name="Arial", bold=True, size=16, color="FFFFFF")
    t.fill      = PatternFill("solid", start_color="1C2833")
    t.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 40

    ws.merge_cells("A2:E2")
    sub = ws["A2"]
    sub.value     = f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}  •  Source : {LIST_URL}"
    sub.font      = Font(name="Arial", italic=True, size=10, color="888888")
    sub.alignment = Alignment(horizontal="center")

    headers = ["Code", "Secteur", "Nb Entreprises", "Feuille Excel", "Statut"]
    h_font  = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    h_fill  = PatternFill("solid", start_color="2C3E50")
    h_align = Alignment(horizontal="center", vertical="center")
    thin    = Side(style="thin", color="AAAAAA")
    border  = Border(left=thin, right=thin, top=thin, bottom=thin)

    for ci, h in enumerate(headers, 1):
        c = ws.cell(4, ci, h)
        c.font, c.fill, c.alignment, c.border = h_font, h_fill, h_align, border
    ws.row_dimensions[4].height = 28

    total_companies = 0
    for ri, (code, sheet, label, hdr_color, _, count, status) in enumerate(summary_data, 5):
        alt = PatternFill("solid", start_color="F2F3F4") if ri % 2 == 0 else None
        row_vals = [code, label, count, sheet, status]
        for ci, val in enumerate(row_vals, 1):
            c = ws.cell(ri, ci, val)
            c.font      = Font(name="Arial", size=11,
                               color=hdr_color if ci == 2 else "000000",
                               bold=(ci == 2))
            c.alignment = Alignment(
                horizontal="center" if ci in (1, 3, 5) else "left",
                vertical="center"
            )
            c.border = border
            if alt:
                c.fill = alt
        total_companies += count if isinstance(count, int) else 0

    tr = len(summary_data) + 5
    ws.cell(tr, 1, "TOTAL").font = Font(name="Arial", bold=True, size=12)
    ws.cell(tr, 3, total_companies).font = Font(name="Arial", bold=True, size=12, color="1F4E79")
    ws.cell(tr, 3).alignment = Alignment(horizontal="center")
    for ci in range(1, 6):
        ws.cell(tr, ci).border = border
        ws.cell(tr, ci).fill   = PatternFill("solid", start_color="D5E8F5")

    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 55
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 28
    ws.column_dimensions["E"].width = 14
    ws.row_dimensions[tr].height = 28


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

def main(delay=1.2):
    print("=" * 70)
    print("  Scraper Universel – Annuaire des Entreprises Industrielles Tunisie")
    print(f"  {len(SECTORS)} secteurs  •  Output → {OUTPUT_PATH}")
    print("=" * 70)

    if os.path.exists(OUTPUT_PATH):
        wb = load_workbook(OUTPUT_PATH)
        print(f"\nWorkbook existant chargé.")
    else:
        wb = Workbook()
        if "Sheet" in wb.sheetnames:
            del wb["Sheet"]

    summary_data = []

    for code, sheet_name, label, hdr_color, alt_color in SECTORS:
        print(f"\n{'━'*70}")
        print(f"  ▶  Secteur {code} — {label}")
        print(f"{'━'*70}")

        try:
            records = scrape_sector(code, label, delay=delay)

            if records:
                if sheet_name in wb.sheetnames:
                    del wb[sheet_name]
                ws = wb.create_sheet(title=sheet_name)
                _write_data_sheet(ws, records, hdr_color, alt_color)
                status = "✅ OK"
                count  = len(records)
                print(f"  ✅  {count} entreprises → feuille '{sheet_name}'")
            else:
                status = "⚠ Vide"
                count  = 0
                print(f"  ⚠  Aucune donnée pour ce secteur.")

        except Exception as e:
            print(f"  [ERREUR] {e}")
            status = "❌ Erreur"
            count  = 0

        summary_data.append((code, sheet_name, label, hdr_color, alt_color,
                              count, status))

        build_summary_sheet(wb, summary_data)
        wb.save(OUTPUT_PATH)
        print(f"  💾  Sauvegarde intermédiaire OK")

    build_summary_sheet(wb, summary_data)
    wb.save(OUTPUT_PATH)

    total = sum(d[5] for d in summary_data if isinstance(d[5], int))
    print(f"\n{'='*70}")
    print(f"  ✅  Terminé ! {total} entreprises scrapées au total.")
    print(f"  📁  Fichier → {OUTPUT_PATH}")
    print(f"{'='*70}")


if __name__ == "__main__":
    delay = float(sys.argv[1]) if len(sys.argv) > 1 else 1.2
    main(delay=delay)