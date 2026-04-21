# 💼 A12 News – Wirtschaft, Tourismus, Wissenschaft und Forschung

Automatischer Newscrawler für die **Abteilung 12 Wirtschaft, Tourismus, Wissenschaft und Forschung** des Amts der Steiermärkischen Landesregierung.

🌐 **Website:** https://schalltechnik.github.io/A12-Wirtschaft-News

---

## Kategorien

| | Kategorie | Themen |
|---|---|---|
| 💼 | Wirtschaft & Standort | Unternehmen, Arbeitsmarkt, Investitionen, KMU |
| 🏔️ | Tourismus | Nächtigungen, Tourismusstrategie, Förderungen |
| 🔬 | Wissenschaft & Forschung | TU Graz, Uni Graz, FH Joanneum, Forschungsprojekte |
| 💶 | Förderungen & EU-Programme | EFRE, aws, FFG, Strukturfonds |
| 💡 | Innovation & Digitalisierung | KI, Startups, Green Tech, Technologiecluster |

---

## Technischer Aufbau

```
A12-Wirtschaft-News/
├── fetch_news.py                 ← News-Crawler + Gemini KI-Zusammenfassung
├── README.md
├── .github/
│   └── workflows/
│       └── daily-update.yml     ← Automatischer täglicher Run
└── docs/
    ├── index.html               ← Website (GitHub Pages)
    └── data.json                ← Aktuelle Newsdaten
```

**Läuft automatisch:** täglich um **06:30 Uhr** (Graz) via GitHub Actions

**KI-Zusammenfassungen:** Google Gemini API (`gemini-2.5-flash`)

**Datenquellen:** Google News RSS Feeds

---

## Einrichtung

### 1. Repository klonen / Dateien hochladen
Alle Dateien in ein neues GitHub Repository hochladen.

### 2. GitHub Secret setzen
Repository → **Settings → Secrets and variables → Actions → New repository secret**

| Name | Wert |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API Key |

### 3. GitHub Pages aktivieren
Settings → **Pages** → Branch: `main`, Folder: `/docs` → Save

### 4. Ersten Lauf starten
Actions → **„A12 News Update"** → **„Run workflow"**

---

## Zeitplan (alle Abteilungs-Crawler)

| Projekt | Uhrzeit Graz |
|---|---|
| Lärmschutz News | 05:00 |
| A15 Energie | 05:30 |
| A16 Verkehr | 06:00 |
| **A12 Wirtschaft** | **06:30** |

---

*Powered by Google Gemini AI & GitHub Actions · © Florian Lackner*  
