#!/usr/bin/env python3
"""
Täglicher KI-Newsletter – powered by Gemini 2.5 Flash + Google Search Grounding
Verschickt täglich via Gmail SMTP, getriggert durch GitHub Actions.
Nur Standard-Library – keine externen Pakete nötig.
"""

import copy
import html as html_mod
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
def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"FEHLER: Umgebungsvariable/Secret '{name}' fehlt oder ist leer. "
              f"Bitte in den GitHub-Repo-Settings unter 'Secrets and variables' prüfen.",
              file=sys.stderr)
        sys.exit(1)
    return value


GEMINI_API_KEY     = _require_env("GEMINI_API_KEY")
GMAIL_ADDRESS      = _require_env("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = _require_env("GMAIL_APP_PASSWORD")

# Mehrere Empfänger möglich: kommagetrennt, z.B. "a@gmail.com,b@web.de"
RECIPIENTS = [e.strip() for e in _require_env("RECIPIENT_EMAIL").split(",") if e.strip()]

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",  # Fallback MIT Google-Search-Grounding (2.0-lite kann das nicht)
]

HISTORY_FILE      = "newsletter_history.json"
HISTORY_MAX_DAYS  = 5   # Duplikat-Blacklist: so viele Tage zurück sperren
HISTORY_STORE_DAYS = 10  # Aufbewahrung in der Datei (Kontext für Duplikat-Prüfung)

def gemini_url(model: str) -> str:
    return (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={GEMINI_API_KEY}"
    )

TODAY = datetime.now().strftime("%d.%m.%Y")


# ── Inspirations-Bibliothek: 1 Idee pro Tag – Alltag, Arbeit, Kreatives, Tools ─
INSPIRATIONEN = [
    {
        "titel": "Essensplan aus dem, was der Kühlschrank hergibt",
        "kategorie": "Alltag",
        "beschreibung": "Statt abends ratlos vor dem Kühlschrank zu stehen: Zähle der KI einfach auf, was da ist – sie baut daraus einen Wochenplan mit Rezepten und Einkaufsliste für das, was noch fehlt.",
        "prompt": "In meinem Kühlschrank sind: [Zutaten aufzählen]. Wir sind [Anzahl] Personen, davon [Besonderheiten, z.B. ein Kind, eine Vegetarierin]. Erstelle 3 Abendessen-Ideen daraus, mit kurzen Rezepten. Was müsste ich für den Rest der Woche zukaufen?",
        "tipp": "Funktioniert auch mit einem Foto vom Kühlschrankinhalt – einfach hochladen statt abtippen.",
    },
    {
        "titel": "Behördenbrief verstehen und beantworten",
        "kategorie": "Alltag",
        "beschreibung": "Amtsdeutsch ist eine eigene Sprache. Die KI übersetzt dir jeden Bescheid in Klartext und formuliert die Antwort gleich mit – inklusive Fristen, die du nicht verpassen darfst.",
        "prompt": "Hier ist ein Brief vom Amt: [Text einfügen oder Foto hochladen]. Erkläre mir in einfachen Worten: (1) Was wollen die von mir? (2) Bis wann muss ich reagieren? (3) Was passiert, wenn ich nichts tue? Formuliere dann einen Antwortentwurf.",
        "tipp": "Persönliche Daten (Aktenzeichen, Adresse) kannst du vor dem Einfügen schwärzen – für die Erklärung braucht die KI sie nicht.",
    },
    {
        "titel": "Städtetrip in 10 Minuten durchgeplant",
        "kategorie": "Alltag",
        "beschreibung": "Reiseführer wälzen war gestern. Die KI baut dir eine Route, die zu deinem Tempo passt – mit Restaurants, die keine Touristenfallen sind, und einem Plan B für Regen.",
        "prompt": "Ich fahre für [X Tage] nach [Stadt], Budget [gering/mittel/gehoben]. Ich mag [Interessen], ich hasse [z.B. lange Schlangen, Museen]. Erstelle einen Tagesplan mit realistischen Laufwegen, 2 Restaurant-Tipps pro Tag abseits der Touristenpfade und einer Schlechtwetter-Alternative.",
        "tipp": "Frag danach: 'Was würde ein Einheimischer an diesem Plan ändern?' – das holt die besten Korrekturen raus.",
    },
    {
        "titel": "Geschenkidee, die nicht 08/15 ist",
        "kategorie": "Alltag",
        "beschreibung": "Gutschein und Wein gehen immer – und sind immer einfallslos. Beschreibe die Person kurz, und die KI denkt in Richtungen, auf die du allein nicht kommst.",
        "prompt": "Ich suche ein Geschenk für [Person, z.B. meinen Vater, 68]. Er interessiert sich für [Hobbys], hat schon alles und sagt immer 'ich brauche nichts'. Budget: [X €]. Schlage 5 Ideen vor – mindestens 2 davon Erlebnisse statt Dinge, keine Gutscheine.",
        "tipp": "Je eine konkrete Anekdote über die Person ('er redet seit Monaten über...') verbessert die Vorschläge enorm.",
    },
    {
        "titel": "Vertrag checken, bevor du unterschreibst",
        "kategorie": "Alltag",
        "beschreibung": "Handyvertrag, Fitnessstudio, Mietwagen: Die KI liest das Kleingedruckte in Sekunden und zeigt dir die Stellen, über die du stolpern könntest – Kündigungsfristen, automatische Verlängerungen, versteckte Kosten.",
        "prompt": "Hier ist ein Vertrag, den ich unterschreiben soll: [Text einfügen]. Liste auf: (1) Kündigungsfrist und Mindestlaufzeit, (2) alle Kosten inkl. versteckter Gebühren, (3) die 3 Klauseln, die am ehesten zu meinen Lasten gehen. Erkläre alles in einfachen Worten.",
        "tipp": "Ersetzt keinen Anwalt bei großen Verträgen – aber für Alltagsverträge ist es der Check, den sonst niemand macht.",
    },
    {
        "titel": "Arztbefund in Klartext übersetzen",
        "kategorie": "Alltag",
        "beschreibung": "'Unauffälliges Parenchym, kein Anhalt für Malignität' – bitte was? Die KI übersetzt Befunde in verständliche Sprache und hilft dir, die richtigen Fragen für den nächsten Arzttermin vorzubereiten.",
        "prompt": "Hier ist ein medizinischer Befund: [Text einfügen]. Übersetze ihn in einfache Sprache. Was ist unauffällig, was sollte ich im Blick behalten? Welche 3 Fragen sollte ich meinem Arzt beim nächsten Termin stellen?",
        "tipp": "Wichtig: Das ersetzt keine ärztliche Beratung – aber du gehst informiert ins Gespräch statt verunsichert.",
    },
    {
        "titel": "Reklamation, die ernst genommen wird",
        "kategorie": "Alltag",
        "beschreibung": "Kaputtes Produkt, verspäteter Flug, falsche Rechnung: Die KI kennt deine Rechte und formuliert die Beschwerde so, dass sie sachlich Druck macht – höflich, bestimmt und mit den richtigen Stichworten.",
        "prompt": "Ich möchte mich beschweren: [Was ist passiert, wann, was hast du schon versucht]. Schreibe eine sachliche, bestimmte Reklamation. Nenne meine Rechte in dieser Situation (Deutschland) und formuliere eine klare Forderung mit Frist.",
        "tipp": "Bei Flugverspätungen explizit nach 'EU-Fluggastrechteverordnung 261/2004' fragen – das Stichwort wirkt Wunder.",
    },
    {
        "titel": "10 Minuten Englisch beim Kaffee",
        "kategorie": "Lernen",
        "beschreibung": "Die KI ist ein geduldiger Sprachpartner, der nie genervt ist: Sie unterhält sich mit dir auf Englisch (oder jeder anderen Sprache), korrigiert sanft und passt sich deinem Niveau an.",
        "prompt": "Lass uns Englisch üben. Führe eine lockere Unterhaltung mit mir über [Thema]. Antworte auf meinem Niveau, korrigiere meine Fehler kurz in Klammern und stelle mir immer eine Anschlussfrage. Fang an!",
        "tipp": "In der Sprach-App (ChatGPT/Gemini) geht das sogar mündlich – wie ein echtes Gespräch, nur ohne Scham.",
    },
    {
        "titel": "Jedes Thema so erklärt, dass es klick macht",
        "kategorie": "Lernen",
        "beschreibung": "Zinseszins, Blockchain, Photosynthese – egal was: Lass es dir auf genau deinem Niveau erklären, mit Beispielen aus deinem Alltag. Und frag so lange nach, bis es wirklich sitzt.",
        "prompt": "Erkläre mir [Thema] so, als wäre ich 14 Jahre alt – mit einem Beispiel aus dem Alltag. Danach: Stelle mir 3 Verständnisfragen, um zu prüfen, ob ich es wirklich verstanden habe.",
        "tipp": "Der Prüfungs-Teil am Ende ist der Trick: Erklären lassen fühlt sich nach Verstehen an, abgefragt werden deckt Lücken auf.",
    },
    {
        "titel": "Gebrauchtkauf ohne Reinfall",
        "kategorie": "Alltag",
        "beschreibung": "Gebrauchtwagen, E-Bike oder Waschmaschine aus den Kleinanzeigen: Die KI sagt dir, worauf du bei genau diesem Modell achten musst, welche Fragen du stellen solltest und ob der Preis fair ist.",
        "prompt": "Ich will gebraucht kaufen: [Produkt, Modell, Baujahr, geforderter Preis]. Worauf muss ich bei diesem Modell besonders achten (typische Mängel)? Welche 5 Fragen stelle ich dem Verkäufer? Ist der Preis realistisch?",
        "tipp": "Anzeigentext einfach mitschicken – die KI erkennt oft Warnsignale in der Formulierung, die man selbst überliest.",
    },
    {
        "titel": "Trainingsplan, der zu deinem echten Leben passt",
        "kategorie": "Alltag",
        "beschreibung": "Keine Hochglanz-Fitnesspläne, die nach zwei Wochen scheitern: Die KI baut einen Plan um deinen Kalender, dein Level und deine Ausreden herum – und passt ihn an, wenn das Leben dazwischenkommt.",
        "prompt": "Ich will [Ziel, z.B. fitter werden / 5 km laufen können]. Ich habe [X] mal pro Woche [Y] Minuten Zeit, mein Level: [Anfänger/...]. Einschränkungen: [z.B. Knieprobleme]. Erstelle einen realistischen 4-Wochen-Plan, der auch eine verpasste Einheit verkraftet.",
        "tipp": "Nach Woche 1 zurückkommen und ehrlich berichten – die Anpassung ist mehr wert als der erste Plan.",
    },
    {
        "titel": "Rede oder Trinkspruch für die nächste Feier",
        "kategorie": "Kreativ",
        "beschreibung": "Hochzeit, runder Geburtstag, Abschied eines Kollegen: Du lieferst 3 Anekdoten, die KI baut daraus eine Rede mit rotem Faden, Lachern an den richtigen Stellen und einem Ende, das hängen bleibt.",
        "prompt": "Ich halte eine [5-minütige] Rede zu [Anlass] für [Person/Beziehung zu dir]. Hier sind 3 Anekdoten: [aufzählen]. Ton: [herzlich/humorvoll]. Baue daraus eine Rede mit starkem Einstieg und einem Schluss zum Anstoßen. Keine Plattitüden.",
        "tipp": "Laut vorlesen und alles streichen, was du so nie sagen würdest – dann klingt es nach dir statt nach KI.",
    },
    {
        "titel": "Ein eigener Song als Geschenk",
        "kategorie": "Kreativ",
        "beschreibung": "Mit Suno erstellst du aus einer Textbeschreibung einen komplett produzierten Song – Musik, Gesang, alles. Ein persönlicher Geburtstagssong mit Insider-Witzen ist das Geschenk, das garantiert niemand sonst mitbringt.",
        "url": "https://suno.com",
        "link_text": "Suno ausprobieren",
        "tipp": "Lass dir den Songtext vorher von Claude oder ChatGPT schreiben (mit Namen und Anekdoten) und gib ihn Suno als Vorlage – das Ergebnis wird deutlich persönlicher.",
    },
    {
        "titel": "NotebookLM: Frag deine eigenen Unterlagen",
        "kategorie": "Tool-Tipp",
        "beschreibung": "Googles NotebookLM ist kostenlos und beantwortet Fragen direkt aus deinen hochgeladenen Dokumenten – Versicherungspolicen, Bedienungsanleitungen, Mietvertrag. Statt 40 Seiten zu suchen, fragst du einfach: 'Bin ich bei Fahrraddiebstahl versichert?'",
        "url": "https://notebooklm.google.com",
        "link_text": "NotebookLM ausprobieren",
        "tipp": "Die Audio-Funktion macht aus deinen Unterlagen einen Podcast-Dialog – klingt verrückt, ist aber ideal zum Pendeln.",
    },
    {
        "titel": "Perplexity: Recherche mit Quellenangabe",
        "kategorie": "Tool-Tipp",
        "beschreibung": "Wie eine Suchmaschine, nur dass du eine fertige Antwort mit klickbaren Quellen bekommst statt zehn Tabs. Besonders stark bei Fragen wie 'Was ist der aktuelle Stand bei X?' – wo klassische KI-Chats gern veraltet oder erfunden antworten.",
        "url": "https://www.perplexity.ai",
        "link_text": "Perplexity ausprobieren",
        "tipp": "Perfekt für Kaufentscheidungen: 'Vergleiche [Produkt A] und [Produkt B], nur Tests aus den letzten 12 Monaten.'",
    },
    {
        "titel": "DeepL Write: der 30-Sekunden-Feinschliff",
        "kategorie": "Tool-Tipp",
        "beschreibung": "Wichtige E-Mail, Bewerbung, heikle Nachricht? DeepL Write verbessert deinen deutschen Text stilistisch, ohne ihn komplett umzuschreiben – du bleibst du, nur präziser. Vom deutschen Anbieter, kostenlos im Browser.",
        "url": "https://www.deepl.com/write",
        "link_text": "DeepL Write ausprobieren",
        "tipp": "Den Ton-Regler auf 'diplomatisch' stellen, bevor du eine wütende E-Mail abschickst. Danke uns später.",
    },
    {
        "titel": "Goblin Tools: der Anti-Aufschieber",
        "kategorie": "Tool-Tipp",
        "beschreibung": "'Magic ToDo' zerlegt überwältigende Aufgaben ('Umzug organisieren', 'Steuererklärung machen') in kleine, machbare Schritte – so klein, dass Anfangen leichter fällt als Aufschieben. Kostenlos, ohne Anmeldung.",
        "url": "https://goblin.tools",
        "link_text": "Goblin Tools ausprobieren",
        "tipp": "Der Regler mit den Chilischoten bestimmt, wie kleinteilig zerlegt wird – bei echten Aufschiebe-Monstern: volle Schärfe.",
    },
    {
        "titel": "Fotobuch-Texte, die nicht nach Pflicht klingen",
        "kategorie": "Kreativ",
        "beschreibung": "Das Urlaubs-Fotobuch scheitert selten an den Fotos, sondern an den Texten. Erzähl der KI stichpunktartig, was passiert ist – sie macht daraus kurze, warme Bildunterschriften und eine Einleitung.",
        "prompt": "Ich mache ein Fotobuch über [Anlass, z.B. unseren Sommerurlaub in Italien]. Hier Stichpunkte zu den Kapiteln: [aufzählen]. Schreibe je eine kurze, warmherzige Kapitel-Einleitung (2-3 Sätze) und schlage einen Buchtitel vor. Ton: persönlich, nicht kitschig.",
        "tipp": "Funktioniert genauso für Jahresrückblicke, Abschiedsbücher für Kollegen oder Omas 80. Geburtstag.",
    },
    {
        "titel": "Meeting-Notizen in 30 Sekunden zum Protokoll",
        "kategorie": "Arbeit",
        "beschreibung": "Rohnotizen rein, fertiges Protokoll raus: sauber strukturiert nach besprochenen Punkten, Entscheidungen und Aufgaben mit Verantwortlichen. Der Klassiker, der pro Woche locker eine Stunde spart.",
        "prompt": "Strukturiere diese Meeting-Notizen in: (1) Besprochene Punkte, (2) Entscheidungen, (3) Offene Aufgaben mit Verantwortlichen und Deadline. Formuliere präzise, keine Füllsätze. Hier die Notizen: [einfügen]",
        "tipp": "Innerhalb von 24 h versenden – danach erinnert sich niemand mehr an die Details.",
    },
    {
        "titel": "Endlosen E-Mail-Thread auf den Kern eindampfen",
        "kategorie": "Arbeit",
        "beschreibung": "30 E-Mails, 5 Meinungen, keine Entscheidung? Kopiere den Verlauf in die KI und bekomme in Sekunden: worum es wirklich geht, wer was will und was der nächste Schritt wäre.",
        "prompt": "Hier ist ein E-Mail-Verlauf: [einfügen]. Destilliere: (1) Worum geht es wirklich? (2) Welche Positionen gibt es? (3) Was ist noch ungeklärt? (4) Was wäre ein konkreter nächster Schritt?",
        "tipp": "Ideal 5 Minuten vor dem Meeting, in dem es um genau diesen Thread geht.",
    },
    {
        "titel": "Schwieriges Feedback, das ankommt statt verletzt",
        "kategorie": "Arbeit",
        "beschreibung": "Kritik an Kollegen, Dienstleister oder Chef ist ein Drahtseilakt. Die KI formuliert deine Kernbotschaft so, dass sie direkt ist, ohne zu eskalieren – und du behältst die Kontrolle über den Ton.",
        "prompt": "Ich muss folgendes Feedback geben an [Rolle]: [Kernkritik in Stichpunkten]. Formuliere es konstruktiv und lösungsorientiert. Ton: direkt und respektvoll, nicht beschönigend. Gib mir 2 Varianten: eine für ein Gespräch, eine als E-Mail.",
        "tipp": "Kontext dazugeben ('die Person reagiert empfindlich auf X') macht den Vorschlag deutlich treffsicherer.",
    },
    {
        "titel": "Entscheidungen durchdenken statt im Kreis grübeln",
        "kategorie": "Arbeit",
        "beschreibung": "Jobwechsel, größere Anschaffung, Projekt-Weichenstellung: Die KI zwingt dein Bauchgefühl in eine Struktur – Pro, Contra, Kriterien, Empfehlung. Oft merkst du beim Lesen, was du eigentlich längst entschieden hast.",
        "prompt": "Ich muss mich entscheiden: Option A ist [Beschreibung], Option B ist [Beschreibung]. Meine Kriterien: [z.B. Kosten, Zeit, Risiko, Bauchgefühl]. Erstelle eine ehrliche Pro/Contra-Analyse, empfiehl eine Option mit Begründung – und nenne die Frage, die ich mir selbst noch beantworten muss.",
        "tipp": "Am Ende ergänzen: 'Was würde ein guter Freund mir raten?' – die Antwort darauf trifft oft am genauesten.",
    },
    {
        "titel": "Haushaltsbudget entwirren ohne Excel-Frust",
        "kategorie": "Alltag",
        "beschreibung": "Wo bleibt eigentlich das Geld? Zähle der KI deine ungefähren Einnahmen und Ausgaben auf – sie sortiert, zeigt dir die größten Hebel und schlägt realistische Sparziele vor, ohne Verzichtspredigt.",
        "prompt": "Hier sind unsere monatlichen Einnahmen und Ausgaben (ungefähr): [aufzählen]. Sortiere das in Kategorien, zeige mir die 3 größten Einsparhebel und schlage ein realistisches Sparziel vor. Keine Extremvorschläge – es muss alltagstauglich bleiben.",
        "tipp": "Einmal im Quartal wiederholen reicht völlig – wichtiger als Präzision ist, die Muster zu sehen.",
    },
    {
        "titel": "Kinderfragen gemeinsam erforschen",
        "kategorie": "Alltag",
        "beschreibung": "'Warum ist der Himmel blau?' – 'Äh...' Die KI liefert kindgerechte Erklärungen, die auch dir Spaß machen, plus ein kleines Experiment für zu Hause. Aus Verlegenheit wird ein gemeinsames Forschungsprojekt.",
        "prompt": "Mein Kind ([Alter]) hat gefragt: [Frage]. Erkläre die Antwort kindgerecht in 3-4 Sätzen, mit einem Vergleich aus der Kinderwelt. Gibt es ein einfaches Experiment oder eine Beobachtung, mit der wir das zusammen entdecken können?",
        "tipp": "Die Experiment-Frage ist der Geheimtipp – aus 30 Sekunden Antwort wird ein ganzer Nachmittag.",
    },
]


def get_inspiration() -> dict:
    day_of_year = datetime.now().timetuple().tm_yday
    return INSPIRATIONEN[(day_of_year - 1) % len(INSPIRATIONEN)]


# ── Newsletter-Verlauf (Duplikat-Schutz) ─────────────────────────────────────
def _read_history() -> dict:
    if not os.path.exists(HISTORY_FILE):
        return {"editions": []}
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except Exception as e:
        print(f"  History-Load übersprungen: {e}")
        return {"editions": []}


def _edition_headlines(edition: dict) -> list:
    """Alle Schlagzeilen einer Ausgabe – unterstützt altes (titles/schnell als
    Strings) UND neues Schema (top_news/schnelldurchlauf als Dicts)."""
    out = []
    # neues Schema
    for n in edition.get("top_news", []) + edition.get("praxis", []):
        if isinstance(n, dict) and n.get("titel"):
            out.append(n["titel"])
    for s in edition.get("schnelldurchlauf", []):
        if isinstance(s, dict) and s.get("text"):
            out.append(s["text"])
    # altes Schema (Strings)
    out.extend(t for t in edition.get("titles", []) if isinstance(t, str) and t)
    out.extend(s for s in edition.get("schnell", []) if isinstance(s, str) and s)
    return out


def _edition_blobs(edition: dict) -> list:
    """Reiches Vergleichsmaterial: Titel + Zusammenfassung zu einem Themen-Blob
    zusammengefasst, damit der Filter Themen erkennt – nicht nur Wortgleichheit."""
    out = []
    for n in edition.get("top_news", []) + edition.get("praxis", []):
        if isinstance(n, dict):
            blob = (n.get("titel", "") + " " + n.get("zusammenfassung", "")).strip()
            if blob:
                out.append(blob)
    for s in edition.get("schnelldurchlauf", []):
        if isinstance(s, dict) and s.get("text"):
            out.append(s["text"])
    out.extend(t for t in edition.get("titles", []) if isinstance(t, str) and t)
    out.extend(s for s in edition.get("schnell", []) if isinstance(s, str) and s)
    return out


def load_published_titles() -> list:
    """Schlagzeilen der letzten HISTORY_MAX_DAYS Ausgaben – kompakte Blacklist für den Prompt."""
    history = _read_history()
    titles = []
    for edition in history.get("editions", [])[-HISTORY_MAX_DAYS:]:
        titles.extend(_edition_headlines(edition))
    return [t for t in titles if t]


def load_published_corpus() -> list:
    """Titel + Zusammenfassungen der letzten HISTORY_MAX_DAYS Ausgaben –
    Vergleichsbasis für den deterministischen Qualitäts-Filter."""
    history = _read_history()
    blobs = []
    for edition in history.get("editions", [])[-HISTORY_MAX_DAYS:]:
        blobs.extend(_edition_blobs(edition))
    return [b for b in blobs if b]


def load_recent_podcasts() -> list:
    """Podcast-Episoden der letzten HISTORY_MAX_DAYS Ausgaben (Duplikat-Sperre)."""
    history = _read_history()
    titles = []
    for edition in history.get("editions", [])[-HISTORY_MAX_DAYS:]:
        pod = edition.get("podcast", {})
        if isinstance(pod, dict) and pod.get("episoden_titel"):
            titles.append(pod["episoden_titel"])
    return titles


def _commit_history(message: str) -> None:
    """Committet und pusht die History-Datei (läuft in GitHub Actions via checkout@v4)."""
    import subprocess
    subprocess.run(["git", "config", "user.email", "action@github.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Newsletter Bot"], check=True)
    subprocess.run(["git", "add", HISTORY_FILE], check=True)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if staged.returncode != 0:
        subprocess.run(["git", "commit", "-m", message], check=True)
        subprocess.run(["git", "pull", "--rebase"], check=False)
        subprocess.run(["git", "push"], check=True)


def load_sent_recipients() -> list:
    """Empfänger, die die heutige Ausgabe bereits erhalten haben (Teilversand-Schutz)."""
    log = _read_history().get("sent_log", {})
    return log.get("to", []) if log.get("date") == TODAY else []


def record_sent(recipient: str) -> None:
    """Merkt sich sofort lokal, wer die heutige Ausgabe schon hat (Push folgt gesammelt)."""
    try:
        history = _read_history()
        log = history.get("sent_log", {})
        if log.get("date") != TODAY:
            log = {"date": TODAY, "to": []}
        if recipient not in log["to"]:
            log["to"].append(recipient)
        history["sent_log"] = log
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  Versand-Log übersprungen (non-fatal): {e}")


def already_sent_today() -> bool:
    """True, wenn heute bereits an alle versendet wurde (Backup-Lauf-Schutz)."""
    if _read_history().get("last_sent", "") == TODAY:
        return True
    return set(RECIPIENTS) <= set(load_sent_recipients())


def save_published_titles(data: dict) -> None:
    """Schreibt heutige Ausgabe in newsletter_history.json und pusht via git."""
    try:
        today_entry = {
            "date": TODAY,
            "top_news": [
                {k: n.get(k, "") for k in ("titel", "zusammenfassung", "take", "quelle", "url", "datum")}
                for n in data.get("top_news", [])
            ],
            "praxis": [
                {k: p.get(k, "") for k in ("titel", "zusammenfassung", "branche", "quelle", "url", "datum")}
                for p in data.get("praxis", [])
            ],
            "schnelldurchlauf": [
                {k: s.get(k, "") for k in ("text", "quelle", "url")}
                for s in data.get("schnelldurchlauf", [])
            ],
            "podcast": {
                k: data.get("podcast", {}).get(k, "")
                for k in ("episoden_titel", "podcast_name")
            },
        }
        history = _read_history()
        editions = [e for e in history.get("editions", []) if e.get("date") != TODAY]
        editions.append(today_entry)
        history["editions"] = editions[-HISTORY_STORE_DAYS:]
        history["last_sent"] = TODAY
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        _commit_history(f"chore: newsletter history {TODAY} [skip ci]")
        n = len(today_entry["top_news"]) + len(today_entry["schnelldurchlauf"])
        print(f"  ✓ History gespeichert ({n} Meldungen für morgen geblockt)")
    except Exception as e:
        print(f"  History-Save übersprungen (non-fatal): {e}")


# ── Prompt ────────────────────────────────────────────────────────────────────
PROMPT_BASE = f"""Du bist Chefredakteur eines deutschsprachigen KI-Newsletters fuer Wissensarbeiter.
Heute ist der {TODAY}. Nutze Google Search zur Recherche. Alle Texte auf Deutsch.

--- ZIELGRUPPE ---
Wissensarbeiter und Projektverantwortliche in deutschen Unternehmen. Keine Entwickler, keine Investoren, keine Startup-Gruender.
BRANCHEN-FOKUS: Der Leserkreis arbeitet u.a. im deutschen Einzelhandel und in der Telekommunikationsbranche.
Meldungen zu KI in diesen Branchen haben besonderen Wert – der Newsletter bleibt aber allgemein
verstaendlich und interessant, kein Branchen-Fachblatt.
Jemand der: (1) den Ueberblick ueber KI-Entwicklungen behalten will die seinen Arbeitsalltag beeinflussen;
(2) KI praktisch fuer Selbstorganisation, Projektarbeit und Dokumentation nutzen moechte;
(3) sich kleine KI-Helfer bauen oder entdecken will – auch ohne tiefe Programmierkenntnisse.

--- STIL (AInauten-Stil als Vorbild) ---
Ton: Wie ein gut informierter Kollege der die Tools selbst kennt und getestet hat. Nicht neutral –
einordnen, bewerten, klare Perspektive bieten. Auch Schwaechen und Einschraenkungen benennen,
das schafft mehr Vertrauen als reines Loben.
Schreibweise: Direkte Ansprache ("du"), aktive Sprache, keine Passivsaetze.
Keine Buzzwords ("revolutionaer", "disruptiv", "bahnbrechend", "KI-Zeitalter") – konkret statt Hype.
Struktur pro News: (1) Kontext/Warum passiert das gerade? (2) Was ist passiert + konkrete Details.
(3) Take: Ausprobieren? Abwarten? Wichtig oder Hype? Balanced – Schwaechen duerfen genannt werden.
Ueberschriften: Spezifisch, zeigen was sich aendert – nicht nur was passiert ist.
  SCHLECHT: "OpenAI veroeffentlicht neues Modell"
  GUT: "GPT-5 schlaegt Claude bei komplexen Texten – lohnt sich der Wechsel fuer dich?"
  SCHLECHT: "Neue KI-Tools verfuegbar"
  GUT: "Dieses Tool erledigt Meeting-Protokolle in 30 Sekunden – und es ist kostenlos"
  SCHLECHT: "Google kuendigt Update an"
  GUT: "Gemini direkt im Browser: Was das fuer alle bedeutet, die kein Claude-Abo haben"

--- AKTUALITAET ---
STRIKTE REGEL: Nur Nachrichten der letzten 48 Stunden. Aeltere Artikel sind VERBOTEN.
Pruefe das Veroeffentlichungsdatum jedes Artikels explizit per Suche bevor du ihn aufnimmst.
Wenn du das Datum eines Artikels nicht mit Sicherheit bestaetigen kannst – lass ihn weg.
Lieber 3 frische Nachrichten als 5 mit alten dabei. Qualitaet vor Quantitaet.
AUSNAHME praxis-Rubrik: Unternehmens-Use-Cases duerfen bis zu 7 Tage alt sein, wenn sie
noch nicht im Newsletter waren.
Podcast: Episode aus den letzten 7 Tagen – aber NUR aufnehmen wenn wirklich herausragend (siehe REGELN).
TOP-PRIORITAET: Neue Modell-Releases (ChatGPT, Claude, Gemini, Llama, DeepSeek, Mistral usw.),
neue APIs und SDK-Versionen – diese IMMER aufnehmen wenn in den letzten 24h veroeffentlicht.
Suche explizit nach: "site:techcrunch.com after:{TODAY}" oder aehnlichen Datumsfiltern.

--- BLACKLIST (niemals verwenden) ---
AInauten, TAAFT, Doppelgaenger Newsletter/Podcast, AI Daily Brief

--- QUELLEN ---
News (englisch): TechCrunch, The Verge, Wired, Ars Technica, MIT Technology Review, Bloomberg Technology, The Information, VentureBeat, Reuters Technology
News (deutsch): The Decoder (the-decoder.de), heise online, t3n, Golem
Wirtschaft/Praxis: Handelsblatt, WirtschaftsWoche, manager magazin, Lebensmittel Zeitung,
Fachpresse Handel und Telekommunikation, Unternehmens-Ankuendigungen (Pressebereiche)
Communities: Hacker News, Reddit (r/LocalLLaMA, r/machinelearning, r/artificial), DEV Community, GitHub Trending
Analyse: Hugging Face Blog, Import AI, Stratechery, Papers With Code
Asien: Quellen zu DeepSeek, Qwen und anderen asiatischen Open-Source-Modellen
Podcasts: Lex Fridman, Hard Fork NYT, Practical AI, Latent Space, No Priors, TWIML, Dwarkesh Podcast, BG2 Pod

--- NEWS SCORING (der wichtigste Filter) ---
Der Relevanz-Test fuer JEDE Meldung: "Bewegt sie den KI-Markt, kann der Leser sie heute
nutzen, oder zeigt sie konkret wie ein Unternehmen KI einsetzt?" Wenn nichts davon: raus.
KERN-EBENE A – MARKTBEWEGER (das Herz des Newsletters, KEIN Limit):
Was passiert bei den Frontier Labs (OpenAI, Anthropic, Google, Meta, xAI, DeepSeek)?
Neue Modell-Releases, grosse Produktnews, US-Regierung und Geopolitik, Chips, grosse
Uebernahmen und Machtverschiebungen. Die grossen Meldungen, die den Markt bewegen –
im Stil von Rundown/Finimize. IMMER aufnehmen, wenn es sie gibt.
KERN-EBENE B – HEUTE NUTZBAR:
Neue Features die AB SOFORT verfuegbar sind, in Tools die Wissensarbeiter taeglich nutzen
(ChatGPT, Gemini, Claude, Microsoft Copilot/Office, Notion, Teams, DeepL). Ein Feature das
gestern fuer alle ausgerollt wurde schlaegt eine Ankuendigung mit Warteliste.
ERGAENZUNGS-EBENE C – KI IN DER PRAXIS (eigene Rubrik "praxis", 0-2 Eintraege):
Konkrete Unternehmens-Use-Cases und Rollouts: Welches Unternehmen setzt KI wofuer ein –
weltweit und besonders in Deutschland/Europa? Beispiele: ein Haendler automatisiert
Bestellprozesse, eine Bank baut eine Super-App, ein Telko nutzt KI im Netzbetrieb.
Handel und Telekommunikation haben Vorrang bei gleicher Staerke, aber jede wirklich
interessante Praxis-Story zaehlt. NUR echte Faelle mit Substanz – KEINE Umfragen,
KEINE Studien ohne konkretes Unternehmen, kein PR-Nebel. Leer lassen ist voellig okay.
EU-CHECK: Pruefe bei jedem Feature ob es in der EU/Deutschland verfuegbar ist. Wenn nicht
oder erst spaeter, MUSS das im Take stehen (z.B. "In der EU noch nicht verfuegbar").
ABLEHNEN: Reine Aktienkurse, oberflaechliches PR ohne Substanz, akademische Forschung ohne
praktischen Anwendungsfall, Startup-Finanzierungsnews ohne technischen oder strategischen Kern

--- AUSGABE ---
Gib ausschliesslich gueltiges JSON zurueck, ohne Markdown-Formatierung, ohne Erklaerungen:

{{
  "intro": "3-4 Saetze Einleitung im Stil eines Kollegen der den Newsletter selbst liest. Variiere den Einstieg von Tag zu Tag: mal eine ueberraschende Zahl, mal eine Frage, mal eine Beobachtung, mal eine kurze Begruessung – NICHT jeden Tag dieselbe Eroeffnung. PFLICHT: Nenne eine spezifische Zahl, ein konkretes Faktum oder eine ueberraschende Wendung aus den heutigen News – keine vagen Teaser wie 'interessante Entwicklungen'. Schliesse mit einem kurzen Hinweis was heute noch drin ist. KEINE Floskeln wie 'Willkommen zur neuen Ausgabe' oder 'Im heutigen Newsletter'.",
  "top_news": [
    {{
      "titel": "Spezifischer Titel der zeigt was sich aendert – nicht nur was passiert ist",
      "zusammenfassung": "3-5 Saetze auf Deutsch: Erst kurzer Kontext (warum passiert das gerade?), dann was genau passiert ist, dann konkrete Details und erste Auswirkungen. Nicht nur berichten – einordnen. Keine generischen Saetze wie 'Dies ist ein wichtiger Schritt'.",
      "bedeutung": "EIN Satz: Was heisst diese News ganz konkret fuer den Alltag des Lesers? (praktische Konsequenz, kein Meinungs-Take)",
      "update": "NUR setzen (true) wenn dies eine ECHTE Weiterentwicklung eines bereits gemeldeten Themas ist – dann muss der Titel mit 'Update:' beginnen und die Zusammenfassung klar sagen was NEU ist",
      "take": "1-2 Saetze klare Empfehlung: Lohnt sich das Ausprobieren? Abwarten? Wirklich wichtig oder Hype? Schwaechen und Einschraenkungen koennen und sollen genannt werden wenn vorhanden.",
      "quelle": "Name der Quelle",
      "url": "https://direktlink-zum-artikel/nicht-zur-homepage",
      "datum": "TT.MM.YYYY"
    }}
  ],
  "praxis": [
    {{
      "titel": "Welches Unternehmen macht was mit KI – konkret, nicht abstrakt",
      "zusammenfassung": "2-4 Saetze: Was genau macht das Unternehmen, wie weit ist es, was ist das Ergebnis oder Ziel? Konkrete Zahlen und Details wenn verfuegbar.",
      "branche": "Branche in einem Wort, z.B. Handel, Telko, Banken, Industrie, Logistik",
      "quelle": "Name der Quelle",
      "url": "https://direktlink-zum-artikel",
      "datum": "TT.MM.YYYY"
    }}
  ],
  "schnelldurchlauf": [
    {{
      "emoji": "EIN passendes Emoji als Kategorie-Label: 🛠️ Tools, 💼 Business, 🧠 Forschung, 📱 Consumer, ⚖️ Regulierung, 💰 Geld",
      "text": "Ein einziger pointierter Satz der die Meldung komplett erfasst – konkret, kein Clickbait",
      "quelle": "Name der Quelle",
      "url": "https://direktlink-zum-artikel"
    }}
  ],
  "podcast": {{
    "episoden_titel": "...",
    "podcast_name": "...",
    "warum_hoeren": "2-3 Saetze auf Deutsch: Was macht diese Episode AUSSERGEWOEHNLICH?",
    "url": "https://...",
    "datum": "TT.MM.YYYY"
  }},
  "zahl_des_tages": {{
    "zahl": "Eine konkrete Zahl/Prozentangabe/Kennzahl aus den heutigen News, z.B. '40%' oder '2,3 Mio.'",
    "kontext": "Ein einziger Satz der erklaert wofuer die Zahl steht und warum sie relevant ist",
    "quelle": "Name der Quelle"
  }}
}}

REGELN – DAS WICHTIGSTE PRINZIP: Jede Sektion muss sich ihren Platz VERDIENEN.
Der Newsletter soll in unter 6 Minuten lesbar sein. Laenge ist okay, wenn jeder Eintrag
wirklich relevant ist – aber NIEMALS eine Sektion aus Pflichtgefuehl fuellen.
- top_news: 2 BIS 4 Eintraege – nur die staerksten Stories. An schwachen Tagen sind 2 voellig okay.
- praxis: 0 BIS 2 Eintraege – NUR bei echten Unternehmens-Use-Cases. Meist wird hier 0-1 stehen. Leere Liste [] ist der Normalfall an vielen Tagen.
- schnelldurchlauf: 3 BIS 6 Einzeiler – nur was wirklich interessant ist, ebenfalls max. 48h alt
- podcast: HOHE SCHWELLE. Nur ausfuellen wenn eine Episode herausragend ist: grosser Gast packt aus, ein Unternehmen erklaert seinen KI-Umbau konkret, etwas wirklich Neues wird erstmals diskutiert. An normalen Tagen leeres Objekt {{}} zurueckgeben. NICHT dieselbe Episode wie in den Vortagen (siehe ggf. Sperrliste unten).
- zahl_des_tages: Nur ausfuellen wenn die Zahl wirklich verblueffend ist und aus einer der News stammt. Sonst leeres Objekt {{}}.
- Eine Meldung erscheint in GENAU EINER Sektion (top_news ODER praxis ODER schnelldurchlauf)
- Alle Daten im Format TT.MM.YYYY
- URLs direkt zum Artikel (nicht Homepage), Fallback: https://www.google.com/search?q=titel+quelle
- Lieber 2 starke Meldungen als 3 bei der eine ein Lueckenbuesser ist
- bedeutung: pro Top-News PFLICHT – der Satz beginnt gedanklich mit 'Fuer dich heisst das: ...'
"""


# Täglich wechselnder Such-Schwerpunkt – damit Gemini nicht jeden Tag in
# denselben Ecken sucht und dieselben Stories wiederfindet.
FOKUS_ROTATION = [
    "neue Modell-Releases, APIs und Entwickler-Werkzeuge",              # Montag
    "KI im Handel und bei Konsumguetern (Use Cases, Rollouts)",         # Dienstag
    "EU-Regulierung, Datenschutz und KI-Recht",                         # Mittwoch
    "KI-Agenten und Automatisierung im Arbeitsalltag",                  # Donnerstag
    "KI in der Telekommunikation und im Netzbetrieb (Use Cases)",       # Freitag
    "Forschung, Open-Source-Modelle und Benchmarks",                    # Samstag
    "Consumer-Apps, KI im Privatleben und Unternehmens-Use-Cases",      # Sonntag
]


def build_prompt(published_titles: list, recent_podcasts: list = None,
                 retry_hinweis: bool = False) -> str:
    """Baut den finalen Prompt – injiziert bereits veröffentlichte Schlagzeilen und Podcasts."""
    prompt = PROMPT_BASE
    fokus = FOKUS_ROTATION[datetime.now().weekday()]
    prompt += f"""
--- HEUTIGER SUCH-SCHWERPUNKT ---
Lege heute einen zusaetzlichen Schwerpunkt auf: {fokus}.
Das ist ein Schwerpunkt, KEIN Filter – starke News aus anderen Bereichen trotzdem aufnehmen.
"""
    if retry_hinweis:
        prompt += """
--- ZWEITER ANLAUF ---
Der vorherige Entwurf bestand fast nur aus bereits gemeldeten Themen und wurde verworfen.
Suche jetzt gezielt nach Meldungen, die du beim ersten Mal NICHT gefunden hast:
andere Quellen, andere Themenfelder, kleinere aber frische Meldungen.
Wiederhole unter keinen Umstaenden Themen aus der Sperrliste.
"""
    if published_titles:
        block = "\n".join(f"  - {t}" for t in published_titles[:50])
        prompt += f"""
--- BEREITS VEROEFFENTLICHT – ABSOLUTES DUPLIKAT-VERBOT ---
Diese Meldungen liefen in den letzten {HISTORY_MAX_DAYS} Ausgaben.
Weder in top_news noch im schnelldurchlauf duerfen sie – auch inhaltlich aehnlich – erneut erscheinen.
Das gilt auch fuer dasselbe Thema aus einer ANDEREN Quelle oder mit anderer Formulierung
(gleiches Modell-Update, gleiche Produktankuendigung, gleiche Kennzahl = verboten).
EINZIGE AUSNAHME: Eine ECHTE neue Entwicklung zu einem dieser Themen (neue Fakten, neue
Fristen, neue Zahlen, neuer Beschluss) darfst du bringen – dann "update": true setzen,
den Titel mit "Update:" beginnen und in der Zusammenfassung klar sagen, was seit der
letzten Meldung NEU ist. Eine blosse Wiederholung aus anderer Quelle ist KEIN Update.
Waehle ansonsten konsequent andere Themen:
{block}
"""
    if recent_podcasts:
        pod_block = "\n".join(f"  - {t}" for t in recent_podcasts)
        prompt += f"""
--- PODCAST-SPERRLISTE ---
Diese Episoden wurden bereits empfohlen – waehle eine ANDERE Episode:
{pod_block}
"""
    return prompt


# ── Gemini API Call (mit Retry + Model-Fallback bei 503) ─────────────────────
def call_gemini(prompt: str, patient: bool = True) -> dict:
    """patient=True: Hauptdurchlauf, lange 5xx-Wartezeiten. patient=False: optionale
    Durchläufe (Editor) mit kurzer Geduld, damit das 30-Min-Job-Limit sicher hält."""
    payload = {
        "tools": [{"googleSearch": {}}],
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 16384,
        },
    }
    data = json.dumps(payload).encode("utf-8")

    max_attempts = 3 if patient else 2
    for model in GEMINI_MODELS:
        print(f"Versuche Modell: {model} ...")
        for attempt in range(max_attempts):
            req = urllib.request.Request(
                gemini_url(model), data=data,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    print(f"  ✓ Antwort von {model}")
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                print(f"  HTTP {e.code} von {model} (Versuch {attempt+1}/{max_attempts}): {body[:200]}")
                if e.code in (500, 502, 503, 504) and attempt < max_attempts - 1:
                    wait = (120 if patient else 30) * (attempt + 1)
                    print(f"  warte {wait}s ...")
                    time.sleep(wait)
                elif e.code in (500, 502, 503, 504):
                    print(f"  {model} dauerhaft gestört – wechsle Modell.")
                    break
                elif e.code == 429:
                    print(f"  {model} Quota erschöpft – wechsle Modell.")
                    break
                elif e.code == 404:
                    print(f"  {model} nicht gefunden – wechsle Modell.")
                    break
                else:
                    raise RuntimeError(f"Gemini {model} HTTP {e.code}: {body[:600]}")
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                # Timeout, DNS, Verbindungsabriss – vorübergehend, nicht fatal
                print(f"  Netzwerkfehler bei {model} (Versuch {attempt+1}/{max_attempts}): {e}")
                if attempt < max_attempts - 1:
                    wait = 30 * (attempt + 1)
                    print(f"  warte {wait}s ...")
                    time.sleep(wait)
                else:
                    print(f"  {model} nicht erreichbar – wechsle Modell.")
                    break
    raise RuntimeError("Alle Gemini-Modelle nicht verfügbar.")


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


def normalize_data(data: dict) -> dict:
    """Sichert die Modell-Antwort ab: Gemini liefert Felder manchmal als null
    oder mit falschem Typ – das hat am 06.07. den Lauf gecrasht."""
    if not isinstance(data, dict):
        return {}
    for key in ("top_news", "praxis", "schnelldurchlauf"):
        val = data.get(key)
        data[key] = [x for x in val if isinstance(x, dict)] if isinstance(val, list) else []
    for key in ("podcast", "zahl_des_tages"):
        if not isinstance(data.get(key), dict):
            data[key] = {}
    for key in ("intro",):
        if not isinstance(data.get(key), str):
            data[key] = ""
    return data


# ── Redaktions-Check: zweiter Gemini-Durchlauf prüft den eigenen Entwurf ──────
EDITOR_PROMPT_TEMPLATE = """Du bist der schaerfste Redaktionsleiter dieses KI-Newsletters und pruefst
den Entwurf eines Kollegen, bevor er rausgeht. Heute ist der {today}.
Nutze Google Search um Fakten und Daten zu verifizieren.

Entwurf als JSON:
{draft}

PRUEFE UND KORRIGIERE:
1. AKTUALITAET: Verifiziere per Suche, dass jeder Artikel in top_news und schnelldurchlauf tatsaechlich
   aus den letzten 24-48 Stunden stammt. Entferne jeden Eintrag, den du nicht verifizieren kannst.
2. DOPPLUNGEN: Wenn zwei Eintraege (auch top_news vs schnelldurchlauf) inhaltlich dasselbe Thema
   behandeln, behalte nur den staerkeren und entferne den anderen komplett.
3. SCHWAECHE: Streiche Floskeln, Buzzwords ("revolutionaer", "bahnbrechend", "KI-Zeitalter") und vage
   Saetze. Ersetze sie durch konkrete Formulierungen.
4. TAKE-QUALITAET: Jeder Take muss eine echte Meinung sein (ausprobieren/abwarten/Hype), keine
   Wiederholung der Zusammenfassung.
5. EU-CHECK: Wenn ein Feature nicht in der EU verfuegbar ist, muss das im Take stehen.
6. ZAHL DES TAGES: Pruefe dass die Zahl wirklich aus einer der News stammt, nicht erfunden ist.
7. Wenn nach der Pruefung weniger als 2 Eintraege in top_news uebrig bleiben, fuelle NICHT mit
   schwachen Eintraegen auf – lieber kurz und stark als lang und schwach.
8. PRAXIS-CHECK: Eintraege in "praxis" muessen ECHTE Unternehmens-Use-Cases sein (konkretes
   Unternehmen, konkreter Einsatz). Umfragen, Studien ohne Firma und PR-Nebel entfernen.
9. PODCAST-SCHWELLE: Streiche die Podcast-Empfehlung KOMPLETT (leeres Objekt), wenn die
   Episode nicht wirklich herausragend ist. Eine solide Episode reicht NICHT.
10. ZAHL-SCHWELLE: Streiche zahl_des_tages (leeres Objekt), wenn die Zahl nicht wirklich
   verblueffend ist.
11. UPDATE-CHECK: Eintraege mit "update": true muessen eine ECHTE neue Entwicklung enthalten
   (verifiziere per Suche: neues Datum, neue Fakten). Wenn es nur eine Wiederholung ist,
   entferne den Eintrag komplett. Behalte das "update"-Feld bei echten Updates bei.

Gib das KORRIGIERTE JSON in EXAKT demselben Format zurueck (Felder: intro, top_news,
praxis, schnelldurchlauf, podcast, zahl_des_tages). Behalte ALLE Unterfelder jedes
Eintrags bei, insbesondere "bedeutung" (top_news), "branche" (praxis) und "emoji"
(schnelldurchlauf).
Keine Erklaerungen, kein Markdown, nur das JSON.
"""

EDITOR_BLACKLIST_BLOCK = """
8. BEREITS GELAUFEN – HARTES THEMEN-VERBOT: Die folgenden Meldungen liefen in den letzten
   {days} Ausgaben. Entferne JEDEN Eintrag, der dasselbe Thema behandelt – auch wenn er aus
   einer anderen Quelle stammt oder anders formuliert ist (gleiches Modell-Update, gleiche
   Produktankuendigung, gleiche Kennzahl = Duplikat). Im Zweifel entfernen.
{block}
"""


def run_editor_pass(data: dict, published_titles: list = None) -> dict:
    """Zweiter Gemini-Durchlauf: prueft Aktualitaet, Dopplungen und Schreibqualitaet des Entwurfs."""
    try:
        keys = ("intro", "top_news", "praxis", "schnelldurchlauf", "podcast", "zahl_des_tages")
        draft_json = json.dumps({k: data[k] for k in keys if k in data}, ensure_ascii=False)
        editor_prompt = EDITOR_PROMPT_TEMPLATE.format(today=TODAY, draft=draft_json)
        if published_titles:
            block = "\n".join(f"  - {t}" for t in published_titles[:50])
            editor_prompt += EDITOR_BLACKLIST_BLOCK.format(days=HISTORY_MAX_DAYS, block=block)
        response = call_gemini(editor_prompt, patient=False)
        candidates = response.get("candidates", [])
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        raw_text = "".join(p.get("text", "") for p in parts)
        if not raw_text.strip():
            print("  Editor-Pass: leere Antwort – Entwurf wird unverändert übernommen")
            return data
        edited = normalize_data(extract_json(raw_text))
        if not edited.get("top_news"):
            print("  Editor-Pass: keine top_news im Ergebnis – Entwurf wird unverändert übernommen")
            return data
        for key in keys:
            if key in edited:
                data[key] = edited[key]
        print(f"  ✓ Editor-Pass abgeschlossen ({len(data.get('top_news', []))} Top-News übrig)")
        return data
    except Exception as e:
        print(f"  Editor-Pass übersprungen (non-fatal): {e}")
        return data


# ── Qualitäts-Sicherheitsnetz: Aktualität & Dopplungen programmatisch prüfen ──
# Häufige deutsche Funktionswörter – tragen nichts zur Themengleichheit bei.
_STOPWORDS = {
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einer",
    "eines", "und", "oder", "aber", "auch", "noch", "nur", "schon", "mit", "ohne",
    "fuer", "für", "von", "vom", "zum", "zur", "zu", "im", "in", "an", "am", "auf",
    "aus", "bei", "bis", "nach", "vor", "ueber", "über", "unter", "durch", "gegen",
    "ist", "sind", "war", "wird", "werden", "wurde", "wurden", "hat", "haben",
    "kann", "koennen", "können", "soll", "sollen", "muss", "muessen", "müssen",
    "sich", "dich", "dir", "dein", "deine", "deinen", "deiner", "du", "es", "er",
    "sie", "wir", "ihr", "man", "als", "wie", "was", "wer", "wo", "wann", "warum",
    "jetzt", "neu", "neue", "neuer", "neues", "neuen", "macht", "machen", "mehr",
    "alle", "alles", "diese", "dieser", "dieses", "diesem", "ki", "ai", "the",
    "lassen", "laesst", "lässt", "bringt", "bringen", "wird's", "so", "dann",
}

# Markante KI-Entitäten/Produktnamen, die ein Thema eindeutig kennzeichnen –
# auch wenn sie kurz sind (würden sonst durch die Längenregel fallen).
_AI_ENTITIES = {
    "gpt", "glm", "qwen", "grok", "siri", "llama", "gemma", "gemini", "claude",
    "copilot", "dspark", "sora", "veo", "flash", "opus", "sonnet", "haiku",
    "perplexity", "notebooklm",
}

# Zu breite Begriffe: Hersteller- und Sammelnamen, die in vielen verschiedenen
# Stories auftauchen. Sie zählen NICHT als eigenständiges Themen-Signal, sonst
# gilt jede zweite Google-/Apple-Meldung als Dopplung.
_GENERIC_TOKENS = {
    # Firmennamen: tauchen in vielen VERSCHIEDENEN Stories auf – kein Themen-Signal.
    # (Firma+Produkt wie "Anthropic"+"Claude" galt sonst fälschlich als Duplikat.)
    "google", "apple", "microsoft", "meta", "amazon", "nvidia", "samsung",
    "openai", "anthropic", "mistral", "deepseek",
    "cloud", "store", "update", "updates", "modell", "modelle", "version",
    "launch", "release", "feature", "features", "tool", "tools", "app", "apps",
    "unternehmen", "nutzer", "nutzern", "funktion", "funktionen", "milliarden",
    "million", "millionen", "prozent", "studie", "bericht", "markt",
}


def _normalize_words(s: str) -> set:
    words = re.findall(r"[a-zäöüß0-9]+", s.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _significant_tokens(s: str) -> set:
    """Markante Tokens eines Textes: lange Inhaltswörter (Entitäten/Nomen) plus
    bekannte KI-Produktnamen, OHNE breite Hersteller-/Sammelbegriffe.
    Zwei geteilte markante Tokens = gleiches Thema."""
    words = re.findall(r"[a-zäöüß0-9]+", s.lower())
    return {w for w in words
            if w not in _STOPWORDS and w not in _GENERIC_TOKENS
            and (len(w) >= 5 or w in _AI_ENTITIES)}


def _too_similar(a: str, b: str, threshold: float = 0.5) -> bool:
    """Themengleichheit – greift auch bei unterschiedlicher Formulierung.
    Blockiert, wenn entweder die Wortüberlappung hoch ist (mit Mindest-Substanz
    von 4 gemeinsamen Inhaltswörtern – verhindert Fehlalarme bei kurzen Titeln)
    ODER zwei markante Entitäten/Begriffe geteilt werden (z.B. 'deepseek'+'dspark')."""
    set_a, set_b = _normalize_words(a), _normalize_words(b)
    if not set_a or not set_b:
        return False
    shared = set_a & set_b
    overlap = len(shared) / min(len(set_a), len(set_b))
    if overlap >= threshold and len(shared) >= 4:
        return True
    shared_sig = _significant_tokens(a) & _significant_tokens(b)
    # Mindestens ein ECHTER Produktname muss dabei sein – zwei zufällig geteilte
    # gewöhnliche Wörter ("globalen"+"wettlauf") sind kein Themen-Beweis
    return len(shared_sig) >= 2 and any(t in _AI_ENTITIES for t in shared_sig)


def _is_fresh(datum: str, max_age_days: int = 2) -> bool:
    try:
        d = datetime.strptime(datum.strip(), "%d.%m.%Y")
        age = (datetime.now() - d).days
        return -1 <= age <= max_age_days  # leichte Toleranz für Zeitzonen-Versatz
    except (ValueError, AttributeError):
        return True  # Datum nicht parsebar – nicht blockieren


def enforce_quality_gate(data: dict, published_corpus: list, recent_podcasts: list = None) -> tuple:
    """Letztes Sicherheitsnetz nach dem Editor-Pass: veraltete & (themen-)doppelte
    Meldungen entfernen. Vergleicht Titel + Zusammenfassung gegen die Vorausgaben."""
    removed = []
    seen_blobs = []
    kept_top_news = []
    for item in data.get("top_news", []):
        titel = item.get("titel", "")
        blob = (titel + " " + item.get("zusammenfassung", "")).strip()
        if not _is_fresh(item.get("datum", "")):
            print(f"  Qualitäts-Filter: '{titel[:50]}' zu alt – entfernt")
            removed.append(titel)
            continue
        # Echte Follow-ups (vom Editor verifiziert) duerfen bekannte Themen fortschreiben –
        # nur die tagesinterne Dopplung wird weiterhin geprueft
        corpus_check = seen_blobs if item.get("update") is True else published_corpus + seen_blobs
        if any(_too_similar(blob, t) for t in corpus_check):
            print(f"  Qualitäts-Filter: '{titel[:50]}' Themen-Duplikat – entfernt")
            removed.append(titel)
            continue
        seen_blobs.append(blob)
        kept_top_news.append(item)
    data["top_news"] = kept_top_news

    kept_praxis = []
    for item in data.get("praxis", []):
        titel = item.get("titel", "")
        blob = (titel + " " + item.get("zusammenfassung", "")).strip()
        if not _is_fresh(item.get("datum", ""), max_age_days=7):
            print(f"  Qualitäts-Filter: Praxis '{titel[:50]}' zu alt – entfernt")
            removed.append(titel)
            continue
        if any(_too_similar(blob, t) for t in published_corpus + seen_blobs):
            print(f"  Qualitäts-Filter: Praxis '{titel[:50]}' Themen-Duplikat – entfernt")
            removed.append(titel)
            continue
        seen_blobs.append(blob)
        kept_praxis.append(item)
    data["praxis"] = kept_praxis

    kept_schnell = []
    for item in data.get("schnelldurchlauf", []):
        text = item.get("text", "")
        if any(_too_similar(text, t) for t in published_corpus + seen_blobs):
            print(f"  Qualitäts-Filter: '{text[:50]}' Themen-Duplikat – entfernt")
            removed.append(text)
            continue
        seen_blobs.append(text)
        kept_schnell.append(item)
    data["schnelldurchlauf"] = kept_schnell

    pod_titel = data.get("podcast", {}).get("episoden_titel", "")
    if pod_titel and recent_podcasts and any(_too_similar(pod_titel, t) for t in recent_podcasts):
        print(f"  Qualitäts-Filter: Podcast '{pod_titel[:50]}' lief bereits – entfernt")
        data["podcast"] = {}
    return data, removed


def _generate_draft(prompt: str) -> dict:
    """Ein Gemini-Durchlauf mit Retry bei leerer ODER unbrauchbarer Antwort
    (z.B. am Token-Limit abgeschnittenes JSON)."""
    reason = "?"
    for attempt in range(3):
        response = call_gemini(prompt)
        candidates = response.get("candidates", [])
        if not candidates:
            raise ValueError(f"Keine Candidates: {json.dumps(response)[:300]}")
        parts = candidates[0].get("content", {}).get("parts", [])
        raw_text = "".join(p.get("text", "") for p in parts)
        if raw_text.strip():
            try:
                return normalize_data(extract_json(raw_text))
            except ValueError as e:
                reason = f"unbrauchbares JSON: {str(e)[:120]}"
        else:
            reason = f"leere Antwort (Finish: {candidates[0].get('finishReason', '?')})"
        if attempt < 2:
            print(f"Gemini-Antwort verworfen ({reason}) – Versuch {attempt + 2}/3 ...")
            time.sleep(15)
    raise ValueError(f"Gemini liefert nach 3 Versuchen nichts Brauchbares. Zuletzt: {reason}")


def get_newsletter_data() -> dict:
    published_titles = load_published_titles()
    published_corpus = load_published_corpus()
    recent_podcasts = load_recent_podcasts()
    if published_titles:
        print(f"  {len(published_titles)} Meldungen aus Vorausgaben werden geblockt")
    removed_total = []
    for gen_attempt in range(2):
        prompt = build_prompt(published_titles + removed_total, recent_podcasts,
                              retry_hinweis=(gen_attempt > 0))
        data = _generate_draft(prompt)
        print("Entwurf steht. Lasse Redaktionsleiter (2. Gemini-Durchlauf) gegenprüfen ...")
        data = run_editor_pass(data, published_titles + removed_total)
        data, removed = enforce_quality_gate(data, published_corpus, recent_podcasts)
        removed_total.extend(removed)
        if len(data.get("top_news", [])) >= 2:
            break
        if gen_attempt == 0:
            print(f"Nach Qualitätsfilter weniger als 2 Top-News – zweiter Anlauf "
                  f"({len(removed_total)} Themen zusätzlich gesperrt) ...")
    if not data.get("top_news") and not data.get("praxis") and not data.get("schnelldurchlauf"):
        # Kein Abbruch mehr: ehrliche Kompakt-Ausgabe statt Ausfall
        print("Keine Meldung hat die Qualitätsprüfung überlebt – baue ehrliche Kompakt-Ausgabe.")
        data["kompakt"] = True
        data["intro"] = ("Heute ist ein seltener Tag: Nichts von dem, was die KI-Welt gerade "
                         "diskutiert, wäre für dich wirklich neu – alles Wesentliche hattest du "
                         "schon in den letzten Ausgaben. Das ist auch eine Information: kein "
                         "FOMO nötig. Dafür lohnt sich die heutige Inspiration weiter unten.")
        data["podcast"] = data.get("podcast") or {}
        data["zahl_des_tages"] = data.get("zahl_des_tages") or {}
    elif 0 < len(data.get("top_news", [])) < 2:
        data["intro"] = (data.get("intro", "").strip() + " Heute ist die Ausgabe bewusst "
                         "kompakt – es gab schlicht wenig wirklich Neues, und lieber kurz "
                         "als künstlich aufgebläht.").strip()
    data["inspiration"] = get_inspiration()
    return data


# ── URL-Validierung: syntaktisch + kurzer Erreichbarkeits-Check ───────────────
def _url_dead(url: str) -> bool:
    """True nur bei eindeutig toten Links (404/410/DNS-Fehler). Bot-Blocker
    (403/429/999) und Timeouts gelten als lebendig – News-Sites blocken Scraper."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; NewsletterBot)"})
        with urllib.request.urlopen(req, timeout=6):
            return False
    except urllib.error.HTTPError as e:
        return e.code in (404, 410)
    except urllib.error.URLError:
        return True   # DNS-Fehler / Verbindung unmoeglich -> halluzinierte Domain
    except Exception:
        return False  # Timeout etc.: im Zweifel Link behalten


def validate_url(url: str, title: str = "", source: str = "") -> str:
    query = urllib.parse.quote(f"{title} {source}")
    fallback = f"https://www.google.com/search?q={query}"
    if not (url and url.startswith("http") and len(url) > 15):
        return fallback
    if _url_dead(url):
        print(f"  URL tot, ersetzt durch Suche: {url[:70]}")
        return fallback
    return url


def validate_all_urls(data: dict) -> dict:
    print("Validiere URLs (syntaktisch) ...")
    for item in data.get("top_news", []):
        item["url"] = validate_url(item.get("url", ""), item.get("titel", ""), item.get("quelle", ""))
    for item in data.get("praxis", []):
        item["url"] = validate_url(item.get("url", ""), item.get("titel", ""), item.get("quelle", ""))
    for item in data.get("schnelldurchlauf", []):
        item["url"] = validate_url(item.get("url", ""), item.get("text", ""), item.get("quelle", ""))
    pod = data.get("podcast", {})
    pod["url"] = validate_url(pod.get("url", ""), pod.get("episoden_titel", ""), pod.get("podcast_name", ""))
    return data


# ── Design-Konstanten (Modern Playful) ────────────────────────────────────────
FONT   = "'Helvetica Neue',Helvetica,Arial,sans-serif"
C_BG   = "#f4f4f4"
C_CARD = "#ffffff"
C_TEXT = "#1e293b"
C_MUTE = "#64748b"
C_BDR  = "#e2e8f0"

# Sektionsfarben
SEC = {
    "news":    {"emoji": "🚀", "color": "#4f46e5", "light": "#eef2ff"},
    "blitz":   {"emoji": "⚡", "color": "#ea580c", "light": "#fff7ed"},
    "podcast": {"emoji": "🎙️", "color": "#f43f5e", "light": "#fff1f2"},
    "tipp":    {"emoji": "💡", "color": "#d97706", "light": "#fffbeb"},
    "zahl":    {"emoji": "📊", "color": "#be185d", "light": "#fdf2f8"},
    "praxis":  {"emoji": "🏢", "color": "#0f766e", "light": "#f0fdfa"},
    "trend":   {"emoji": "📈", "color": "#9333ea", "light": "#faf5ff"},
}


def _escape_for_html(data: dict) -> dict:
    """Escapet alle Modell-Texte (ein '<' im Titel würde sonst das Layout zerschießen).
    Arbeitet auf einer Kopie – die Text-Version der Mail bleibt unangetastet."""
    data = copy.deepcopy(data)
    def esc(s):
        return html_mod.escape(s, quote=True)
    if isinstance(data.get("intro"), str):
        data["intro"] = esc(data["intro"])
    for lst_key in ("top_news", "praxis", "schnelldurchlauf"):
        for item in data.get(lst_key, []):
            for k, v in list(item.items()):
                if isinstance(v, str):
                    item[k] = v[:8] if k == "emoji" else esc(v)
    for dict_key in ("podcast", "zahl_des_tages"):
        for k, v in list(data.get(dict_key, {}).items()):
            if isinstance(v, str):
                data[dict_key][k] = esc(v)
    return data


def build_html(data: dict) -> str:
    data        = _escape_for_html(data)
    top_news    = data.get("top_news", [])
    praxis      = data.get("praxis", [])
    schnell     = data.get("schnelldurchlauf", [])
    podcast     = data.get("podcast", {})
    intro       = data.get("intro", "")
    inspiration  = data.get("inspiration", {})
    zahl_tages   = data.get("zahl_des_tages", {})
    day_of_year  = datetime.now().timetuple().tm_yday

    # Lesezeit-Schätzung (200 Wörter/Min)
    _words = sum(
        len((n.get('zusammenfassung','') + ' ' + n.get('take','')).split())
        for n in top_news
    )
    _words += sum(len(p.get('zusammenfassung','').split()) for p in praxis)
    _words += sum(len(s.get('text','').split()) for s in schnell)
    _words += len(podcast.get('warum_hoeren','').split())
    _words += len(intro.split())
    _words += len((inspiration.get('beschreibung','') + ' ' + inspiration.get('prompt','')).split())
    read_min = max(2, round(_words / 200))

    def badge(text: str, color: str, bg: str) -> str:
        return (f'<span style="display:inline-block;background:{bg};color:{color};'
                f'font-family:{FONT};font-size:11px;font-weight:700;letter-spacing:.5px;'
                f'text-transform:uppercase;padding:3px 10px;border-radius:20px;">{text}</span>')

    def section_title(s: dict, title: str) -> str:
        return f"""
        <tr><td style="padding:32px 0 18px;">
          <span style="font-family:{FONT};font-size:10px;font-weight:900;
                       color:{s['color']};letter-spacing:2.5px;text-transform:uppercase;
                       border-bottom:2px solid {s['color']};padding-bottom:6px;">
            {s['emoji']}&ensp;{title}
          </span>
        </td></tr>"""

    def news_block(item: dict, idx: int) -> str:
        take = item.get('take', '')
        take_row = f"""
          <tr><td colspan="2" style="padding:0 18px 14px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr><td style="background:{SEC['news']['light']};border-left:4px solid {SEC['news']['color']};
                             border-radius:0 8px 8px 0;padding:10px 14px;">
                <span style="font-family:{FONT};font-size:10px;font-weight:900;
                      color:{SEC['news']['color']};letter-spacing:1.5px;text-transform:uppercase;">
                  TAKE&ensp;</span>
                <span style="font-family:{FONT};font-size:13px;color:#1e293b;line-height:1.65;">
                  {take}</span>
              </td></tr>
            </table>
          </td></tr>""" if take else ''
        bedeutung = item.get('bedeutung', '')
        bedeutung_row = f"""
          <tr><td colspan="2" style="padding:0 18px 12px;">
            <span style="font-family:{FONT};font-size:13px;color:#0f766e;line-height:1.6;">
              ➜&ensp;<strong>Für dich heißt das:</strong> {bedeutung}
            </span>
          </td></tr>""" if bedeutung else ''
        return f"""
        <tr><td style="padding:0 0 14px;">
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="border-radius:12px;border:1px solid #eaecf2;background:#f9fafb;">
            <tr>
              <td style="padding:16px 18px 0;vertical-align:middle;">
                <span style="font-family:{FONT};font-size:11px;font-weight:600;color:{C_MUTE};">
                  {item.get('datum','')} &middot; {item.get('quelle','')}
                </span>
              </td>
              <td style="padding:12px 16px 0;text-align:right;vertical-align:top;width:36px;">
                <span style="font-family:{FONT};font-size:22px;font-weight:900;
                             color:{SEC['news']['color']};opacity:.18;line-height:1;">
                  {str(idx).zfill(2)}
                </span>
              </td>
            </tr>
            <tr><td colspan="2" style="padding:6px 18px 10px;">
              <a href="{item.get('url','#')}"
                 style="font-family:{FONT};font-size:17px;font-weight:800;
                        color:{C_TEXT};text-decoration:none;line-height:1.4;">
                {item.get('titel','')}
              </a>
            </td></tr>
            <tr><td colspan="2" style="padding:0 18px 14px;">
              <span style="font-family:{FONT};font-size:14px;color:#475569;line-height:1.75;">
                {item.get('zusammenfassung','')}
              </span>
            </td></tr>
            {bedeutung_row}
            {take_row}
            <tr><td colspan="2" style="padding:10px 18px 14px;border-top:1px solid #eaecf2;">
              <a href="{item.get('url','#')}"
                 style="font-family:{FONT};font-size:12px;font-weight:700;
                        color:{SEC['news']['color']};text-decoration:none;">
                Weiterlesen &rarr;
              </a>
            </td></tr>
          </table>
        </td></tr>"""

    def overview_row(emoji: str, text: str, url: str = "") -> str:
        inner = (f'<a href="{url}" style="color:{C_TEXT};text-decoration:none;">{text}</a>'
                 if url else text)
        return (f'<tr><td style="padding:0 0 8px;vertical-align:top;width:24px;">'
                f'<span style="font-size:14px;">{emoji}</span></td>'
                f'<td style="padding:0 0 8px 8px;">'
                f'<span style="font-family:{FONT};font-size:13px;font-weight:600;'
                f'color:{C_TEXT};line-height:1.5;">{inner}</span></td></tr>')

    overview_rows = "".join(
        overview_row("🚀", n.get("titel", ""), n.get("url", "")) for n in top_news[:5]
    )
    for p in praxis[:2]:
        if p.get("titel"):
            overview_rows += overview_row("🏢", p["titel"], p.get("url", ""))
    # Inspiration nur listen, wenn es auch echte News gibt – sonst wirkt die Box leer
    if overview_rows and inspiration.get("titel"):
        overview_rows += overview_row("💡", f"KI-Inspiration: {inspiration['titel']}")

    zahl_block = ""
    if zahl_tages.get("zahl"):
        zahl_block = f"""
      <tr><td style="padding:18px 0 0;">
        <table width="100%" cellpadding="0" cellspacing="0"
               style="background:linear-gradient(135deg,{SEC['zahl']['light']} 0%,#ffffff 100%);
                      border:1px solid #fbcfe8;border-radius:12px;">
          <tr>
            <td style="padding:18px 8px 18px 20px;vertical-align:middle;width:1%;">
              <span style="font-family:{FONT};font-size:34px;font-weight:900;
                           color:{SEC['zahl']['color']};letter-spacing:-1px;white-space:nowrap;">
                {zahl_tages.get('zahl','')}
              </span>
            </td>
            <td style="padding:18px 20px 18px 10px;vertical-align:middle;">
              <span style="font-family:{FONT};font-size:9px;font-weight:900;color:{SEC['zahl']['color']};
                           letter-spacing:1.5px;text-transform:uppercase;">Zahl des Tages</span><br>
              <span style="font-family:{FONT};font-size:13px;color:#374151;line-height:1.5;">
                {zahl_tages.get('kontext','')}
              </span>
              <span style="font-family:{FONT};font-size:11px;color:{C_MUTE};"> &middot; {zahl_tages.get('quelle','')}</span>
            </td>
          </tr>
        </table>
      </td></tr>""" if zahl_tages.get("zahl") else ""

    def blitz_row(item: dict, is_last: bool) -> str:
        quelle = item.get('quelle', '')
        link = (f'&ensp;<a href="{item.get("url","#")}" style="font-family:{FONT};font-size:12px;'
                f'font-weight:700;color:{SEC["blitz"]["color"]};text-decoration:none;'
                f'white-space:nowrap;">{quelle} &rarr;</a>') if quelle else ''
        border = '' if is_last else f'border-bottom:1px solid #fed7aa;'
        emoji = item.get('emoji', '') or '⚡'
        return (f'<tr><td style="padding:10px 0;vertical-align:top;width:22px;{border}">'
                f'<span style="font-size:13px;">{emoji}</span></td>'
                f'<td style="padding:10px 0 10px 8px;{border}">'
                f'<span style="font-family:{FONT};font-size:13px;color:#334155;line-height:1.6;">'
                f'{item.get("text","")}</span>{link}</td></tr>')

    blitz_rows = "".join(blitz_row(b, i == len(schnell[:6]) - 1) for i, b in enumerate(schnell[:6]))
    blitz_section = f"""
      {section_title(SEC['blitz'], 'Schnelldurchlauf')}
      <tr><td style="padding:0 0 0;">
        <table width="100%" cellpadding="0" cellspacing="0"
               style="background:{SEC['blitz']['light']};border-radius:12px;
                      border:1px solid #fed7aa;">
          <tr><td style="padding:6px 18px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              {blitz_rows}
            </table>
          </td></tr>
        </table>
      </td></tr>""" if blitz_rows else ""

    news_rows  = "".join(news_block(n, i+1) for i, n in enumerate(top_news))
    overview_box = f"""
      <tr><td style="padding:20px 0 0;">
        <table width="100%" cellpadding="0" cellspacing="0"
               style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;">
          <tr><td style="padding:14px 18px 6px;">
            <span style="font-family:{FONT};font-size:10px;font-weight:900;color:{C_MUTE};
                         letter-spacing:2px;text-transform:uppercase;">
              ⚡ Heute für dich drin
            </span>
          </td></tr>
          <tr><td style="padding:6px 18px 12px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              {overview_rows}
            </table>
          </td></tr>
        </table>
      </td></tr>""" if overview_rows else ""
    news_section = f"""
      {section_title(SEC['news'], 'Top News des Tages')}
      {news_rows}""" if news_rows else ""

    def praxis_block(item: dict) -> str:
        branche = badge(item.get('branche', ''), SEC['praxis']['color'], '#ccfbf1')
        return f"""
        <tr><td style="padding:0 0 14px;">
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="border-radius:12px;border:1px solid #99f6e4;background:{SEC['praxis']['light']};">
            <tr><td style="padding:16px 18px 8px;">
              <table width="100%" cellpadding="0" cellspacing="0"><tr>
                <td>{branche}</td>
                <td style="text-align:right;">
                  <span style="font-family:{FONT};font-size:11px;font-weight:600;color:{C_MUTE};">
                    {item.get('quelle','')}
                  </span>
                </td>
              </tr></table>
            </td></tr>
            <tr><td style="padding:0 18px 8px;">
              <a href="{item.get('url','#')}"
                 style="font-family:{FONT};font-size:16px;font-weight:800;
                        color:{C_TEXT};text-decoration:none;line-height:1.4;">
                {item.get('titel','')}
              </a>
            </td></tr>
            <tr><td style="padding:0 18px 14px;">
              <span style="font-family:{FONT};font-size:14px;color:#374151;line-height:1.7;">
                {item.get('zusammenfassung','')}
              </span>
            </td></tr>
          </table>
        </td></tr>"""

    praxis_rows = "".join(praxis_block(p) for p in praxis[:2])
    praxis_section = f"""
      {section_title(SEC['praxis'], 'KI in der Praxis')}
      {praxis_rows}""" if praxis_rows else ""

    podcast_section = f"""
      {section_title(SEC['podcast'], 'Podcast-Empfehlung')}
      <tr><td style="padding:0 0 0;">
        <table width="100%" cellpadding="0" cellspacing="0"
               style="border-radius:12px;border:1px solid #fecdd3;">
          <tr><td style="background:{SEC['podcast']['light']};border-radius:12px 12px 0 0;
                         padding:9px 18px 8px;border-bottom:1px solid #fecdd3;">
            <span style="font-family:{FONT};font-size:10px;font-weight:700;
                         color:{SEC['podcast']['color']};letter-spacing:2px;text-transform:uppercase;">
              {SEC['podcast']['emoji']}&ensp;{podcast.get('podcast_name','')}
            </span>
          </td></tr>
          <tr><td style="padding:14px 18px 16px;">
            <p style="margin:0 0 3px;font-family:{FONT};font-size:11px;color:{C_MUTE};">
              {podcast.get('datum','')}
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
      </td></tr>""" if podcast.get('episoden_titel') else ""
    insp_badge = badge(inspiration.get('kategorie', ''), SEC['tipp']['color'], '#fef3c7')
    insp_prompt = f"""
          <tr><td style="padding:0 20px 14px;">
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#0f172a;border-radius:8px;">
              <tr><td style="padding:12px 16px 14px;">
                <p style="margin:0;font-family:'Courier New',Courier,monospace;font-size:13px;
                          color:#e2e8f0;line-height:1.7;">{inspiration.get('prompt','')}</p>
              </td></tr>
            </table>
          </td></tr>""" if inspiration.get("prompt") else ""
    insp_tipp = f"""
          <tr><td style="padding:0 20px 14px;">
            <span style="font-family:{FONT};font-size:13px;color:#92400e;line-height:1.6;">
              💡 {inspiration.get('tipp','')}
            </span>
          </td></tr>""" if inspiration.get("tipp") else ""
    insp_link = f"""
          <tr><td style="padding:10px 20px 16px;border-top:1px solid #fde68a;">
            <a href="{inspiration.get('url','#')}"
               style="font-family:{FONT};font-size:12px;font-weight:700;
                      color:{SEC['tipp']['color']};text-decoration:none;">
              {inspiration.get('link_text','Ausprobieren')} &rarr;
            </a>
          </td></tr>""" if inspiration.get("url") else ""
    inspiration_section = f"""
      {section_title(SEC['tipp'], 'Deine KI-Inspiration')}
      <tr><td style="padding:0 0 0;">
        <table width="100%" cellpadding="0" cellspacing="0"
               style="background:{SEC['tipp']['light']};border-radius:12px;
                      border:1px solid #fde68a;">
          <tr><td style="padding:18px 20px 0;">
            <div style="margin-bottom:10px;">{insp_badge}</div>
            <h3 style="margin:0 0 10px;font-family:{FONT};font-size:16px;font-weight:700;
                       color:{C_TEXT};">{inspiration.get('titel','')}</h3>
            <p style="margin:0 0 14px;font-family:{FONT};font-size:14px;
                      color:#374151;line-height:1.75;">{inspiration.get('beschreibung','')}</p>
          </td></tr>
          {insp_prompt}
          {insp_tipp}
          {insp_link}
          <tr><td style="font-size:0;line-height:0;height:6px;">&nbsp;</td></tr>
        </table>
      </td></tr>""" if inspiration.get("titel") else ""


    top_titel = top_news[0].get("titel", "") if top_news else ""
    preheader = f"{top_titel} – und mehr in der heutigen Ausgabe."

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <title>KI-Newsletter – {TODAY}</title>
</head>
<body style="margin:0;padding:0;background:{C_BG};">
<!-- Preheader: unsichtbar, erscheint in der Inbox-Vorschau -->
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">
  {preheader}&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;
</div>
<table width="100%" cellpadding="0" cellspacing="0" style="background:{C_BG};">
<tr><td align="center" style="padding:24px 16px 48px;">
<table width="620" cellpadding="0" cellspacing="0" style="max-width:620px;width:100%;">

  <!-- HEADER -->
  <tr><td bgcolor="#1e1b4b" style="background:linear-gradient(135deg,#1e1b4b 0%,#4338ca 60%,#6d28d9 100%);
                 border-radius:16px 16px 0 0;padding:30px 36px 26px;">
    <p style="margin:0 0 8px;font-family:{FONT};font-size:10px;color:#818cf8;
              letter-spacing:3px;text-transform:uppercase;">
      TÄGLICH &nbsp;·&nbsp; KOSTENLOS &nbsp;·&nbsp; {read_min}&thinsp;MIN &nbsp;·&nbsp; AUSGABE&thinsp;#{day_of_year}
    </p>
    <h1 style="margin:0 0 8px;font-family:{FONT};font-size:30px;font-weight:900;
               color:#ffffff;letter-spacing:-.5px;line-height:1.15;">
      KI-Newsletter 🤖
    </h1>
    <p style="margin:0;font-family:{FONT};font-size:13px;color:#c7d2fe;line-height:1.5;">
      {TODAY} &nbsp;&middot;&nbsp; Kuratiert von Gemini 2.5 Flash &nbsp;&middot;&nbsp; Jeden Morgen im Postfach
    </p>
  </td></tr>

  <!-- BODY -->
  <tr><td style="background:{C_CARD};padding:4px 36px 40px;
                 border-radius:0 0 16px 16px;
                 box-shadow:0 8px 30px rgba(79,70,229,.08);">
    <table width="100%" cellpadding="0" cellspacing="0">

      <!-- INTRO -->
      <tr><td style="padding:26px 0 0;">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr><td style="border-left:3px solid #4338ca;padding:4px 0 4px 14px;">
            <p style="margin:0;font-family:{FONT};font-size:15px;color:#334155;line-height:1.8;">
              {intro}
            </p>
          </td></tr>
        </table>
      </td></tr>

      <!-- ZAHL DES TAGES -->
      {zahl_block}

      {overview_box}

      {news_section}

      <!-- KI IN DER PRAXIS -->
      {praxis_section}

      <!-- SEKTION 1B: SCHNELLDURCHLAUF -->
      {blitz_section}

      {podcast_section}

      {inspiration_section}

    </table>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="padding:28px 0 0;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="background:#f8fafc;border-radius:12px;padding:16px 20px;
                     border:1px solid #e2e8f0;text-align:center;">
        <p style="margin:0 0 6px;font-family:{FONT};font-size:14px;font-weight:700;color:{C_TEXT};">
          Was fehlt, was nervt, was willst du mehr davon? 💬
        </p>
        <p style="margin:0;font-family:{FONT};font-size:13px;color:#64748b;line-height:1.6;">
          Antworte einfach auf diese E-Mail – ich lese jede Antwort persönlich.
          Und wenn dir die Ausgabe gefallen hat: Leite sie an einen Kollegen weiter.
        </p>
      </td></tr>
      <tr><td style="padding:18px 0 0;text-align:center;">
        <p style="margin:0 0 4px;font-family:{FONT};font-size:12px;color:#94a3b8;line-height:1.8;">
          🤖 Automatisch kuratiert von Gemini 2.5 Flash &middot; GitHub Actions
        </p>
        <p style="margin:0;font-family:{FONT};font-size:11px;color:#cbd5e1;">
          Jeden Morgen &middot; 0&thinsp;€/Monat &middot; Ausgabe&thinsp;#{day_of_year}
        </p>
      </td></tr>
    </table>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


# ── E-Mail senden ─────────────────────────────────────────────────────────────
def build_text(data: dict) -> str:
    """Schlichte Text-Alternative zur HTML-Mail (bessere Spam-Bewertung)."""
    lines = [f"KI-NEWSLETTER – {TODAY}", ""]
    intro = data.get("intro", "")
    if intro:
        lines += [intro, ""]
    zahl = data.get("zahl_des_tages", {})
    if zahl.get("zahl"):
        lines += [f"ZAHL DES TAGES: {zahl['zahl']} – {zahl.get('kontext','')}", ""]
    if data.get("top_news"):
        lines.append("TOP NEWS")
        for n in data["top_news"]:
            lines.append(f"* {n.get('titel','')}")
            if n.get("zusammenfassung"):
                lines.append(f"  {n['zusammenfassung']}")
            if n.get("url"):
                lines.append(f"  {n['url']}")
        lines.append("")
    if data.get("praxis"):
        lines.append("KI IN DER PRAXIS")
        for p in data["praxis"]:
            lines.append(f"* [{p.get('branche','')}] {p.get('titel','')}")
            if p.get("zusammenfassung"):
                lines.append(f"  {p['zusammenfassung']}")
            if p.get("url"):
                lines.append(f"  {p['url']}")
        lines.append("")
    if data.get("schnelldurchlauf"):
        lines.append("SCHNELLDURCHLAUF")
        for s in data["schnelldurchlauf"]:
            lines.append(f"* {s.get('text','')}")
        lines.append("")
    pod = data.get("podcast", {})
    if pod.get("episoden_titel"):
        lines += [f"PODCAST: {pod['episoden_titel']} ({pod.get('podcast_name','')})",
                  pod.get("url", ""), ""]
    insp = data.get("inspiration", {})
    if insp.get("titel"):
        lines += [f"KI-INSPIRATION: {insp['titel']}", insp.get("beschreibung", ""), ""]
    lines.append("Antworte einfach auf diese E-Mail mit Feedback.")
    return "\n".join(lines)


def send_email(subject: str, html_body: str, to: str, text_body: str = ""):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = to
    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    for attempt in range(3):
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as smtp:
                smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
                smtp.sendmail(GMAIL_ADDRESS, to, msg.as_string())
            print(f"  ✓ Gesendet an {to}")
            return
        except Exception as e:
            if attempt < 2:
                print(f"  SMTP-Fehler bei {to} (Versuch {attempt+1}/3): {e} – warte 15s ...")
                time.sleep(15)
            else:
                raise


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
def run_daily():
    print("Rufe Gemini API auf (kann bis zu 60 Sekunden dauern) ...")
    data = get_newsletter_data()
    print("Gemini-Antwort erhalten. Validiere URLs ...")
    data = validate_all_urls(data)
    print("Baue E-Mail ...")
    html = build_html(data)
    text = build_text(data)
    if len(html) > 90_000:
        print(f"  WARNUNG: HTML ist {len(html)} Bytes gross – Gmail kappt Mails ab ~102 KB!")
    # Betreff: Top-Story als Aufhänger, Fallback generisch
    top_news = data.get("top_news", [])
    top_titel = top_news[0].get("titel", "").strip() if top_news else ""
    if data.get("kompakt"):
        subject = f"🤖 Heute nichts verpasst – die Kompakt-Ausgabe ({TODAY})"
    elif top_titel:
        if len(top_titel) > 70:
            top_titel = top_titel[:67].rstrip() + "..."
        subject = f"🤖 {top_titel}"
    else:
        subject = f"🤖 KI-Newsletter {TODAY} – Top News & KI-Tipps"
    sent_already = load_sent_recipients()
    todo = [r for r in RECIPIENTS if r not in sent_already]
    if sent_already:
        print(f"  {len(sent_already)} Empfänger haben die heutige Ausgabe bereits – nur Rest wird beliefert")
    print(f"Sende E-Mail an {len(todo)} Empfänger ...")
    for recipient in todo:
        send_email(subject, html, recipient, text)
        record_sent(recipient)
    print("Fertig! Newsletter wurde erfolgreich versandt.")
    save_published_titles(data)


def main():
    print(f"Starte KI-Newsletter für {TODAY} ...")
    if already_sent_today():
        print("Heute wurde bereits erfolgreich versendet – Backup-Lauf beendet sich.")
        return
    try:
        run_daily()
    except Exception as e:
        print(f"FEHLER: {type(e).__name__}: {e}", file=sys.stderr)
        try:
            _commit_history(f"chore: newsletter sent-log {TODAY} [skip ci]")
        except Exception:
            pass
        send_error_email(e)
        sys.exit(1)


if __name__ == "__main__":
    main()

