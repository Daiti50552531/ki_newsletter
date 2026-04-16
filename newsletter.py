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
GEMINI_API_KEY    = os.environ["GEMINI_API_KEY"]
GMAIL_ADDRESS     = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT_EMAIL   = os.environ["RECIPIENT_EMAIL"]

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
    """Robustes JSON-Parsing – funktioniert auch wenn Gemini Markdown-Blöcke mitschickt."""
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


# ── HTML-E-Mail aufbauen ──────────────────────────────────────────────────────
def build_html(data: dict) -> str:
    top_news    = data.get("top_news", [])
    podcast     = data.get("podcast", {})
    inspiration = data.get("inspiration", [])
    tipp        = data.get("gemini_tipp", {})

    def news_block(item: dict) -> str:
        return f"""
        <div style="margin-bottom:28px; padding-bottom:20px; border-bottom:1px solid #e8e0d4;">
          <p style="margin:0 0 6px; font-size:12px; color:#9e8e7e;
                    letter-spacing:1px; text-transform:uppercase;">
            {item.get('datum', '')} &nbsp;·&nbsp; {item.get('quelle', '')}
          </p>
          <h3 style="margin:0 0 8px; font-size:18px; color:#2c2416;
                     font-family:Georgia,serif; line-height:1.35;">
            <a href="{item.get('url', '#')}" style="color:#2c2416; text-decoration:none;">
              {item.get('titel', '')}
            </a>
          </h3>
          <p style="margin:0; font-size:15px; color:#4a3f35; line-height:1.7;">
            {item.get('zusammenfassung', '')}
          </p>
          <p style="margin:8px 0 0;">
            <a href="{item.get('url', '#')}"
               style="font-size:13px; color:#c45d3e; text-decoration:none; font-weight:600;">
              → Artikel lesen
            </a>
          </p>
        </div>"""

    def inspiration_block(item: dict) -> str:
        return f"""
        <div style="margin-bottom:28px; padding-bottom:20px; border-bottom:1px solid #e8e0d4;">
          <p style="margin:0 0 6px; font-size:12px; color:#9e8e7e;
                    letter-spacing:1px; text-transform:uppercase;">
            {item.get('datum', '')} &nbsp;·&nbsp; {item.get('quelle', '')}
            &nbsp;·&nbsp; Tools: {item.get('tools', '')}
          </p>
          <h3 style="margin:0 0 8px; font-size:18px; color:#2c2416;
                     font-family:Georgia,serif; line-height:1.35;">
            <a href="{item.get('url', '#')}" style="color:#2c2416; text-decoration:none;">
              {item.get('projekt_name', '')}
            </a>
          </h3>
          <p style="margin:0; font-size:15px; color:#4a3f35; line-height:1.7;">
            {item.get('beschreibung', '')}
          </p>
          <p style="margin:8px 0 0;">
            <a href="{item.get('url', '#')}"
               style="font-size:13px; color:#c45d3e; text-decoration:none; font-weight:600;">
              → Mehr erfahren
            </a>
          </p>
        </div>"""

    news_html  = "".join(news_block(n) for n in top_news)
    insp_html  = "".join(inspiration_block(n) for n in inspiration)
    badge      = (f'<span style="background:#c45d3e; color:#fff; font-size:11px; '
                  f'padding:2px 8px; border-radius:3px; letter-spacing:1px; '
                  f'text-transform:uppercase;">{tipp.get("kategorie", "")}</span>')

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>KI-Newsletter – {TODAY}</title>
</head>
<body style="margin:0; padding:0; background:#f0ebe3; font-family:Georgia,serif;">

  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0ebe3;">
    <tr><td align="center" style="padding:32px 16px;">

      <table width="640" cellpadding="0" cellspacing="0"
             style="max-width:640px; width:100%; background:#faf6f0;
                    border-radius:8px; overflow:hidden;
                    box-shadow:0 2px 12px rgba(0,0,0,0.08);">

        <!-- HEADER -->
        <tr>
          <td style="background:#2c2416; padding:36px 40px 28px;">
            <p style="margin:0 0 6px; font-size:12px; color:#9e8e7e;
                      letter-spacing:2px; text-transform:uppercase;">
              Täglich · {TODAY}
            </p>
            <h1 style="margin:0; font-size:30px; color:#faf6f0;
                       font-family:Georgia,serif; letter-spacing:-0.5px;">
              KI-Newsletter
            </h1>
            <p style="margin:8px 0 0; font-size:14px; color:#9e8e7e;">
              Kuratiert von Gemini 2.5 Flash · Das Wichtigste aus der KI-Welt
            </p>
          </td>
        </tr>

        <!-- BODY -->
        <tr>
          <td style="padding:40px 40px 8px;">

            <!-- SEKTION 1: TOP NEWS -->
            <p style="margin:0 0 4px; font-size:11px; color:#c45d3e;
                      letter-spacing:2px; text-transform:uppercase;
                      font-family:Arial,sans-serif;">Sektion 1</p>
            <h2 style="margin:0 0 24px; font-size:24px; color:#2c2416;
                       font-family:Georgia,serif;
                       border-bottom:3px solid #c45d3e; padding-bottom:12px;">
              Top News
            </h2>
            {news_html}

            <!-- SEKTION 2: PODCAST -->
            <p style="margin:32px 0 4px; font-size:11px; color:#c45d3e;
                      letter-spacing:2px; text-transform:uppercase;
                      font-family:Arial,sans-serif;">Sektion 2</p>
            <h2 style="margin:0 0 24px; font-size:24px; color:#2c2416;
                       font-family:Georgia,serif;
                       border-bottom:3px solid #c45d3e; padding-bottom:12px;">
              Podcast-Empfehlung des Tages
            </h2>
            <div style="background:#f0ebe3; border-left:4px solid #c45d3e;
                        padding:20px 24px; border-radius:0 6px 6px 0; margin-bottom:32px;">
              <p style="margin:0 0 6px; font-size:12px; color:#9e8e7e;
                        letter-spacing:1px; text-transform:uppercase;">
                {podcast.get('datum', '')} &nbsp;·&nbsp; {podcast.get('podcast_name', '')}
              </p>
              <h3 style="margin:0 0 10px; font-size:19px; color:#2c2416;
                         font-family:Georgia,serif; line-height:1.35;">
                <a href="{podcast.get('url', '#')}" style="color:#2c2416; text-decoration:none;">
                  {podcast.get('episoden_titel', '')}
                </a>
              </h3>
              <p style="margin:0 0 10px; font-size:15px; color:#4a3f35; line-height:1.7;">
                {podcast.get('warum_hoeren', '')}
              </p>
              <a href="{podcast.get('url', '#')}"
                 style="font-size:13px; color:#c45d3e; text-decoration:none; font-weight:600;">
                → Episode anhören
              </a>
            </div>

            <!-- SEKTION 3: INSPIRATION -->
            <p style="margin:0 0 4px; font-size:11px; color:#c45d3e;
                      letter-spacing:2px; text-transform:uppercase;
                      font-family:Arial,sans-serif;">Sektion 3</p>
            <h2 style="margin:0 0 24px; font-size:24px; color:#2c2416;
                       font-family:Georgia,serif;
                       border-bottom:3px solid #c45d3e; padding-bottom:12px;">
              Inspiration &amp; Monetarisierung
            </h2>
            {insp_html}

            <!-- SEKTION 4: GEMINI TIPP -->
            <p style="margin:0 0 4px; font-size:11px; color:#c45d3e;
                      letter-spacing:2px; text-transform:uppercase;
                      font-family:Arial,sans-serif;">Sektion 4</p>
            <h2 style="margin:0 0 24px; font-size:24px; color:#2c2416;
                       font-family:Georgia,serif;
                       border-bottom:3px solid #c45d3e; padding-bottom:12px;">
              Gemini Pro Tipp
            </h2>
            <div style="background:#fff8f0; border:1px solid #e8d8c8;
                        border-radius:6px; padding:24px; margin-bottom:32px;">
              <div style="margin-bottom:12px;">{badge}</div>
              <h3 style="margin:0 0 12px; font-size:19px; color:#2c2416;
                         font-family:Georgia,serif;">
                {tipp.get('titel', '')}
              </h3>
              <p style="margin:0; font-size:15px; color:#4a3f35; line-height:1.7;">
                {tipp.get('beschreibung', '')}
              </p>
            </div>

          </td>
        </tr>

        <!-- FOOTER -->
        <tr>
          <td style="background:#2c2416; padding:24px 40px; text-align:center;">
            <p style="margin:0; font-size:12px; color:#9e8e7e; line-height:1.8;">
              Dieser Newsletter wird täglich automatisch von Gemini 2.5 Flash kuratiert.<br>
              Betrieben auf GitHub Actions · Vollständig kostenlos · {TODAY}
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>

</body>
</html>"""


# ── E-Mail senden ─────────────────────────────────────────────────────────────
def send_email(subject: str, html_body: str, to: str = RECIPIENT_EMAIL):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = to
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        smtp.sendmail(GMAIL_ADDRESS, to, msg.as_string())

    print(f"E-Mail erfolgreich gesendet an {to}")


def send_error_email(error: Exception):
    subject = f"[KI-Newsletter] Fehler am {TODAY}"
    html = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif; padding:24px; max-width:600px;">
  <h2 style="color:#c45d3e;">KI-Newsletter: Fehler aufgetreten</h2>
  <table style="border-collapse:collapse; width:100%;">
    <tr><td style="padding:6px 0; color:#666; width:120px;">Datum:</td>
        <td style="padding:6px 0;"><strong>{TODAY}</strong></td></tr>
    <tr><td style="padding:6px 0; color:#666;">Fehlertyp:</td>
        <td style="padding:6px 0;"><strong>{type(error).__name__}</strong></td></tr>
    <tr><td style="padding:6px 0; color:#666; vertical-align:top;">Nachricht:</td>
        <td style="padding:6px 0;">{str(error)[:1000]}</td></tr>
  </table>
  <p style="margin-top:20px; color:#666;">
    Bitte prüfe die
    <a href="https://github.com/daiti50552531/ki_newsletter/actions">GitHub Actions Logs</a>
    für Details.
  </p>
</body></html>"""
    try:
        send_email(subject, html)
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
        print("Sende E-Mail via Gmail SMTP ...")
        send_email(subject, html)
        print("Fertig! Newsletter wurde erfolgreich versandt.")
    except Exception as e:
        print(f"FEHLER: {type(e).__name__}: {e}", file=sys.stderr)
        send_error_email(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
