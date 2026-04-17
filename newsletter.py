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
import urllib.error
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

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL   = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
)

TODAY = datetime.now().strftime("%d.%m.%Y")


# ── Prompt ────────────────────────────────────────────────────────────────────
PROMPT = f"""Du bist Chefredakteur eines deutschsprachigen KI-Newsletters.
Heute ist der {TODAY}. Recherchiere mit Google Search aktuelle KI-Nachrichten.

WICHTIG: Verwende NUR Quellen, die maximal 3 Tage alt sind (Ausnahme: Podcast-Empfehlungen).

BLACKLIST – diese Quellen NIEMALS verwenden:
- AInauten (Newsletter/Podcast)
- TAAFT (Newsletter)
- Doppelgänger (Newsletter/Podcast)
- AI Daily Brief (Podcast/Newsletter)

BEVORZUGTE QUELLEN: TechCrunch, The Verge, Ars Technica, MIT Technology Review,
Reddit (r/artificial, r/machinelearning), Hacker News, DEV Community, Indie Hackers,
Product Hunt, Ben's Bites, The Rundown AI, Import AI, Papers With Code,
Hugging Face Blog, VentureBeat, Nischen-Blogs.

Erstelle einen Newsletter mit EXAKT dieser JSON-Struktur (nur JSON, kein Markdown-Wrapper):

{{
  "top_news": [
    {{
      "titel": "...",
      "zusammenfassung": "2-3 Sätze auf Deutsch",
      "quelle": "Name der Quelle",
      "url": "https://...",
      "datum": "TT.MM.YYYY"
    }}
  ],
  "podcast": {{
    "episoden_titel": "...",
    "podcast_name": "...",
    "warum_hoeren": "2-3 Sätze auf Deutsch",
    "url": "https://...",
    "datum": "TT.MM.YYYY"
  }},
  "inspiration": [
    {{
      "projekt_name": "...",
      "beschreibung": "2-3 Sätze (Was, Wie gebaut, was verdient) auf Deutsch",
      "tools": "...",
      "quelle": "Name der Quelle",
      "url": "https://...",
      "datum": "TT.MM.YYYY"
    }}
  ],
  "gemini_tipp": {{
    "titel": "...",
    "kategorie": "Produktivität|Coding|Recherche|Content",
    "beschreibung": "3-5 Sätze mit konkretem Beispiel auf Deutsch"
  }}
}}

REGELN:
- top_news: GENAU 5 Einträge (Themen: Technik, Strategie, Open Source, Hardware)
- inspiration: GENAU 4 Einträge, mindestens 1 Projekt das mit Google Gemini gebaut wurde
- Stil: Deutsch, knackig, informiert, mit Einordnung – kein Marketing-Sprech, kein Buzzword-Bingo
- ALLE URLs müssen echte, funktionierende Links sein
- ALLE Daten im Format TT.MM.YYYY
"""


# ── Gemini API Call ───────────────────────────────────────────────────────────
def call_gemini() -> dict:
    payload = {
        "tools": [{"google_search": {}}],
        "contents": [{"role": "user", "parts": [{"text": PROMPT}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 8192,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        GEMINI_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    text = text.rstrip("`").strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group(0))
    raise ValueError("Kein JSON in der Gemini-Antwort gefunden.\n\nAntwort war:\n" + text[:500])


def get_newsletter_data() -> dict:
    response = call_gemini()
    candidates = response.get("candidates", [])
    if not candidates:
        raise ValueError(f"Keine Candidates in der Gemini-Antwort: {json.dumps(response)[:500]}")
    parts = candidates[0].get("content", {}).get("parts", [])
    raw_text = "".join(p.get("text", "") for p in parts)
    if not raw_text.strip():
        raise ValueError("Gemini hat leeren Text zurückgegeben. Finish-Reason: "
                         + str(candidates[0].get("finishReason")))
    return extract_json(raw_text)


# ── Design-Konstanten (Ainauten-Style) ────────────────────────────────────────
FONT       = "system-ui,-apple-system,'Segoe UI',Arial,sans-serif"
C_BG       = "#f4f4f5"
C_CARD     = "#ffffff"
C_HEADER   = "#18181b"
C_ACCENT   = "#f59e0b"
C_TEXT     = "#18181b"
C_MUTED    = "#71717a"
C_BORDER   = "#e4e4e7"
C_LABEL_BG = "#fef3c7"
C_LABEL_TX = "#92400e"


def build_html(data: dict) -> str:
    top_news    = data.get("top_news", [])
    podcast     = data.get("podcast", {})
    inspiration = data.get("inspiration", [])
    tipp        = data.get("gemini_tipp", {})

    def label(text: str) -> str:
        return (f'<span style="display:inline-block;background:{C_LABEL_BG};color:{C_LABEL_TX};'
                f'font-size:11px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;'
                f'padding:2px 8px;border-radius:4px;font-family:{FONT};">{text}</span>')

    def section_header(num: str, title: str) -> str:
        return f"""
        <tr><td style="padding:36px 0 18px;">
          <p style="margin:0 0 4px;font-family:{FONT};font-size:11px;font-weight:700;
                    color:{C_ACCENT};letter-spacing:1.5px;text-transform:uppercase;
                    border-top:2px solid {C_ACCENT};padding-top:12px;">{num}</p>
          <h2 style="margin:4px 0 0;font-family:{FONT};font-size:22px;font-weight:800;
                     color:{C_TEXT};letter-spacing:-.3px;">{title}</h2>
        </td></tr>"""

    def news_block(item: dict, idx: int) -> str:
        return f"""
        <tr><td style="padding:0 0 24px;border-bottom:1px solid {C_BORDER};margin-bottom:24px;">
          <p style="margin:0 0 6px;font-family:{FONT};font-size:12px;color:{C_MUTED};">
            <strong style="color:{C_ACCENT};">#{idx}</strong>
            &nbsp;&middot;&nbsp;{item.get('datum','')} &middot; {item.get('quelle','')}
          </p>
          <h3 style="margin:0 0 8px;font-family:{FONT};font-size:16px;font-weight:700;
                     line-height:1.4;">
            <a href="{item.get('url','#')}" style="color:{C_TEXT};text-decoration:none;">
              {item.get('titel','')}
            </a>
          </h3>
          <p style="margin:0 0 10px;font-family:{FONT};font-size:14px;color:#3f3f46;
                    line-height:1.7;">{item.get('zusammenfassung','')}</p>
          <a href="{item.get('url','#')}" style="font-family:{FONT};font-size:13px;
             color:{C_ACCENT};font-weight:600;text-decoration:none;">Weiterlesen &rarr;</a>
        </td></tr>
        <tr><td style="padding:0 0 24px;"></td></tr>"""

    def inspiration_block(item: dict) -> str:
        return f"""
        <tr><td style="padding:0 0 24px;border-bottom:1px solid {C_BORDER};">
          <p style="margin:0 0 6px;font-family:{FONT};font-size:12px;color:{C_MUTED};">
            {item.get('datum','')} &middot; {item.get('quelle','')}
          </p>
          <h3 style="margin:0 0 6px;font-family:{FONT};font-size:16px;font-weight:700;
                     line-height:1.4;">
            <a href="{item.get('url','#')}" style="color:{C_TEXT};text-decoration:none;">
              {item.get('projekt_name','')}
            </a>
          </h3>
          <p style="margin:0 0 8px;">{label('Tools: ' + item.get('tools',''))}</p>
          <p style="margin:0 0 10px;font-family:{FONT};font-size:14px;color:#3f3f46;
                    line-height:1.7;">{item.get('beschreibung','')}</p>
          <a href="{item.get('url','#')}" style="font-family:{FONT};font-size:13px;
             color:{C_ACCENT};font-weight:600;text-decoration:none;">Mehr erfahren &rarr;</a>
        </td></tr>
        <tr><td style="padding:0 0 24px;"></td></tr>"""

    news_rows = "".join(news_block(n, i+1) for i, n in enumerate(top_news))
    insp_rows = "".join(inspiration_block(n) for n in inspiration)
    kat_badge = label(tipp.get('kategorie', ''))

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>KI-Newsletter – {TODAY}</title>
</head>
<body style="margin:0;padding:0;background:{C_BG};">
<table width="100%" cellpadding="0" cellspacing="0" style="background:{C_BG};">
  <tr><td align="center" style="padding:24px 16px 40px;">
    <table width="620" cellpadding="0" cellspacing="0" style="max-width:620px;width:100%;">

      <!-- HEADER -->
      <tr>
        <td style="background:{C_HEADER};border-radius:12px 12px 0 0;padding:28px 36px 24px;">
          <p style="margin:0 0 4px;font-family:{FONT};font-size:11px;color:#a1a1aa;
                    letter-spacing:2px;text-transform:uppercase;">
            {TODAY} &middot; Täglich kostenlos
          </p>
          <h1 style="margin:0;font-family:{FONT};font-size:26px;font-weight:800;
                     color:#ffffff;letter-spacing:-.5px;">KI-Newsletter</h1>
          <p style="margin:6px 0 0;font-family:{FONT};font-size:13px;color:#a1a1aa;">
            Kuratiert von Gemini 2.5 Flash &middot; Das Wichtigste aus der KI-Welt
          </p>
        </td>
      </tr>

      <!-- BODY -->
      <tr>
        <td style="background:{C_CARD};padding:8px 36px 32px;border-radius:0 0 12px 12px;
                   box-shadow:0 4px 20px rgba(0,0,0,0.07);">
          <table width="100%" cellpadding="0" cellspacing="0">

            {section_header("Sektion 01", "Top News")}
            {news_rows}

            {section_header("Sektion 02", "Podcast-Empfehlung des Tages")}
            <tr><td style="padding:0 0 32px;">
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;">
                <tr><td style="padding:20px 24px;">
                  <p style="margin:0 0 6px;font-family:{FONT};font-size:12px;color:{C_MUTED};">
                    {podcast.get('datum','')} &middot; {podcast.get('podcast_name','')}
                  </p>
                  <h3 style="margin:0 0 10px;font-family:{FONT};font-size:16px;font-weight:700;
                             line-height:1.4;">
                    <a href="{podcast.get('url','#')}" style="color:{C_TEXT};text-decoration:none;">
                      {podcast.get('episoden_titel','')}
                    </a>
                  </h3>
                  <p style="margin:0 0 12px;font-family:{FONT};font-size:14px;color:#3f3f46;
                            line-height:1.7;">{podcast.get('warum_hoeren','')}</p>
                  <a href="{podcast.get('url','#')}" style="font-family:{FONT};font-size:13px;
                     color:{C_ACCENT};font-weight:600;text-decoration:none;">
                    Episode anhören &rarr;
                  </a>
                </td></tr>
              </table>
            </td></tr>

            {section_header("Sektion 03", "Inspiration &amp; Monetarisierung")}
            {insp_rows}

            {section_header("Sektion 04", "Gemini Pro Tipp")}
            <tr><td style="padding:0 0 16px;">
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="background:{C_BG};border-radius:8px;">
                <tr><td style="padding:20px 24px;">
                  <div style="margin-bottom:10px;">{kat_badge}</div>
                  <h3 style="margin:0 0 10px;font-family:{FONT};font-size:16px;font-weight:700;
                             color:{C_TEXT};">{tipp.get('titel','')}</h3>
                  <p style="margin:0;font-family:{FONT};font-size:14px;color:#3f3f46;
                            line-height:1.7;">{tipp.get('beschreibung','')}</p>
                </td></tr>
              </table>
            </td></tr>

          </table>
        </td>
      </tr>

      <!-- FOOTER -->
      <tr>
        <td style="padding:20px 0 0;text-align:center;">
          <p style="margin:0;font-family:{FONT};font-size:12px;color:#a1a1aa;line-height:1.8;">
            Automatisch kuratiert von Gemini 2.5 Flash &middot; GitHub Actions &middot; {TODAY}<br>
            Vollständig kostenlos &middot; 0&thinsp;€/Monat
          </p>
        </td>
      </tr>

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
  <h2 style="color:{C_ACCENT};">KI-Newsletter: Fehler aufgetreten</h2>
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
        print("Gemini-Antwort erhalten. Baue HTML-E-Mail ...")
        html = build_html(data)
        subject = f"KI-Newsletter {TODAY} – Top News, Podcast & Gemini-Tipp"
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
