#!/usr/bin/env python3
"""Intelligence de prix SEAO : données ouvertes -> rapports par secteur.
Usage:
  python build.py --discover      # affiche la structure réelle des fichiers (1re exécution)
  python build.py --weeks 52      # génère docs/ (public) et premium/ (rapports payants)
"""
import argparse, datetime as dt, html, json, os, re, statistics, sys, unicodedata, urllib.request

CKAN = "https://www.donneesquebec.ca/recherche/api/3/action/package_show?id=systeme-electronique-dappel-doffres-seao"
SITE_NAME = "Prix gagnants QC"          # à changer
SUBSCRIBE_URL = "https://exemple.substack.com/subscribe"  # à remplacer par ton lien d'abonnement payant

SECTORS = {  # ordre = priorité. Mots-clés sans accents, minuscules.
    "Déneigement et entretien": ["deneigement", "entretien", "tonte", "paysag", "balayage"],
    "Informatique et logiciels": ["informatique", "logiciel", "infonuagique", "cloud", "cybersecur", "licence", "reseau", "developpement de"],
    "Construction et génie civil": ["construction", "pavage", "asphalte", "aqueduc", "egout", "reconstruction", "genie civil", "voirie", "trottoir"],
    "Services professionnels": ["services professionnels", "ingenierie", "architect", "surveillance de chantier", "etude", "conseil"],
    "Véhicules et équipements": ["camion", "vehicule", "autobus", "equipement", "tracteur", "remorque"],
    "Fournitures": ["fourniture", "approvisionnement", "achat de", "location de"],
}

def norm(s):
    return unicodedata.normalize("NFD", (s or "").lower()).encode("ascii", "ignore").decode()

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "seao-intel/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def weekly_files(n):
    pkg = json.loads(fetch(CKAN))["result"]
    res = [r for r in pkg["resources"] if re.search(r"hebdo_\d{8}", r.get("url", "")) and r["url"].lower().endswith(".json")]
    res.sort(key=lambda r: re.search(r"hebdo_(\d{8})", r["url"]).group(1))
    return [r["url"] for r in res[-n:]]

def g(d, *path):
    for p in path:
        if isinstance(d, list):
            d = d[0] if d else None
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d

def extract(rel):
    """Lit une release de type OCDS. Tolérant : plusieurs chemins possibles."""
    title = g(rel, "tender", "title") or rel.get("title") or ""
    amount = g(rel, "awards", "value", "amount") or g(rel, "contracts", "value", "amount")
    supplier = g(rel, "awards", "suppliers", "name") or g(rel, "contracts", "suppliers", "name")
    est = g(rel, "tender", "value", "amount")
    status = (g(rel, "tender", "status") or "").lower()
    vals = sorted(round(b["value"], 2) for b in rel.get("bids", []) if isinstance(b.get("value"), (int, float)) and b["value"] > 0)
    n_bids = g(rel, "tender", "numberOfTenderers") or len(vals) or None
    gap = None
    if isinstance(amount, (int, float)) and amount > 0 and round(amount, 2) in vals:
        vals.remove(round(amount, 2))
        if vals:
            gap = (vals[0] - amount) / amount
    return {
        "id": rel.get("ocid") or rel.get("id"),
        "date": (rel.get("date") or "")[:10],
        "title": title.strip(),
        "buyer": g(rel, "buyer", "name") or "",
        "amount": float(amount) if isinstance(amount, (int, float)) and amount > 0 else None,
        "supplier": supplier or "",
        "estimate": float(est) if isinstance(est, (int, float)) and est > 0 else None,
        "open": status in ("active", "planned"),
        "deadline": (g(rel, "tender", "tenderPeriod", "endDate") or "")[:10],
        "adate": (g(rel, "awards", "date") or rel.get("date") or "")[:10],
        "n_bids": n_bids, "gap": gap,
    }

def sector_of(title):
    t = norm(title)
    for name, kws in SECTORS.items():
        if any(k in t for k in kws):
            return name
    return "Autres"

def money(x):
    return f"{x:,.0f}".replace(",", "\u202f") + " $"

def stats(rows):
    amts = [r["amount"] for r in rows if r["amount"]]
    if len(amts) < 5:
        return None
    q = statistics.quantiles(amts, n=4)
    gaps = [r["gap"] for r in rows if r["gap"] is not None and r["gap"] >= 0]
    nbs = [r["n_bids"] for r in rows if r["n_bids"] and r["amount"]]
    wins = {}
    for r in rows:
        if r["supplier"] and r["amount"]:
            w = wins.setdefault(r["supplier"], [0, 0.0])
            w[0] += 1; w[1] += r["amount"]
    return {
        "n": len(amts), "median": statistics.median(amts), "p25": q[0], "p75": q[2],
        "gap": statistics.median(gaps) if len(gaps) >= 5 else None, "bidders": statistics.median(nbs) if len(nbs) >= 5 else None,
        "top": sorted(wins.items(), key=lambda kv: -kv[1][0])[:10],
        "big": sorted([r for r in rows if r["amount"]], key=lambda r: -r["amount"])[:10],
    }

CSS = """:root{--bg:#f4f6f3;--ink:#16231b;--mute:#5a6b60;--card:#fff;--line:#d9e1db;--accent:#1f6b43;--aInk:#fff}
@media(prefers-color-scheme:dark){:root{--bg:#0f1a13;--ink:#e8f1ea;--mute:#98ab9f;--card:#16251b;--line:#27392d;--accent:#5fcf92;--aInk:#06200f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:760px;margin:0 auto;padding:32px 20px 60px}h1{font-size:clamp(1.7rem,5vw,2.4rem);line-height:1.15;letter-spacing:-.02em;margin:0 0 10px}
.lead{color:var(--mute);max-width:60ch}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:14px 0}
.big{font-size:2rem;font-weight:700;color:var(--accent);font-variant-numeric:tabular-nums}a{color:var(--accent)}
.btn{display:inline-block;background:var(--accent);color:var(--aInk);padding:12px 20px;border-radius:10px;text-decoration:none;font-weight:600}
table{border-collapse:collapse;width:100%;font-size:.95rem}td,th{padding:8px 6px;border-bottom:1px solid var(--line);text-align:left}
.lock{border:2px dashed var(--line);color:var(--mute);padding:16px;border-radius:10px}footer{color:var(--mute);font-size:.85rem;margin-top:36px}"""

def page(title, body, desc=""):
    return f"""<!DOCTYPE html><html lang="fr-CA"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc)}"><style>{CSS}</style></head><body><main>{body}
<footer>Source : Système électronique d’appel d’offres (SEAO), données ouvertes du gouvernement du Québec, licence CC-BY 4.0. Analyse indépendante, à titre informatif.</footer></main></body></html>"""

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", norm(s)).strip("-")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=52)
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--discover", action="store_true")
    a = ap.parse_args()
    urls = weekly_files(1 if a.discover else a.weeks)
    if not urls:
        sys.exit("Aucun fichier hebdo trouvé : vérifier le jeu de données sur donneesquebec.ca")
    if a.discover:
        data = json.loads(fetch(urls[-1]))
        rels = data.get("releases", data) if isinstance(data, dict) else data
        print("Fichier :", urls[-1], "| releases :", len(rels))
        print(json.dumps(rels[0], ensure_ascii=False, indent=2)[:4000])
        print("\nextract() ->", extract(rels[0]))
        return
    today = dt.date.today().isoformat()
    cutoff = (dt.date.today() - dt.timedelta(days=30 * a.months)).isoformat()
    best = {}
    for u in urls:
        try:
            data = json.loads(fetch(u))
        except Exception as e:
            print("Ignoré", u, e); continue
        for rel in (data.get("releases", []) if isinstance(data, dict) else data):
            r = extract(rel)
            if not r["title"]:
                continue
            old = best.get(r["id"])
            if old is None or (r["amount"] and not old["amount"]) or (bool(r["amount"]) == bool(old["amount"]) and r["date"] >= old["date"]):
                best[r["id"]] = r
    rows = [r for r in best.values() if (r["amount"] and r["adate"] >= cutoff) or (r["open"] and r["deadline"] >= today)]
    by = {}
    for r in rows:
        by.setdefault(sector_of(r["title"]), []).append(r)
    os.makedirs("docs", exist_ok=True); os.makedirs("premium", exist_ok=True)
    cards, built = "", 0
    for name, rs in sorted(by.items()):
        s = stats(rs)
        if not s or name == "Autres":
            continue
        built += 1; sl = slug(name)
        ratio = f"<p>Un contrat attire en général <strong>{s['bidders']:.0f} soumissionnaires</strong>, et la deuxième meilleure soumission est <strong>{s['gap']*100:.0f} % plus élevée</strong> que celle du gagnant (médiane). C’est la marge que le gagnant aurait pu garder.</p>" if s["gap"] is not None and s["bidders"] else ""
        pub = f"""<p><a href="index.html">← Tous les secteurs</a></p><h1>{html.escape(name)} : quels prix gagnent au Québec ?</h1>
<p class="lead">Analyse de {s['n']} contrats publics attribués. Mise à jour : {today}.</p>
<div class="card"><div>Prix médian d’un contrat</div><div class="big">{money(s['median'])}</div>
<div>La moitié des contrats se situe entre {money(s['p25'])} et {money(s['p75'])}.</div></div>{ratio}
<div class="lock"><strong>Rapport complet (abonnés) :</strong> les 10 entreprises qui gagnent le plus, les 10 plus gros contrats récents avec leurs acheteurs et les appels d’offres ouverts à viser cette semaine.<br><br>
<a class="btn" href="{SUBSCRIBE_URL}">Recevoir le rapport chaque semaine</a></div>"""
        open(f"docs/{sl}.html", "w", encoding="utf-8").write(page(f"{name} : prix gagnants des contrats publics au Québec", pub, f"Prix médian et fourchettes des contrats publics en {name.lower()} au Québec."))
        cards += f'<div class="card"><a href="{sl}.html"><strong>{html.escape(name)}</strong></a><div>Prix médian : {money(s["median"])} · {s["n"]} contrats</div></div>'
        opens = sorted([r for r in rs if r["open"] and r["deadline"] >= today], key=lambda r: r["deadline"])[:15]
        md = [f"# {name} : rapport du {today}", "", f"Contrats analysés : {s['n']}. Prix médian : {money(s['median'])} (de {money(s['p25'])} à {money(s['p75'])}).", "", "## Entreprises qui gagnent le plus", "", "| Entreprise | Contrats | Valeur totale |", "|---|---|---|"]
        if s["gap"] is not None and s["bidders"]:
            md.insert(3, f"Soumissionnaires par contrat (médiane) : {s['bidders']:.0f}. Écart avec la 2e soumission : {s['gap']*100:.0f} %.")
        md += [f"| {n} | {v[0]} | {money(v[1])} |" for n, v in s["top"]]
        md += ["", "## Plus gros contrats récents", "", "| Acheteur | Objet | Gagnant | Montant |", "|---|---|---|---|"]
        md += [f"| {r['buyer']} | {r['title'][:80]} | {r['supplier']} | {money(r['amount'])} |" for r in s["big"]]
        md += ["", "## Appels d’offres ouverts", ""] + [f"- {r['title'][:100]} ({r['buyer']}), date limite : {r['deadline'] or 'n.d.'}" for r in opens]
        open(f"premium/{sl}-{today}.md", "w", encoding="utf-8").write("\n".join(md))
    idx = f"""<h1>{SITE_NAME}</h1><p class="lead">À quel prix les contrats publics du Québec sont-ils réellement gagnés ? Les prix médians par secteur, calculés chaque semaine à partir des données officielles du SEAO.</p>{cards}"""
    open("docs/index.html", "w", encoding="utf-8").write(page(SITE_NAME, idx, "Prix gagnants des contrats publics au Québec, par secteur."))
    print(f"{len(rows)} avis lus, {built} secteurs générés.")

if __name__ == "__main__":
    main()
