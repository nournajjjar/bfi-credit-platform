# backend/routes/dashboard.py
"""
Dashboard API — aggregated statistics from reports database
"""
from fastapi import APIRouter, HTTPException
from Database import get_conn
import json

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _safe_json(val):
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    if isinstance(val, (bytes, memoryview)):
        try:
            val = val.decode("utf-8")
        except Exception:
            return {}
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return {}
    return {}


@router.get("/stats")
async def get_dashboard_stats():
    try:
        conn = get_conn()
        cur  = conn.cursor()

        # ── Companies per sector from APII tables ──────────────────────────
        sector_labels = {
            'secteur_01_mecanique_electrique': 'Mécanique & Électrique',
            'secteur_02_chimique': 'Chimique',
            'secteur_03_materiaux_construction': 'Matériaux Construction',
            'secteur_04_textile': 'Textile',
            'secteur_05_agro_alimentaire': 'Agro-alimentaire',
            'secteur_agro_alimentaires': 'Agro-alimentaires',
            'secteur_ind_bois_li_ge': 'Bois & Liège',
            'secteur_ind_chimiques': 'Industries Chimiques',
            'secteur_ind_cuir_chaussures': 'Cuir & Chaussures',
            'secteur_ind_diverses': 'Industries Diverses',
            'secteur_ind_lectriques': 'Industries Électriques',
            'secteur_ind_m_caniques': 'Industries Mécaniques',
            'secteur_ind_textile': 'Textile',
            'secteur_mat_riaux_construction': 'Matériaux Construction',
        }
        secteurs_db = []
        for tbl, label in sector_labels.items():
            try:
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                count = cur.fetchone()[0]
                if count > 0:
                    existing = next((s for s in secteurs_db if s["name"] == label), None)
                    if existing:
                        existing["count"] += count
                    else:
                        secteurs_db.append({"name": label, "count": count})
            except Exception:
                pass
        secteurs_db = sorted(secteurs_db, key=lambda x: -x["count"])

        # ── Companies per gouvernorat from all sector tables ───────────────
        sector_tables = list(sector_labels.keys())
        all_gov = {}
        for tbl in sector_tables:
            try:
                cur.execute(f"SELECT gouvernorat FROM {tbl} WHERE gouvernorat IS NOT NULL AND gouvernorat != ''")
                for row in cur.fetchall():
                    g = (row[0] or "").strip()
                    if g:
                        all_gov[g] = all_gov.get(g, 0) + 1
            except Exception:
                pass
        gouvernorats_db = sorted(
            [{"name": k, "count": v} for k, v in all_gov.items()],
            key=lambda x: -x["count"]
        )

        # ── All reports ──────────────────────────────────────────────────
        cur.execute("SELECT id, company_name, generated_at, original_data FROM reports ORDER BY generated_at DESC")
        rows = cur.fetchall()

        total_reports   = len(rows)
        gouvernorats    = {}
        secteurs        = {}
        verdicts        = {}
        scores_by_sec   = {}
        timeline        = {}
        companies       = []

        for row in rows:
            report_id    = str(row[0])
            company_name = row[1]
            generated_at = row[2]
            data         = _safe_json(row[3])
            company      = data.get("company", {}) or {}
            rapport      = data.get("generated_report", {}) or {}
            meta         = rapport.get("_meta", {}) or {}

            # Debug: print what we actually parsed (remove after confirming fix)
            print(f"[DASHBOARD DEBUG] {company_name}: data_keys={list(data.keys())} "
                  f"rapport_keys={list(rapport.keys()) if isinstance(rapport, dict) else type(rapport)}")

            # Timeline
            if generated_at:
                day = generated_at.strftime("%Y-%m-%d")
                timeline[day] = timeline.get(day, 0) + 1

            # Gouvernorat
            gov = company.get("gouvernorat") or "Inconnu"
            gouvernorats[gov] = gouvernorats.get(gov, 0) + 1

            # Secteur
            sec = company.get("label_secteur") or "Inconnu"
            secteurs[sec] = secteurs.get(sec, 0) + 1

            # Verdict
            s8 = rapport.get("s8_synthese_verdict")
            if isinstance(s8, dict):
                verdict = s8.get("verdict_credit") or s8.get("profil_risque") or "Inconnu"
            elif isinstance(s8, str):
                try:
                    s8_parsed = json.loads(s8)
                    verdict = s8_parsed.get("verdict_credit") or s8_parsed.get("profil_risque") or "Inconnu"
                except Exception:
                    verdict = "Inconnu"
            else:
                verdict = "Inconnu"
            verdicts[verdict] = verdicts.get(verdict, 0) + 1

            companies.append({
                "report_id":    report_id,
                "company_name": company_name,
                "denomination": company.get("denomination", company_name),
                "gouvernorat":  gov,
                "secteur":      sec,
                "verdict":      verdict,
                "generated_at": generated_at.isoformat() if generated_at else None,
                "emploi":       company.get("emploi"),
                "capital":      company.get("capital"),
                "regime":       company.get("regime"),
            })

        # ── Section scores from section_versions ───────────────────────────
        cur.execute("""
            SELECT section_key, AVG(version), COUNT(*)
            FROM section_versions
            GROUP BY section_key
            ORDER BY section_key
        """)
        for r in cur.fetchall():
            scores_by_sec[r[0]] = {"avg": round(float(r[1]), 2), "count": int(r[2])}

        # Total sections revised (version > 1)
        cur.execute("SELECT COUNT(*) FROM section_versions WHERE version > 1")
        revisions = cur.fetchone()[0]

        # Total versions
        cur.execute("SELECT COUNT(*) FROM section_versions")
        total_versions = cur.fetchone()[0]

        # Top companies by average section version (proxy for revision activity)
        cur.execute("""
            SELECT r.company_name, r.id, AVG(sv.version) as avg_score, COUNT(sv.id) as sections
            FROM reports r
            JOIN section_versions sv ON sv.report_id = r.id
            GROUP BY r.id, r.company_name
            ORDER BY avg_score DESC
            LIMIT 10
        """)
        top_companies_scores = [
            {"company": row[0], "report_id": str(row[1]),
             "avg_score": round(float(row[2]), 2), "sections": int(row[3])}
            for row in cur.fetchall()
        ]

        cur.close()
        conn.close()

        timeline_list = sorted(
            [{"date": k, "count": v} for k, v in timeline.items()],
            key=lambda x: x["date"]
        )
        gov_list = sorted([{"name": k, "count": v} for k, v in gouvernorats.items()], key=lambda x: -x["count"])
        sec_list = sorted([{"name": k, "count": v} for k, v in secteurs.items()],    key=lambda x: -x["count"])
        ver_list = sorted([{"name": k, "count": v} for k, v in verdicts.items()],    key=lambda x: -x["count"])

        return {
            "success": True,
            "total_reports":    total_reports,
            "total_revisions":  int(revisions),
            "total_versions":   int(total_versions),
            "gouvernorats":     gouvernorats_db,
            "gouvernorats_reports": gov_list,
            "secteurs_db": secteurs_db,
            "secteurs":         sec_list[:10],
            "verdicts":         ver_list,
            "scores_by_section": scores_by_sec,
            "timeline":         timeline_list,
            "companies":        companies,
            "top_companies_scores": top_companies_scores,
        }

    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, detail=str(e))