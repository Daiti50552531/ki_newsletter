#!/usr/bin/env python3
"""
Täglicher KI-Newsletter – powered by Gemini 2.5 Flash + Google Search Grounding
Verschickt täglich via Gmail SMTP, getriggert durch GitHub Actions.
Nur Standard-Library – keine externen Pakete nötig.
"""

import json
import os
import re
import smtplib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Credentials aus Umgebungsvariablen ────────────────────────────────────────
GEMINI_API_KEY     = os.environ["GEMINI_API_KEY"]
GMAIL_ADDRESS      = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]

# Mehrere Empfänger möglich: kommagetrennt, z.B. "a@gmail.com,b@web.de"
RECIPIENTS = [e.strip() for e in os.environ["RECIPIENT_EMAIL"].split(",") if e.strip()]

GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

def gemini_url(model: str) -> str:
    return (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={GEMINI_API_KEY}"
    )

TODAY = datetime.now().strftime("%d.%m.%Y")


# ── Prompt ────────────────────────────────────────────────────────────────────
PROMPT = f"""Du bist Chefredakteur eines deutschsprachigen KI-Newsletters für Builder, Entwickler und Indie-Hacker.
Heute ist der {TODAY}. Nutze Google Search zur Recherche. Alle Zusammenfassungen auf Deutsch.

--- AKTUALITAET ---
Keine Quelle darf aelter als 3 Tage sein. Ausnahme: Podcast-Empfehlungen duerfen aelter sein wenn hochrelevant.

--- BLACKLIST (niemals verwenden) ---
AInauten, TAAFT, Doppelgaenger Newsletter/Podcast, AI Daily Brief

--- QUELLEN (englischsprachige bevorzugen) ---
News: TechCrunch, The Verge, Wired, Ars Technica, MIT Technology Review, Bloomberg Technology, The Information, VentureBeat, Reuters Technology
Communities: Hacker News, Reddit (r/LocalLLaMA, r/machinelearning, r/artificial, r/SaaS), DEV Community, GitHub Trending
Builder: Indie Hackers, Product Hunt, Papers With Code, Hugging Face Blog, Import AI, Stratechery
Asien: Quellen zu DeepSeek, Qwen und anderen asiatischen Open-Source-Modellen
Podcasts (fuer Sektion 2 und als News-Quellen): Lex Fridman, Hard Fork NYT, Practical AI, Latent Space, No Priors, TWIML, Dwarkesh Podcast, BG2 Pod

--- NEWS SCORING (nur aufnehmen wenn Builder-relevant) ---
AUFNEHMEN: Neue Modell-Releases, Open-Source-Durchbrueche, Agenten-Framework-Updates, neue API-Faehigkeiten, Hardware fuer KI, strategische Moves die das Oekosystem verschieben
ABLEHNEN: Reine Aktienkurse und Finanzmeldungen, oberflaechliches PR ohne techn. Substanz

--- BUILDER-PROJEKTE SUCHEN (fuer Sektion 3) ---
Suche aktiv nach: "MRR", "Micro-SaaS", "built with Gemini", "built with Claude Code", "API integration", "Automated workflow", "indie hacker", "side project"
Pro Projekt extrahieren: Was ist das Problem? Wie wurde es gebaut (Tech-Stack)? Was wird verdient?

--- AUSGABE ---
Gib ausschliesslich gueltiges JSON zurueck, ohne Markdown-Formatierung, ohne Erklaerungen:

{{
  "top_news": [
    {{
      "titel": "Praegnanter deutscher Titel",
      "zusammenfassung": "2-3 Saetze auf Deutsch, Builder-Perspektive, keine Buzzwords",
      "quelle": "Name der Quelle",
      "url": "https://direktlink-zum-artikel/nicht-zur-homepage",
      "datum": "TT.MM.YYYY"
    }}
  ],
  "podcast": {{
    "episoden_titel": "...",
    "podcast_name": "...",
    "warum_hoeren": "2-3 Saetze auf Deutsch",
    "url": "https://...",
    "datum": "TT.MM.YYYY"
  }},
  "inspiration": [
    {{
      "projekt_name": "...",
      "beschreibung": "2-3 Saetze: Problem, Tech-Stack, Monetarisierung",
      "tools": "z.B. Gemini API + Python oder Claude Code + Zapier",
      "quelle": "Name der Quelle",
      "url": "https://...",
      "datum": "TT.MM.YYYY"
    }}
  ],
  "gemini_tipp": {{
    "titel": "...",
    "kategorie": "Produktivitaet|Coding|Recherche|Content",
    "beschreibung": "3-5 Saetze mit konkretem Beispiel und Prompt-Vorlage"
  }}
}}

REGELN:
- top_news: GENAU 5 Eintraege, mindestens 3 aus englischsprachigen Quellen
- inspiration: 3 BIS 5 Eintraege, mindestens 1 mit Gemini gebaut, mindestens 1 mit Claude Code
- Alle Daten im Format TT.MM.YYYY
- URLs direkt zum Artikel (nicht Homepage), nur verifizierte URLs, Fallback: https://www.google.com/search?q=titel+quelle
"""


# ── Gemini API Call (mit Retry + Model-Fallback bei 503) ─────────────────────
def call_gemini() -> dict:
    payload = {
        "tools": [{"google_search": {}}],
        "contents": [{"role": "user", "parts": [{"text": PROMPT}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
        },
    }
    data = json.dumps(payload).encode("utf-8")

    for model in GEMINI_MODELS:
        print(f"Versuche Modell: {model} ...")
        for attempt in range(3):
            req = urllib.request.Request(
                gemini_url(model), data=data,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    print(f"  ✓ Antwort von {model}")
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 503 and attempt < 2:
                    wait = 20 * (attempt + 1)
                    print(f"  503 – warte {wait}s, Versuch {attempt + 2}/3 ...")
                    time.sleep(wait)
                elif e.code == 503:
                    print(f"  {model} dauerhaft nicht erreichbar – wechsle Modell.")
                    break
                else:
                    raise
    raise RuntimeError("Alle Gemini-Modelle nicht erreichbar (503).")


def extract_json(text: str) -> dict:
    # Markdown-Wrapper entfernen
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    # JSON-Block extrahieren
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("Kein JSON gefunden. Antwort-Anfang:\n" + text[:300])
    json_str = match.group(0)
    # Direkt parsen
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    # Steuerzeichen entfernen die JSON brechen
    json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', json_str)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON-Fehler nach Bereinigung: {e}\nJSON-Anfang:\n{json_str[:400]}")


def get_newsletter_data() -> dict:
    for attempt in range(3):
        response = call_gemini()
        candidates = response.get("candidates", [])
        if not candidates:
            raise ValueError(f"Keine Candidates: {json.dumps(response)[:300]}")
        parts = candidates[0].get("content", {}).get("parts", [])
        raw_text = "".join(p.get("text", "") for p in parts)
        if raw_text.strip():
            return extract_json(raw_text)
        # Leere Antwort trotz STOP – nochmal versuchen
        reason = candidates[0].get("finishReason", "?")
        if attempt < 2:
            print(f"Gemini leere Antwort (Finish: {reason}) – Versuch {attempt + 2}/3 ...")
            time.sleep(15)
        else:
            raise ValueError(f"Gemini liefert nach 3 Versuchen keinen Text. Finish-Reason: {reason}")


# ── URL-Validierung ──────────────────────────────────────────────────────────
def validate_url(url: str, title: str = "", source: str = "") -> str:
    """Prüft ob eine URL erreichbar ist. Gibt Fallback-Suche-URL zurück falls nicht."""
    if not url or not url.startswith("http"):
        query = urllib.parse.quote(f"{title} {source}")
        return f"https://www.google.com/search?q={query}"
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            if r.status < 400:
                return url
    except Exception:
        pass
    # Fallback: Google-Suche nach Titel + Quelle
    query = urllib.parse.quote(f"{title} {source}")
    return f"https://www.google.com/search?q={query}"


def validate_all_urls(data: dict) -> dict:
    """Validiert alle URLs im Newsletter und ersetzt kaputte durch Suche-Links."""
    print("Validiere URLs ...")
    for item in data.get("top_news", []):
        original = item.get("url", "")
        fixed = validate_url(original, item.get("titel", ""), item.get("quelle", ""))
        if fixed != original:
            print(f"  ⚠ URL ersetzt: {original[:60]} → Google-Suche")
        item["url"] = fixed

    pod = data.get("podcast", {})
    pod["url"] = validate_url(pod.get("url", ""),
                               pod.get("episoden_titel", ""), pod.get("podcast_name", ""))

    for item in data.get("inspiration", []):
        original = item.get("url", "")
        fixed = validate_url(original, item.get("projekt_name", ""), item.get("quelle", ""))
        if fixed != original:
            print(f"  ⚠ URL ersetzt: {original[:60]} → Google-Suche")
        item["url"] = fixed

    return data


# ── Design-Konstanten (Modern Playful) ────────────────────────────────────────
FONT   = "'Helvetica Neue',Helvetica,Arial,sans-serif"
C_BG   = "#eef2ff"          # Helles Indigo-Blau
C_CARD = "#ffffff"
C_H1   = "#4f46e5"          # Indigo-Header-Akzent
C_HDR  = "#1e1b4b"          # Sehr dunkles Indigo für Header-BG
C_TEXT = "#1e293b"
C_MUTE = "#64748b"
C_BDR  = "#e2e8f0"

# Sektionsfarben
SEC = {
    "news":    {"emoji": "🚀", "color": "#4f46e5", "light": "#eef2ff"},
    "podcast": {"emoji": "🎙️", "color": "#f43f5e", "light": "#fff1f2"},
    "insp":    {"emoji": "💡", "color": "#059669", "light": "#ecfdf5"},
    "tipp":    {"emoji": "✨", "color": "#d97706", "light": "#fffbeb"},
}


def build_html(data: dict) -> str:
    top_news    = data.get("top_news", [])
    podcast     = data.get("podcast", {})
    inspiration = data.get("inspiration", [])
    tipp        = data.get("gemini_tipp", {})

    def badge(text: str, color: str, bg: str) -> str:
        return (f'<span style="display:inline-block;background:{bg};color:{color};'
                f'font-family:{FONT};font-size:11px;font-weight:700;letter-spacing:.5px;'
                f'text-transform:uppercase;padding:3px 10px;border-radius:20px;">{text}</span>')

    def section_title(s: dict, title: str) -> str:
        return f"""
        <tr><td style="padding:36px 0 20px;">
          <table cellpadding="0" cellspacing="0"><tr>
            <td style="background:{s['color']};border-radius:12px;
                       padding:6px 14px;vertical-align:middle;">
              <span style="font-family:{FONT};font-size:13px;font-weight:800;
                           color:#fff;letter-spacing:.5px;text-transform:uppercase;">
                {s['emoji']}&nbsp; {title}
              </span>
            </td>
          </tr></table>
        </td></tr>"""

    def news_block(item: dict, idx: int) -> str:
        return f"""
        <tr><td style="padding:0 0 20px;">
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="border-left:3px solid {SEC['news']['color']};padding-left:14px;">
            <tr><td style="padding:0 0 5px;">
              <span style="font-family:{FONT};font-size:22px;font-weight:900;
                           color:{SEC['news']['color']};opacity:.25;line-height:1;">
                {str(idx).zfill(2)}
              </span>
              &nbsp;
              <span style="font-family:{FONT};font-size:11px;color:{C_MUTE};">
                {item.get('datum','')} &middot; {item.get('quelle','')}
              </span>
            </td></tr>
            <tr><td style="padding:0 0 7px;">
              <a href="{item.get('url','#')}"
                 style="font-family:{FONT};font-size:16px;font-weight:700;
                        color:{C_TEXT};text-decoration:none;line-height:1.4;">
                {item.get('titel','')}
              </a>
            </td></tr>
            <tr><td style="padding:0 0 8px;">
              <span style="font-family:{FONT};font-size:14px;color:#475569;line-height:1.7;">
                {item.get('zusammenfassung','')}
              </span>
            </td></tr>
            <tr><td style="padding:0 0 20px;border-bottom:1px solid {C_BDR};">
              <a href="{item.get('url','#')}"
                 style="font-family:{FONT};font-size:12px;font-weight:700;
                        color:{SEC['news']['color']};text-decoration:none;">
                Weiterlesen &rarr;
              </a>
            </td></tr>
          </table>
        </td></tr>
        <tr><td style="padding:0 0 4px;"></td></tr>"""

    def insp_block(item: dict, idx: int) -> str:
        return f"""
        <tr><td style="padding:0 0 20px;">
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="background:{SEC['insp']['light']};border-radius:10px;">
            <tr><td style="padding:16px 18px 0;">
              <span style="font-family:{FONT};font-size:11px;color:{C_MUTE};">
                {item.get('datum','')} &middot; {item.get('quelle','')}
              </span>
            </td></tr>
            <tr><td style="padding:6px 18px 4px;">
              <a href="{item.get('url','#')}"
                 style="font-family:{FONT};font-size:15px;font-weight:700;
                        color:{C_TEXT};text-decoration:none;line-height:1.4;">
                {item.get('projekt_name','')}
              </a>
            </td></tr>
            <tr><td style="padding:0 18px 8px;">
              {badge('Tools: ' + item.get('tools',''), SEC['insp']['color'], '#d1fae5')}
            </td></tr>
            <tr><td style="padding:0 18px 8px;">
              <span style="font-family:{FONT};font-size:14px;color:#374151;line-height:1.7;">
                {item.get('beschreibung','')}
              </span>
            </td></tr>
            <tr><td style="padding:0 18px 16px;">
              <a href="{item.get('url','#')}"
                 style="font-family:{FONT};font-size:12px;font-weight:700;
                        color:{SEC['insp']['color']};text-decoration:none;">
                Mehr erfahren &rarr;
              </a>
            </td></tr>
          </table>
        </td></tr>"""

    news_rows = "".join(news_block(n, i+1) for i, n in enumerate(top_news))
    insp_rows = "".join(insp_block(n, i+1) for i, n in enumerate(inspiration))
    kat_badge = badge(tipp.get('kategorie', ''), SEC['tipp']['color'], '#fef3c7')

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>KI-Newsletter – {TODAY}</title>
</head>
<body style="margin:0;padding:0;background:{C_BG};">
<table width="100%" cellpadding="0" cellspacing="0" style="background:{C_BG};">
<tr><td align="center" style="padding:28px 16px 48px;">
<table width="620" cellpadding="0" cellspacing="0" style="max-width:620px;width:100%;">

  <!-- HEADER -->
  <tr><td style="background:linear-gradient(135deg,#1e1b4b 0%,#4338ca 100%);
                 border-radius:16px 16px 0 0;padding:32px 36px 28px;">
    <p style="margin:0 0 6px;font-family:{FONT};font-size:11px;color:#a5b4fc;
              letter-spacing:2px;text-transform:uppercase;">
      {TODAY} &nbsp;&middot;&nbsp; Täglich &nbsp;&middot;&nbsp; Kostenlos
    </p>
    <h1 style="margin:0 0 6px;font-family:{FONT};font-size:28px;font-weight:900;
               color:#ffffff;letter-spacing:-.5px;">
      KI-Newsletter 🤖
    </h1>
    <p style="margin:0;font-family:{FONT};font-size:13px;color:#c7d2fe;line-height:1.5;">
      Kuratiert von Gemini 2.5 Flash &middot; Internationale Quellen &middot; Täglich 07:00 Uhr
    </p>
  </td></tr>

  <!-- BODY -->
  <tr><td style="background:{C_CARD};padding:4px 36px 36px;
                 border-radius:0 0 16px 16px;
                 box-shadow:0 8px 30px rgba(79,70,229,.1);">
    <table width="100%" cellpadding="0" cellspacing="0">

      <!-- SEKTION 1: TOP NEWS -->
      {section_title(SEC['news'], 'Top News')}
      {news_rows}

      <!-- SEKTION 2: PODCAST -->
      {section_title(SEC['podcast'], 'Podcast-Empfehlung des Tages')}
      <tr><td style="padding:0 0 32px;">
        <table width="100%" cellpadding="0" cellspacing="0"
               style="background:{SEC['podcast']['light']};border-radius:12px;
                      border:1px solid #fecdd3;">
          <tr><td style="padding:20px 22px;">
            <p style="margin:0 0 5px;font-family:{FONT};font-size:11px;color:{C_MUTE};">
              {podcast.get('datum','')} &middot; {podcast.get('podcast_name','')}
            </p>
            <h3 style="margin:0 0 10px;font-family:{FONT};font-size:16px;font-weight:700;
                       color:{C_TEXT};line-height:1.4;">
              <a href="{podcast.get('url','#')}" style="color:{C_TEXT};text-decoration:none;">
                {podcast.get('episoden_titel','')}
              </a>
            </h3>
            <p style="margin:0 0 12px;font-family:{FONT};font-size:14px;
                      color:#374151;line-height:1.7;">
              {podcast.get('warum_hoeren','')}
            </p>
            <a href="{podcast.get('url','#')}"
               style="font-family:{FONT};font-size:12px;font-weight:700;
                      color:{SEC['podcast']['color']};text-decoration:none;">
              Episode anhören &rarr;
            </a>
          </td></tr>
        </table>
      </td></tr>

      <!-- SEKTION 3: INSPIRATION -->
      {section_title(SEC['insp'], 'Inspiration &amp; Monetarisierung')}
      {insp_rows}

      <!-- SEKTION 4: GEMINI TIPP -->
      {section_title(SEC['tipp'], 'Gemini Pro Tipp')}
      <tr><td style="padding:0 0 16px;">
        <table width="100%" cellpadding="0" cellspacing="0"
               style="background:{SEC['tipp']['light']};border-radius:12px;
                      border:1px solid #fde68a;">
          <tr><td style="padding:20px 22px;">
            <div style="margin-bottom:10px;">{kat_badge}</div>
            <h3 style="margin:0 0 10px;font-family:{FONT};font-size:16px;font-weight:700;
                       color:{C_TEXT};">{tipp.get('titel','')}</h3>
            <p style="margin:0;font-family:{FONT};font-size:14px;
                      color:#374151;line-height:1.7;">{tipp.get('beschreibung','')}</p>
          </td></tr>
        </table>
      </td></tr>

    </table>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="padding:20px 0 0;text-align:center;">
    <p style="margin:0;font-family:{FONT};font-size:12px;color:#94a3b8;line-height:1.9;">
      🤖 Automatisch kuratiert von Gemini 2.5 Flash &middot; GitHub Actions<br>
      Internationale Quellen &middot; Täglich 07:00 Uhr &middot; 0&thinsp;€/Monat
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


# ── E-Mail senden ─────────────────────────────────────────────────────────────
def send_email(subject: str, html_body: str, to: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = to
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        smtp.sendmail(GMAIL_ADDRESS, to, msg.as_string())
    print(f"  ✓ Gesendet an {to}")


def send_error_email(error: Exception):
    subject = f"[KI-Newsletter] Fehler am {TODAY}"
    html = f"""<!DOCTYPE html>
<html><body style="font-family:{FONT};padding:24px;max-width:600px;">
  <h2 style="color:#f43f5e;">KI-Newsletter: Fehler aufgetreten</h2>
  <p><strong>Datum:</strong> {TODAY}</p>
  <p><strong>Fehler:</strong> {type(error).__name__} – {str(error)[:500]}</p>
  <p><a href="https://github.com/daiti50552531/ki_newsletter/actions">GitHub Actions Logs</a></p>
</body></html>"""
    try:
        send_email(subject, html, RECIPIENTS[0])
    except Exception as mail_err:
        print(f"Fehler beim Senden der Fehler-Mail: {mail_err}", file=sys.stderr)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"Starte KI-Newsletter für {TODAY} ...")
    try:
        print("Rufe Gemini API auf (kann bis zu 60 Sekunden dauern) ...")
        data = get_newsletter_data()
        print("Gemini-Antwort erhalten. Validiere URLs ...")
        data = validate_all_urls(data)
        print("Baue HTML-E-Mail ...")
        html = build_html(data)
        subject = f"🤖 KI-Newsletter {TODAY} – Top News, Podcast & Gemini-Tipp"
        print(f"Sende E-Mail an {len(RECIPIENTS)} Empfänger ...")
        for recipient in RECIPIENTS:
            send_email(subject, html, recipient)
        print("Fertig! Newsletter wurde erfolgreich versandt.")
    except Exception as e:
        print(f"FEHLER: {type(e).__name__}: {e}", file=sys.stderr)
        send_error_email(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
