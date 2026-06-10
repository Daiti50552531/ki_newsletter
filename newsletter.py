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

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
]

def gemini_url(model: str) -> str:
    return (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={GEMINI_API_KEY}"
    )

TODAY = datetime.now().strftime("%d.%m.%Y")


# ── Statische Claude-Code-Tipp-Bibliothek (rotiert täglich) ──────────────────
CLAUDE_CODE_TIPPS = [
    {
        "titel": "Meeting-Protokoll in 30 Sekunden strukturieren",
        "anwendungsfall": "Dokumente",
        "beschreibung": "Kopiere deine Rohnotizen aus dem Meeting in Claude und nutze diesen Prompt: 'Strukturiere diese Meeting-Notizen in: (1) Besprochene Punkte, (2) Entscheidungen, (3) Offene Aufgaben mit Verantwortlichen und Deadline. Formuliere präzise, keine Füllsätze.' Du erhältst in Sekunden ein sauberes Protokoll, das du direkt versenden kannst.",
    },
    {
        "titel": "Status-Report in 5 Minuten statt 45",
        "anwendungsfall": "Selbstorganisation",
        "beschreibung": "Prompt: 'Ich bin Projektverantwortlicher und muss einen wöchentlichen Status-Report schreiben. Hier sind meine Stichpunkte: [deine Notizen]. Schreibe daraus einen professionellen Status-Report mit: Zusammenfassung, Stand der Meilensteine, Risiken/Blocker, nächste Schritte.' Du lieferst die Fakten, Claude den Text.",
    },
    {
        "titel": "Langen E-Mail-Thread auf Kern destillieren",
        "anwendungsfall": "Projektueberblick",
        "beschreibung": "Kopiere einen unübersichtlichen E-Mail-Verlauf in Claude: 'Destilliere aus diesem Thread: (1) Worum geht es wirklich? (2) Welche Positionen gibt es? (3) Was ist noch ungeklärt? (4) Was wäre ein konkreter nächster Schritt?' Du bekommst die Essenz in 5 Bullet Points statt 30 E-Mails lesen zu müssen.",
    },
    {
        "titel": "Langes Dokument auf Handlungsrelevanz scannen",
        "anwendungsfall": "Recherche",
        "beschreibung": "Statt ein 40-seitiges Konzept komplett zu lesen: Kopiere es in Claude mit: 'Ich bin [deine Rolle]. Was muss ich aus diesem Dokument wissen und wo muss ich handeln? Nenne nur die für mich relevanten Stellen, ignoriere den Rest.' Claude liest für dich und filtert was zählt.",
    },
    {
        "titel": "Schwierige E-Mail professionell formulieren",
        "anwendungsfall": "Dokumente",
        "beschreibung": "Vor einer heiklen E-Mail (Eskalation, Absage, kritisches Feedback): 'Ich muss folgendes kommunizieren: [Kernaussage in Stichpunkten]. Ton: sachlich, respektvoll, lösungsorientiert. Schreibe eine kurze E-Mail die direkt ist ohne zu verletzen.' Beschreibe Empfänger und Kontext für bessere Ergebnisse.",
    },
    {
        "titel": "Projektrisiken systematisch identifizieren",
        "anwendungsfall": "Projektueberblick",
        "beschreibung": "Prompt: 'Hier ist die Kurzbeschreibung meines Projekts: [Beschreibung]. Welche typischen Risiken treten bei solchen Projekten auf? Strukturiere nach Wahrscheinlichkeit und Auswirkung. Fokus auf Risiken die ich als Projektverantwortlicher beeinflussen kann.' Gut als Startpunkt für deine eigene Risikoanalyse.",
    },
    {
        "titel": "Präsentationsstruktur in Minuten entwickeln",
        "anwendungsfall": "Dokumente",
        "beschreibung": "Vor dem nächsten Deck: 'Ich halte eine 15-minütige Präsentation zu [Thema] vor [Zielgruppe]. Ziel: [Entscheidung/Information/Überzeugung]. Entwickle eine Gliederung mit 5-7 Folien und für jede Folie einen Satz Kernaussage.' Spar dir die leere-Folie-Starrstunde.",
    },
    {
        "titel": "Widersprüche in Anforderungsdokumenten aufdecken",
        "anwendungsfall": "Projektueberblick",
        "beschreibung": "Kopiere dein Lastenheft in Claude: 'Analysiere auf: (1) Widersprüche zwischen Anforderungen, (2) Unklare Formulierungen, (3) Fehlende Informationen die für Umsetzung notwendig wären.' Damit gehst du in Reviews mit konkreten Fragen statt vagen Bauchgefühlen.",
    },
    {
        "titel": "Retrospektive strukturiert vorbereiten",
        "anwendungsfall": "Selbstorganisation",
        "beschreibung": "Vor einer Projektretrospektive: 'Hier sind meine unsortierten Notizen zum Projektverlauf: [Notizen]. Strukturiere in: Was lief gut (Keep), was lief schlecht (Stop), was ändern wir (Start). Formuliere konkret, nicht allgemein.' Du gehst vorbereitet rein statt in der Retro erst nachzudenken.",
    },
    {
        "titel": "Aufgaben aus voller Inbox priorisieren",
        "anwendungsfall": "Selbstorganisation",
        "beschreibung": "Wenn deine Aufgabenliste überquillt: 'Hier sind meine aktuellen Aufgaben: [Liste]. Ich habe heute noch 3 Stunden. Priorisiere nach Eisenhower-Matrix und schlage vor, was ich heute erledige, was delegiere und was verschiebe.' Funktioniert auch mit kopierten E-Mails.",
    },
    {
        "titel": "Zahlen und KPIs in Management-Sprache übersetzen",
        "anwendungsfall": "Dokumente",
        "beschreibung": "Wenn du Kennzahlen kommunizieren musst: 'Hier sind die Zahlen unseres Projekts: [Zahlen]. Formuliere daraus 3-4 verständliche Sätze für ein Management-Update. Kein Fachjargon, klarer Trend, Bedeutung für unser Projektziel.' Ideal für kurze Steering-Committee-Updates.",
    },
    {
        "titel": "Lessons Learned Bericht halbautomatisch erstellen",
        "anwendungsfall": "Dokumente",
        "beschreibung": "Nach Projektabschluss: 'Hier sind meine Notizen zu was gut und schlecht lief: [Notizen]. Schreibe daraus einen Lessons-Learned-Bericht für unser Wiki. Format: Kontext, was passierte, warum, was wir beim nächsten Mal anders machen.' Statt dem Bericht den alle aufschieben – in 10 Minuten fertig.",
    },
    {
        "titel": "Schwierige Abstimmung vorbereiten",
        "anwendungsfall": "Selbstorganisation",
        "beschreibung": "Vor einem heiklen Gespräch: 'Ich möchte mit [Rolle] über [Thema] sprechen. Mein Ziel: [Ergebnis]. Mögliche Einwände: [deine Vermutungen]. Hilf mir meine Argumente zu strukturieren und auf typische Gegenargumente vorbereitet zu sein.' Geht auch für Gehaltsverhandlungen.",
    },
    {
        "titel": "Technisches Konzept für Nicht-Techniker vereinfachen",
        "anwendungsfall": "Dokumente",
        "beschreibung": "Wenn du ein technisches Thema vor Nicht-Technikern präsentieren musst: 'Erkläre [Konzept/Tool] in maximal 3 Sätzen so, dass ein CFO versteht warum es relevant ist und was es kostet. Keine Abkürzungen, kein Fachjargon, aber präzise.' Perfekt für die Folie die alle verstehen müssen.",
    },
    {
        "titel": "Change Request strukturiert bewerten",
        "anwendungsfall": "Projektueberblick",
        "beschreibung": "Wenn ein Änderungswunsch ins Projekt kommt: 'Hier ist unser Projektstand: [Beschreibung]. Jemand möchte folgendes ändern: [Change Request]. Welche typischen Auswirkungen auf Zeit, Aufwand und Risiko hätte das? Was sollte ich vor einer Entscheidung klären?' Hilft dir den CR sachlich zu bewerten statt bauchgefühlsbasiert.",
    },
    {
        "titel": "Fragenkatalog für Dienstleister-Gespräche erstellen",
        "anwendungsfall": "Recherche",
        "beschreibung": "Bevor du einen Anbieter briefst: 'Ich möchte [Leistung] von einem externen Dienstleister einkaufen. Welche Fragen sollte ich im Erstgespräch stellen um Qualität, Risiken und Eignung zu beurteilen? Fokus auf praktische Projekterfahrung, nicht Hochglanz-Präsentationen.' Damit kommst du informiert ins Gespräch.",
    },
    {
        "titel": "Eigene Arbeit auf Lücken prüfen lassen",
        "anwendungsfall": "Projektueberblick",
        "beschreibung": "Bevor du ein Konzept abgibst: 'Hier ist mein Entwurf: [Text]. Übernimm die Rolle eines kritischen Reviewers. Was fehlt? Wo ist die Argumentation schwach? Was würde ein erfahrener Kollege als erstes beanstanden?' Besser Claude findet die Lücken als dein Chef.",
    },
    {
        "titel": "Wöchentliche Selbstreflexion in 5 Minuten",
        "anwendungsfall": "Selbstorganisation",
        "beschreibung": "Jeden Freitag: 'Ich war diese Woche an folgenden Dingen beteiligt: [Liste]. Was waren meine größten Fortschritte? Wo habe ich Zeit verloren? Was nehme ich mir für nächste Woche vor? Formuliere das als kurzen Rückblick für mein Arbeitsjournal.' Nach 4 Wochen siehst du Muster die dir vorher nie aufgefallen wären.",
    },
    {
        "titel": "Unbekannte Fachbegriffe im eigenen Kontext erklären",
        "anwendungsfall": "Recherche",
        "beschreibung": "Wenn du in Dokumenten oder Meetings auf unbekannte Begriffe stößt: 'Erkläre mir [Begriff] so, als würde ich in der Projektleitung eines deutschen Großunternehmens arbeiten. Kein Fachjargon, praktisches Beispiel aus dem Unternehmensalltag.' Claude erklärt nicht abstrakt, sondern in deinem Kontext.",
    },
    {
        "titel": "Stakeholder für ein neues Projekt identifizieren",
        "anwendungsfall": "Projektueberblick",
        "beschreibung": "Prompt: 'Mein Projekt ist [Kurzbeschreibung] in einem deutschen Großunternehmen. Welche typischen Stakeholder sollte ich einbinden? Strukturiere nach: Wer ist betroffen, welche Interessen haben sie, wie kommuniziere ich am besten mit ihnen?' Als Checkliste damit du niemanden vergisst.",
    },
]


def get_claude_code_tipp() -> dict:
    day_of_year = datetime.now().timetuple().tm_yday
    return CLAUDE_CODE_TIPPS[(day_of_year - 1) % len(CLAUDE_CODE_TIPPS)]


# ── Prompt-des-Tages-Bibliothek (rotiert täglich, versetzt zu Claude-Tipps) ───
PROMPTS_DES_TAGES = [
    {
        "titel": "Meeting-Agenda die wirklich funktioniert",
        "kategorie": "Meetings",
        "prompt": "Ich habe ein [30-minütiges] Meeting zu [Thema] mit [Teilnehmer-Rollen, z.B. Projektleiter, IT, Fachbereich]. Erstelle eine strukturierte Agenda mit Zeitblöcken, einem klaren Meetingziel und einer konkreten Entscheidungsfrage am Ende.",
        "tipp": "Schick die Agenda 24h vorher an alle – das spart die ersten 10 Minuten Orientierungszeit.",
    },
    {
        "titel": "E-Mail-Thread in 3 Bullet Points",
        "kategorie": "Kommunikation",
        "prompt": "Hier ist ein E-Mail-Verlauf: [Thread einfügen]. Fasse ihn in genau 3 Bullet Points zusammen: (1) Worum geht es? (2) Was wurde entschieden oder ist offen? (3) Was ist mein nächster Schritt?",
        "tipp": "Ideal bevor du in ein Gespräch gehst – du brauchst keine 20 E-Mails mehr zu lesen.",
    },
    {
        "titel": "Entscheidung zwischen zwei Optionen durchdenken",
        "kategorie": "Analyse",
        "prompt": "Ich muss zwischen zwei Optionen entscheiden: Option A ist [Beschreibung], Option B ist [Beschreibung]. Meine wichtigsten Kriterien sind [z.B. Kosten, Zeit, Risiko]. Erstelle eine sachliche Pro/Contra-Analyse und empfehle eine Option mit Begründung.",
        "tipp": "Ergänze am Ende: 'Was würde ein erfahrener Kollege in meiner Situation wählen?' – das gibt eine zweite Perspektive.",
    },
    {
        "titel": "Kompliziertes Thema in 3 Sätzen erklären",
        "kategorie": "Kommunikation",
        "prompt": "Erkläre [kompliziertes Thema/Konzept/Tool] in maximal 3 Sätzen so, dass [Zielgruppe, z.B. Vorstand ohne IT-Kenntnisse] sofort versteht warum es relevant ist. Kein Fachjargon, kein Passiv, ein konkretes Beispiel.",
        "tipp": "Perfekt als Einstiegssatz für Präsentationen oder den ersten Absatz einer Entscheidungsvorlage.",
    },
    {
        "titel": "Wochenplanung in 5 Minuten",
        "kategorie": "Selbstorganisation",
        "prompt": "Hier sind alle meine Aufgaben und Termine für diese Woche: [Liste]. Meine wichtigsten Ziele bis Freitag sind: [Ziele]. Erstelle einen realistischen Wochenplan mit Prioritäten. Markiere was ich delegieren oder verschieben könnte.",
        "tipp": "Montagmorgen, 10 Minuten – spart dir täglich Entscheidungsfatigue.",
    },
    {
        "titel": "Feedback geben ohne zu verletzen",
        "kategorie": "Kommunikation",
        "prompt": "Ich muss folgendes Feedback an [Rolle, z.B. Kollege, Dienstleister] geben: [Kernkritik in Stichpunkten]. Formuliere das als konstruktives, lösungsorientiertes Feedback. Ton: direkt und respektvoll, nicht beschönigend.",
        "tipp": "Ergänze deinen eigenen Kontext: 'Die Person reagiert empfindlich auf X' – dann wird der Ton noch passender.",
    },
    {
        "titel": "Projektstand in einem Absatz",
        "kategorie": "Berichte",
        "prompt": "Mein Projekt [Projektname] hat folgenden Status: [Stichpunkte zu Stand, Verzögerungen, Risiken]. Schreibe daraus einen knappen Management-Update-Absatz (max. 5 Sätze): Was läuft, was ist kritisch, was ist der nächste Meilenstein.",
        "tipp": "Für wöchentliche Steering-Committee-Updates – spart das Formulieren und wirkt trotzdem professionell.",
    },
    {
        "titel": "Anforderungen auf Lücken prüfen",
        "kategorie": "Analyse",
        "prompt": "Hier sind die Anforderungen für [Projekt/Feature/Prozess]: [Anforderungen einfügen]. Prüfe auf: (1) Widersprüche, (2) unklare Formulierungen, (3) fehlende Informationen die für die Umsetzung notwendig wären. Sei konkret, nicht allgemein.",
        "tipp": "Vor dem nächsten Review-Meeting einsetzen – du gehst mit echten Fragen rein statt vagen Bauchgefühlen.",
    },
    {
        "titel": "Schwierige Situation im Gespräch vorbereiten",
        "kategorie": "Kommunikation",
        "prompt": "Ich muss [Situation, z.B. Verzögerung kommunizieren / Eskalation ansprechen / Nein sagen] in einem Gespräch mit [Rolle]. Mein Ziel ist [konkretes Ergebnis]. Bereite mich vor: Welche Einstiegssätze wirken deeskalierend? Welche Einwände kommen wahrscheinlich und wie reagiere ich?",
        "tipp": "5 Minuten vor dem Gespräch lesen – gibt Sicherheit ohne Skript auswendig lernen zu müssen.",
    },
    {
        "titel": "Lessons Learned strukturieren",
        "kategorie": "Berichte",
        "prompt": "Hier sind meine unsortierten Notizen zu Projekt [Name]: [Notizen]. Strukturiere daraus einen Lessons-Learned-Bericht mit: Was lief gut (und warum), was lief schlecht (und warum), was machen wir beim nächsten Mal konkret anders.",
        "tipp": "Direkt nach Projektabschluss – bevor alle Details verblasst sind. Dauert 15 Minuten statt 2 Stunden.",
    },
    {
        "titel": "Dienstleister-Angebot kritisch bewerten",
        "kategorie": "Analyse",
        "prompt": "Ich habe ein Angebot von [Dienstleister] für [Leistung] erhalten: [Angebot in Stichpunkten]. Was fehlt in diesem Angebot? Welche versteckten Risiken und Kosten könnte es geben? Welche 5 Fragen muss ich unbedingt stellen bevor ich unterschreibe?",
        "tipp": "Vor der Entscheidung einsetzen – du erkennst Lücken die im Angebot bewusst offen gelassen werden.",
    },
    {
        "titel": "Präsentation für Nicht-Experten bauen",
        "kategorie": "Präsentationen",
        "prompt": "Ich präsentiere [Thema] vor [Zielgruppe, z.B. Führungskräfte ohne Fachkenntnisse]. Dauer: [X Minuten]. Ziel: [Entscheidung herbeiführen / informieren / überzeugen]. Erstelle eine Gliederung mit max. 6 Folien und für jede Folie eine Kernaussage in einem Satz.",
        "tipp": "Eine Kernaussage pro Folie ist das wichtigste Prinzip guter Managementpräsentationen.",
    },
    {
        "titel": "Aufgaben nach Eisenhower priorisieren",
        "kategorie": "Selbstorganisation",
        "prompt": "Hier ist meine aktuelle Aufgabenliste: [Liste]. Sortiere nach Eisenhower-Matrix (dringend/wichtig). Markiere was ich heute erledige, was ich delegieren kann und was ich streichen sollte. Ich habe heute noch [X Stunden] zur Verfügung.",
        "tipp": "Wenn die Liste zu lang wirkt: Alles was nicht dringend UND wichtig ist, hat meist keine echte Deadline.",
    },
    {
        "titel": "Prozess für neue Kollegen dokumentieren",
        "kategorie": "Berichte",
        "prompt": "Ich möchte folgenden Prozess dokumentieren damit neue Kollegen ihn selbständig durchführen können: [Prozessbeschreibung in Stichpunkten]. Schreibe eine klare Schritt-für-Schritt-Anleitung. Markiere Stellen wo Fehler passieren und wie man sie vermeidet.",
        "tipp": "Füge am Ende hinzu: 'Was ist der häufigste Fehler an Schritt X?' – dann wird die Anleitung wirklich praxistauglich.",
    },
    {
        "titel": "Stakeholder identifizieren und priorisieren",
        "kategorie": "Projektmanagement",
        "prompt": "Mein Projekt: [Kurzbeschreibung]. Wer sind die typischen Stakeholder in einem deutschen Großunternehmen für so ein Vorhaben? Für jeden: Welche Interessen hat er, wie stark ist sein Einfluss, wie oft und wie kommuniziere ich mit ihm?",
        "tipp": "Am Anfang eines Projekts einsetzen – die häufigste Ursache für Projektprobleme ist ein vergessener Stakeholder.",
    },
    {
        "titel": "Change-Request-Auswirkung schnell einschätzen",
        "kategorie": "Projektmanagement",
        "prompt": "Mein Projekt ist [Kurzbeschreibung, aktueller Stand]. Jemand möchte folgende Änderung: [Change Request]. Welche Auswirkungen hat das typischerweise auf Zeit, Aufwand und Qualität? Was muss ich klären bevor ich ja oder nein sage?",
        "tipp": "Nie spontan einem Change Request zustimmen – mit diesem Prompt kommst du in 2 Minuten zu einer fundierten Antwort.",
    },
    {
        "titel": "Executive Summary schreiben",
        "kategorie": "Berichte",
        "prompt": "Hier ist mein vollständiges Dokument / mein Bericht: [Text einfügen]. Schreibe eine Executive Summary von max. einer halben Seite: Ausgangslage, Kernerkenntnisse, Empfehlung, nächste Schritte. Entscheider lesen nur die Summary – sie muss für sich allein verständlich sein.",
        "tipp": "Schreib die Executive Summary immer zuletzt, aber platziere sie ganz oben im Dokument.",
    },
    {
        "titel": "Workshop-Agenda vorbereiten",
        "kategorie": "Meetings",
        "prompt": "Ich moderiere einen [halbtägigen] Workshop zum Thema [Ziel des Workshops] mit [Anzahl] Teilnehmern aus [Bereichen]. Erstelle eine Agenda mit Timebox, Methoden und klarem Ziel für jeden Block. Das Endergebnis soll [konkretes Ergebnis, z.B. eine Entscheidung / ein Aktionsplan] sein.",
        "tipp": "Plane immer 20% Pufferzeit ein – Workshops dauern fast immer länger als geplant.",
    },
    {
        "titel": "Eigenen Text auf Schwächen prüfen",
        "kategorie": "Analyse",
        "prompt": "Hier ist mein Entwurf: [Text]. Übernimm die Rolle eines kritischen Reviewers. Was fehlt? Wo ist die Argumentation schwach oder nicht belegt? Was würde ein skeptischer Leser sofort hinterfragen? Formuliere 3-5 konkrete Verbesserungsvorschläge.",
        "tipp": "Besser Claude findet die Lücken als dein Chef. Direkt vor dem Abgeben einsetzen.",
    },
    {
        "titel": "Wochenrückblick und nächste Woche planen",
        "kategorie": "Selbstorganisation",
        "prompt": "Diese Woche habe ich folgendes erledigt / erlebt: [Stichpunkte]. Offene Punkte: [Liste]. Formuliere einen kurzen Wochenrückblick mit: (1) Top 3 Erfolge, (2) Was bremst mich noch, (3) Meine 3 wichtigsten Ziele für nächste Woche.",
        "tipp": "Freitagsnachmittag, 5 Minuten – gibt dir einen sauberen Wochenabschluss und einen klaren Montagsstart.",
    },
    {
        "titel": "Projektauftrag formulieren",
        "kategorie": "Projektmanagement",
        "prompt": "Ich starte ein neues Projekt: [Projektidee in Stichpunkten]. Erstelle einen einseitigen Projektauftrag mit: Ziel (SMART), Scope (was gehört dazu / was nicht), Stakeholder, grobe Meilensteine, offene Fragen die ich noch klären muss.",
        "tipp": "Ein guter Projektauftrag verhindert die 3 häufigsten Probleme: unklares Ziel, Scope Creep, vergessene Stakeholder.",
    },
    {
        "titel": "Eskalations-E-Mail professionell formulieren",
        "kategorie": "Kommunikation",
        "prompt": "Ich muss ein Problem eskalieren: [Problembeschreibung, was bereits versucht wurde, warum es steckt]. Empfänger: [Rolle, z.B. Abteilungsleiter]. Schreibe eine sachliche Eskalations-E-Mail: Problem klar benennen, bisherige Schritte, was ich jetzt brauche, konkreter Vorschlag für nächsten Schritt.",
        "tipp": "Ton: faktenbasiert, lösungsorientiert – keine Schuldzuweisungen. Führungskräfte eskalieren Probleme, nicht Personen.",
    },
    {
        "titel": "Onboarding-Plan für neue Kollegen",
        "kategorie": "Berichte",
        "prompt": "Ein neuer Kollege [Rolle] startet in meinem Team / Projekt. Erstelle einen 4-Wochen-Onboarding-Plan: Was muss er wissen, wen muss er kennenlernen, welche Aufgaben kann er in Woche 1/2/3/4 übernehmen? Kontext: [kurze Team-/Projektbeschreibung].",
        "tipp": "Guter Onboarding spart 2-3 Monate bis zur vollen Produktivität. Einmal erstellen, immer wieder nutzen.",
    },
    {
        "titel": "Verhandlung vorbereiten",
        "kategorie": "Kommunikation",
        "prompt": "Ich verhandle mit [Gegenüber, z.B. Lieferant, interner Bereich] über [Thema, z.B. Budget, Liefertermin, Ressourcen]. Meine Zielposition ist [X], meine Untergrenze ist [Y]. Was sind typische Verhandlungstaktiken die hier angewendet werden? Welche Argumente und Gegenargumente muss ich vorbereiten?",
        "tipp": "Kenne dein BATNA (Best Alternative to a Negotiated Agreement) bevor du verhandelst – dann verhandelst du aus einer Position der Stärke.",
    },
    {
        "titel": "Prozessfehler analysieren",
        "kategorie": "Analyse",
        "prompt": "Folgender Fehler ist in unserem Prozess aufgetreten: [Fehlerbeschreibung]. Führe eine 5-Why-Analyse durch: Warum ist es passiert? (5x Warum fragen bis zur Wurzelursache). Schlage dann 2-3 konkrete Maßnahmen vor die das Problem dauerhaft beheben.",
        "tipp": "Die erste Antwort auf 'Warum?' ist fast nie die echte Ursache – erst beim 4. oder 5. Warum wird es interessant.",
    },
    {
        "titel": "Team-Update formulieren das gelesen wird",
        "kategorie": "Kommunikation",
        "prompt": "Ich muss mein Team über folgenden Sachverhalt informieren: [Sachverhalt]. Die wichtigste Botschaft ist: [Kernaussage]. Was bedeutet das konkret für das Team? Schreibe ein kurzes Team-Update (max. 150 Wörter) das klar, direkt und handlungsorientiert ist.",
        "tipp": "Updates unter 150 Wörter werden gelesen. Updates über 300 Wörter werden überflogen oder ignoriert.",
    },
    {
        "titel": "Besprechungsprotokoll aus Stichpunkten",
        "kategorie": "Meetings",
        "prompt": "Hier sind meine Rohnotizen vom Meeting am [Datum] zum Thema [Thema]: [Notizen]. Erstelle ein sauberes Protokoll mit: Teilnehmer, Besprochene Punkte, Entscheidungen (mit Datum), Aufgaben (Wer macht Was bis Wann).",
        "tipp": "Versende das Protokoll innerhalb von 24h – danach erinnert sich kaum noch jemand an Details.",
    },
    {
        "titel": "Komplexes Dokument auf 1 Seite kürzen",
        "kategorie": "Berichte",
        "prompt": "Hier ist ein langes Dokument: [Text einfügen]. Destilliere es auf maximal eine DIN-A4-Seite (ca. 400 Wörter). Behalte: Ziel, Kernaussagen, Empfehlungen. Streiche: Wiederholungen, Füllsätze, Details die keine Entscheidungsrelevanz haben.",
        "tipp": "Wenn du nicht auf eine Seite kürzen kannst, ist das Dokument noch nicht fertig gedacht.",
    },
    {
        "titel": "Jahresgespräch vorbereiten",
        "kategorie": "Selbstorganisation",
        "prompt": "Ich bereite mein Jahresgespräch mit meiner Führungskraft vor. Meine wichtigsten Leistungen dieses Jahr: [Liste]. Meine Entwicklungswünsche: [Stichpunkte]. Erstelle eine strukturierte Vorbereitung: Was präsentiere ich, welche Ziele schlage ich vor, wie formuliere ich meine Gehaltsforderung sachlich?",
        "tipp": "Jahresgespräch ist eine Verhandlung – wer unvorbereitet reingeht, verlässt es meist mit dem gleichen Gehalt.",
    },
    {
        "titel": "Projekt-Kickoff-Fragen vorbereiten",
        "kategorie": "Projektmanagement",
        "prompt": "Ich nehme am Kickoff für Projekt [Kurzbeschreibung] teil. Welche 10 Fragen muss ich im Kickoff unbedingt stellen um später keine bösen Überraschungen zu erleben? Fokus auf: Ziele, Erwartungen, Ressourcen, Risiken, Entscheidungswege.",
        "tipp": "Im Kickoff gestellte Fragen sind immer akzeptiert – 3 Monate später gelten sie als Unwissenheit.",
    },
]


def get_prompt_des_tages() -> dict:
    day_of_year = datetime.now().timetuple().tm_yday
    # Versatz von 7 damit Prompt und Claude-Tipp nicht synchron rotieren
    return PROMPTS_DES_TAGES[(day_of_year + 6) % len(PROMPTS_DES_TAGES)]


# ── Statische Tool-Bibliothek (rotiert täglich, TAAFT-Stil) ───────────────────
TOOL_TIPPS = [
    {
        "name": "NotebookLM",
        "kategorie": "Recherche",
        "preis": "Kostenlos",
        "url": "https://notebooklm.google.com",
        "beschreibung": "Lade bis zu 50 Dokumente, PDFs oder YouTube-Links hoch und stelle Fragen direkt an deine Quellen – jede Antwort mit Zitatnachweis. Das Killer-Feature: Audio Overviews verwandeln deine Unterlagen in einen Podcast-Dialog, ideal fürs Pendeln. Für Projektdokumentation und Einarbeitung in neue Themen aktuell kaum zu schlagen.",
        "take": "Das unterschätzteste Gratis-Tool von Google. Wenn du nur ein neues Tool diese Woche testest: dieses.",
    },
    {
        "name": "Perplexity",
        "kategorie": "Recherche",
        "preis": "Freemium",
        "url": "https://www.perplexity.ai",
        "beschreibung": "Suchmaschine mit KI-Antworten und klickbaren Quellenangaben – statt zehn Tabs öffnest du eine Antwort mit Belegen. Besonders stark bei aktuellen Themen und Faktenrecherche, wo ChatGPT gern halluziniert. Die kostenlose Version reicht für den Alltag völlig aus.",
        "take": "Mein Standard für jede Recherche, bei der ich Quellen brauche. Google nutze ich fast nur noch für Navigation.",
    },
    {
        "name": "Gamma",
        "kategorie": "Präsentationen",
        "preis": "Freemium",
        "url": "https://gamma.app",
        "beschreibung": "Beschreibe dein Thema in zwei Sätzen oder füge deine Gliederung ein – Gamma baut daraus ein komplettes, ansehnliches Deck mit Layout und Bildern. Export nach PowerPoint funktioniert. Die Designs sind besser als das, was die meisten von uns manuell bauen.",
        "take": "Für interne Decks und erste Entwürfe ein massiver Zeitgewinn. Für das Vorstands-Deck danach manuell verfeinern.",
    },
    {
        "name": "Napkin AI",
        "kategorie": "Visualisierung",
        "preis": "Kostenlos (Beta)",
        "url": "https://www.napkin.ai",
        "beschreibung": "Du fügst Text ein, Napkin schlägt passende Visualisierungen vor: Diagramme, Flowcharts, Prozessgrafiken. Mit einem Klick eingefügt und anpassbar, Export als PNG oder SVG. Verwandelt Textwüsten in Folien, die Leute tatsächlich verstehen.",
        "take": "Genau das Tool für alle, die keine Designer sind, aber ständig Konzepte erklären müssen.",
    },
    {
        "name": "tl;dv",
        "kategorie": "Meetings",
        "preis": "Freemium",
        "url": "https://tldv.io",
        "beschreibung": "Zeichnet Teams-, Meet- und Zoom-Calls auf, transkribiert sie und erstellt automatisch Zusammenfassungen mit Action Items. Du kannst Momente im Meeting taggen und später per Suche wiederfinden. DSGVO-konform mit EU-Hosting-Option – wichtig fürs Unternehmensumfeld.",
        "take": "Wer viele Meetings hat und danach Protokolle schreiben muss, spart hier echte Stunden pro Woche.",
    },
    {
        "name": "DeepL Write",
        "kategorie": "Schreiben",
        "preis": "Kostenlos",
        "url": "https://www.deepl.com/write",
        "beschreibung": "Verbessert deutsche und englische Texte stilistisch: präziser, professioneller oder lockerer – du wählst den Ton. Anders als ChatGPT schreibt es deinen Text nicht komplett um, sondern schlägt gezielte Verbesserungen vor. Vom deutschen Anbieter, läuft komplett im Browser.",
        "take": "Für wichtige E-Mails der schnellste Qualitäts-Boost überhaupt. 30 Sekunden, merklich besserer Text.",
    },
    {
        "name": "Claude Projects",
        "kategorie": "Wissensarbeit",
        "preis": "Ab 18€/Monat (Pro)",
        "url": "https://claude.ai",
        "beschreibung": "Lege pro Thema ein Projekt an und hinterlege Kontext-Dokumente und Anweisungen, die in jedem Chat automatisch verfügbar sind. Statt jedes Mal alles neu zu erklären, kennt Claude dein Projekt, deine Rolle und deinen Stil. Ideal für wiederkehrende Aufgaben wie Status-Reports oder Kundenkommunikation.",
        "take": "Das Feature, das aus Claude ein echtes Arbeitswerkzeug macht. Der Unterschied zu losen Chats ist enorm.",
    },
    {
        "name": "Notion AI",
        "kategorie": "Organisation",
        "preis": "Add-on, ca. 10€/Monat",
        "url": "https://www.notion.com/product/ai",
        "beschreibung": "KI direkt in deinem Wiki und deinen Notizen: Zusammenfassen, Übersetzen, Action Items extrahieren, Datenbanken befragen. Der Vorteil gegenüber externen Chatbots: Die KI kennt deinen gesamten Workspace und durchsucht ihn. Q&A über alle Team-Dokumente hinweg ist der eigentliche Mehrwert.",
        "take": "Lohnt sich erst, wenn dein Team Notion wirklich als zentrale Wissensbasis nutzt – dann aber richtig.",
    },
    {
        "name": "Zapier",
        "kategorie": "Automatisierung",
        "preis": "Freemium",
        "url": "https://zapier.com",
        "beschreibung": "Verbindet über 7.000 Apps ohne Code: E-Mail-Anhänge automatisch in Ablagen sortieren, Formular-Antworten in Tabellen schreiben, Slack-Benachrichtigungen bei neuen Einträgen. Mit den KI-Schritten kannst du mittlerweile auch Texte klassifizieren oder zusammenfassen lassen – mitten in der Automatisierung.",
        "take": "Fang mit einem nervigen, wiederkehrenden Handgriff an und automatisiere genau den. Der Rest kommt von allein.",
    },
    {
        "name": "Lovable",
        "kategorie": "Eigene Tools bauen",
        "preis": "Freemium",
        "url": "https://lovable.dev",
        "beschreibung": "Beschreibe eine kleine Web-App auf Deutsch oder Englisch – Lovable baut sie komplett: Oberfläche, Logik, Datenbank. Ein Urlaubsplaner fürs Team, ein Feedback-Formular, ein internes Dashboard: in Minuten statt Wochen. Kein Entwickler nötig, Ergebnis direkt teilbar per Link.",
        "take": "Die schnellste Art zu erleben, was 'eigene KI-Helfer bauen' heute bedeutet. Erster Prototyp in 15 Minuten.",
    },
    {
        "name": "Google AI Studio",
        "kategorie": "Experimentieren",
        "preis": "Kostenlos",
        "url": "https://aistudio.google.com",
        "beschreibung": "Der direkte Zugang zu Googles Gemini-Modellen ohne Abo: lange Dokumente analysieren, Videos befragen, Bildschirm teilen und live Fragen stellen. Bis zu eine Million Token Kontext – ganze Bücher oder Projektordner passen in einen Prompt. Versteckt sich hinter einem Entwickler-Look, ist aber für jeden bedienbar.",
        "take": "Das großzügigste Gratis-Angebot im KI-Markt. Perfekt um Gemini zu testen, bevor du irgendwas abonnierst.",
    },
    {
        "name": "Le Chat (Mistral)",
        "kategorie": "Chat-Assistent",
        "preis": "Freemium",
        "url": "https://chat.mistral.ai",
        "beschreibung": "Der ChatGPT-Konkurrent aus Frankreich: schnelle Antworten, Websuche, Dokumenten-Analyse und Bildgenerierung. Für Unternehmen interessant, weil europäisch gehostet und DSGVO-freundlicher als US-Anbieter. Qualitativ nicht ganz auf GPT- oder Claude-Niveau, aber näher dran als viele denken.",
        "take": "Wenn dein Unternehmen bei US-Clouds zögert: Das hier ist das Argument, trotzdem mit KI zu arbeiten.",
    },
    {
        "name": "ElevenLabs",
        "kategorie": "Audio",
        "preis": "Freemium",
        "url": "https://elevenlabs.io",
        "beschreibung": "Verwandelt Text in natürlich klingende Sprache – auch auf Deutsch und in deiner eigenen geklonten Stimme. Praktisch für Schulungsvideos, Produkt-Demos oder um lange Dokumente unterwegs als Audio zu hören. Die Qualität ist von echten Sprechern kaum zu unterscheiden.",
        "take": "Für E-Learning und interne Videos ein Gamechanger. Niemand muss mehr selbst einsprechen oder Sprecher buchen.",
    },
    {
        "name": "Canva Magic Studio",
        "kategorie": "Design",
        "preis": "Freemium",
        "url": "https://www.canva.com/magic",
        "beschreibung": "Canvas KI-Werkzeuge: Bilder generieren und bearbeiten, Texte umschreiben, ganze Designs aus einer Beschreibung erstellen. Magic Resize passt ein Design automatisch für alle Formate an – ein Social-Post wird zu Folie, Banner und Story. Für alle, die Design-Aufgaben haben, aber keine Designer sind.",
        "take": "Wenn du eh Canva nutzt, schalte die Magic-Features frei – die sparen mehr Zeit als die meisten Einzeltools.",
    },
    {
        "name": "LanguageTool",
        "kategorie": "Schreiben",
        "preis": "Freemium",
        "url": "https://languagetool.org",
        "beschreibung": "Grammatik- und Stilprüfung speziell stark im Deutschen – deutlich gründlicher als die Word-Rechtschreibprüfung. Als Browser-Extension prüft es überall: E-Mails, Wiki-Einträge, Formulare. Die KI-Umformulierung schlägt bessere Satzvarianten vor, ohne den Sinn zu verändern.",
        "take": "Die Browser-Extension einmal installieren und nie wieder peinliche Tippfehler in wichtigen Mails.",
    },
    {
        "name": "Granola",
        "kategorie": "Meetings",
        "preis": "Freemium",
        "url": "https://www.granola.ai",
        "beschreibung": "Meeting-Notiz-Tool mit anderem Ansatz: Es tritt nicht als Bot ins Meeting ein, sondern hört lokal mit und veredelt deine eigenen Stichpunkte zu vollständigen Notizen. Niemand sieht einen Aufnahme-Hinweis, die Notizen bleiben deine. Aktuell eines der gehyptesten Produktivitäts-Tools – zu Recht.",
        "take": "Eleganter als Bot-Lösungen, weil deine eigenen Gedanken die Struktur vorgeben und die KI nur auffüllt.",
    },
    {
        "name": "Ideogram",
        "kategorie": "Bilder",
        "preis": "Freemium",
        "url": "https://ideogram.ai",
        "beschreibung": "Bildgenerator mit einer Spezialität, an der andere scheitern: lesbarer Text im Bild. Poster, Slide-Hintergründe, Diagramm-Headers mit korrekt geschriebenen Wörtern. Für Arbeitsgrafiken oft nützlicher als Midjourney, weil Beschriftungen einfach stimmen.",
        "take": "Sobald Text im Bild vorkommen soll, ist das hier die erste Wahl – nicht DALL-E, nicht Midjourney.",
    },
    {
        "name": "Goblin Tools",
        "kategorie": "Selbstorganisation",
        "preis": "Kostenlos",
        "url": "https://goblin.tools",
        "beschreibung": "Eine Sammlung kleiner KI-Helfer: 'Magic ToDo' zerlegt überwältigende Aufgaben in machbare Schritte, der 'Formalizer' übersetzt zwischen locker und förmlich, der 'Judge' prüft den Tonfall deiner Nachricht. Ursprünglich für Menschen mit ADHS gebaut, hilft aber jedem mit voller Aufgabenliste.",
        "take": "Klingt unscheinbar, aber Magic ToDo ist die beste Anti-Prokrastinations-Hilfe, die ich kenne.",
    },
    {
        "name": "Krisp",
        "kategorie": "Meetings",
        "preis": "Freemium",
        "url": "https://krisp.ai",
        "beschreibung": "KI-Geräuschunterdrückung für alle Calls: Hundebellen, Baustelle, Großraumbüro – weg. Funktioniert mit jedem Meeting-Tool, weil es sich als virtuelles Mikrofon dazwischenschaltet. Inzwischen auch mit Transkription und Meeting-Zusammenfassungen.",
        "take": "Für alle im Homeoffice mit Nebengeräuschen die 5-Minuten-Installation, die jede Call-Qualität rettet.",
    },
    {
        "name": "Suno",
        "kategorie": "Kreativ",
        "preis": "Freemium",
        "url": "https://suno.com",
        "beschreibung": "Erstellt komplette Songs aus einer Textbeschreibung – Musik, Gesang, Text, fertig produziert. Im Arbeitskontext überraschend nützlich: Jingles für interne Videos, ein Teamsong fürs Offsite, Audio-Branding für Präsentationen. Und ehrlich: Es macht einfach Spaß.",
        "take": "Kein Pflicht-Tool, aber der sicherste Weg, Kollegen in 2 Minuten zum Staunen zu bringen, was KI heute kann.",
    },
    {
        "name": "Excalidraw",
        "kategorie": "Visualisierung",
        "preis": "Kostenlos",
        "url": "https://excalidraw.com",
        "beschreibung": "Whiteboard-Tool im Handskizzen-Look, das mit KI-Unterstützung Diagramme aus Textbeschreibungen generiert ('Text to Diagram'). Architektur-Skizzen, Prozessabläufe, Mindmaps – ohne Anmeldung direkt im Browser. Der Skizzen-Stil signalisiert 'Entwurf' und lädt zu Feedback ein, statt fertig zu wirken.",
        "take": "Perfekt für frühe Konzeptphasen, wo Hochglanz-Diagramme falsche Verbindlichkeit suggerieren würden.",
    },
]


def get_tool_tipp() -> dict:
    day_of_year = datetime.now().timetuple().tm_yday
    # Versatz von 13 damit Tool, Prompt und Claude-Tipp nicht synchron rotieren
    return TOOL_TIPPS[(day_of_year + 13) % len(TOOL_TIPPS)]


# ── Prompt ────────────────────────────────────────────────────────────────────
PROMPT = f"""Du bist Chefredakteur eines deutschsprachigen KI-Newsletters fuer Wissensarbeiter.
Heute ist der {TODAY}. Nutze Google Search zur Recherche. Alle Texte auf Deutsch.

--- ZIELGRUPPE ---
Wissensarbeiter und Projektverantwortliche in deutschen Unternehmen. Keine Entwickler, keine Investoren, keine Startup-Gruender.
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
STRIKTE REGEL: Nur Nachrichten der letzten 24 Stunden. Artikel aelter als 24h sind VERBOTEN.
Pruefe das Veroeffentlichungsdatum jedes Artikels explizit per Suche bevor du ihn aufnimmst.
Wenn du das Datum eines Artikels nicht mit Sicherheit bestaetigen kannst – lass ihn weg.
Lieber 3 frische Nachrichten als 5 mit alten dabei. Qualitaet vor Quantitaet.
Podcast-Empfehlung: Die aktuellste Episode eines der gelisteten Podcasts aus den letzten 7 Tagen.
TOP-PRIORITAET: Neue Modell-Releases (ChatGPT, Claude, Gemini, Llama, DeepSeek, Mistral usw.),
neue APIs und SDK-Versionen – diese IMMER aufnehmen wenn in den letzten 24h veroeffentlicht.
Suche explizit nach: "site:techcrunch.com after:{TODAY}" oder aehnlichen Datumsfiltern.

--- BLACKLIST (niemals verwenden) ---
AInauten, TAAFT, Doppelgaenger Newsletter/Podcast, AI Daily Brief

--- QUELLEN ---
News (englisch): TechCrunch, The Verge, Wired, Ars Technica, MIT Technology Review, Bloomberg Technology, The Information, VentureBeat, Reuters Technology
News (deutsch): The Decoder (the-decoder.de), heise online, t3n
Communities: Hacker News, Reddit (r/LocalLLaMA, r/machinelearning, r/artificial), DEV Community, GitHub Trending
Analyse: Hugging Face Blog, Import AI, Stratechery, Papers With Code
Asien: Quellen zu DeepSeek, Qwen und anderen asiatischen Open-Source-Modellen
Podcasts: Lex Fridman, Hard Fork NYT, Practical AI, Latent Space, No Priors, TWIML, Dwarkesh Podcast, BG2 Pod

--- NEWS SCORING (Rangfolge – der wichtigste Filter) ---
Der zentrale Test fuer jede News: "Kann der Leser damit HEUTE etwas anfangen?"
PRIORITAET 1: Neue Features die AB SOFORT verfuegbar sind, in Tools die Wissensarbeiter
taeglich nutzen (ChatGPT, Gemini, Claude, Microsoft Copilot/Office, Notion, Teams, DeepL).
Ein kleines Feature das gestern fuer alle ausgerollt wurde schlaegt eine grosse Ankuendigung
mit Warteliste oder "coming soon".
PRIORITAET 2: Neue Modell-Releases und Open-Source-Durchbrueche (GPT, Claude, Gemini, Llama,
DeepSeek, Mistral usw.), neue APIs und Agenten-Faehigkeiten.
PRIORITAET 3: Strategische Marktverschiebungen mit direkter Auswirkung auf den Arbeitsalltag.
LIMIT: Maximal EINE reine Strategie-/Branchen-News pro Ausgabe. Der Rest muss praktisch nutzbar sein.
EU-CHECK: Pruefe bei jedem Feature ob es in der EU/Deutschland verfuegbar ist. Wenn nicht
oder erst spaeter, MUSS das im Take stehen (z.B. "In der EU noch nicht verfuegbar").
ABLEHNEN: Reine Aktienkurse und Finanzmeldungen, oberflaechliches PR ohne Substanz,
akademische Forschung ohne praktischen Anwendungsfall, Startup-Finanzierungsnews ohne technischen Kern

--- AUSGABE ---
Gib ausschliesslich gueltiges JSON zurueck, ohne Markdown-Formatierung, ohne Erklaerungen:

{{
  "intro": "3-4 Saetze Einleitung im Stil eines Kollegen der den Newsletter selbst liest. Beginne mit 'Moin!' oder einer konkreten Beobachtung. PFLICHT: Nenne eine spezifische Zahl, ein konkretes Faktum oder eine ueberraschende Wendung aus den heutigen News – keine vagen Teaser wie 'interessante Entwicklungen'. Schliesse mit einem kurzen Hinweis was heute noch drin ist. KEINE Floskeln wie 'Willkommen zur neuen Ausgabe' oder 'Im heutigen Newsletter'.",
  "top_news": [
    {{
      "titel": "Spezifischer Titel der zeigt was sich aendert – nicht nur was passiert ist",
      "zusammenfassung": "3-5 Saetze auf Deutsch: Erst kurzer Kontext (warum passiert das gerade?), dann was genau passiert ist, dann konkrete Details und erste Auswirkungen. Nicht nur berichten – einordnen. Keine generischen Saetze wie 'Dies ist ein wichtiger Schritt'.",
      "take": "1-2 Saetze klare Empfehlung: Lohnt sich das Ausprobieren? Abwarten? Wirklich wichtig oder Hype? Schwaechen und Einschraenkungen koennen und sollen genannt werden wenn vorhanden.",
      "quelle": "Name der Quelle",
      "url": "https://direktlink-zum-artikel/nicht-zur-homepage",
      "datum": "TT.MM.YYYY"
    }}
  ],
  "schnelldurchlauf": [
    {{
      "text": "Ein einziger pointierter Satz der die Meldung komplett erfasst – konkret, kein Clickbait",
      "quelle": "Name der Quelle",
      "url": "https://direktlink-zum-artikel"
    }}
  ],
  "podcast": {{
    "episoden_titel": "...",
    "podcast_name": "...",
    "warum_hoeren": "2-3 Saetze auf Deutsch",
    "url": "https://...",
    "datum": "TT.MM.YYYY"
  }}
}}

REGELN:
- top_news: 3 BIS 4 Eintraege – nur die staerksten Stories, streng kuratiert
- schnelldurchlauf: 4 BIS 6 Einzeiler – interessante Meldungen die keine Top-Story sind, ebenfalls max. 24h alt
- Eine Meldung erscheint ENTWEDER in top_news ODER im schnelldurchlauf, nie in beiden
- Alle Daten im Format TT.MM.YYYY
- URLs direkt zum Artikel (nicht Homepage), Fallback: https://www.google.com/search?q=titel+quelle
"""


# ── Gemini API Call (mit Retry + Model-Fallback bei 503) ─────────────────────
def call_gemini() -> dict:
    payload = {
        "tools": [{"googleSearch": {}}],
        "contents": [{"role": "user", "parts": [{"text": PROMPT}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 16384,
        },
    }
    data = json.dumps(payload).encode("utf-8")

    max_attempts = 3  # max 2+4 Min Wartezeit pro Modell → passt sicher in 30-Min-Timeout
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
                if e.code == 503 and attempt < max_attempts - 1:
                    wait = 120 * (attempt + 1)  # 2 Min, 4 Min
                    print(f"  warte {wait}s ...")
                    time.sleep(wait)
                elif e.code == 503:
                    print(f"  {model} dauerhaft überlastet – wechsle Modell.")
                    break
                elif e.code == 429:
                    print(f"  {model} Quota erschöpft – wechsle Modell.")
                    break
                elif e.code == 404:
                    print(f"  {model} nicht gefunden – wechsle Modell.")
                    break
                else:
                    raise RuntimeError(f"Gemini {model} HTTP {e.code}: {body[:600]}")
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


def get_newsletter_data() -> dict:
    for attempt in range(3):
        response = call_gemini()
        candidates = response.get("candidates", [])
        if not candidates:
            raise ValueError(f"Keine Candidates: {json.dumps(response)[:300]}")
        parts = candidates[0].get("content", {}).get("parts", [])
        raw_text = "".join(p.get("text", "") for p in parts)
        if raw_text.strip():
            data = extract_json(raw_text)
            data["claude_code_tipp"] = get_claude_code_tipp()
            data["prompt_des_tages"] = get_prompt_des_tages()
            data["tool_tipp"] = get_tool_tipp()
            return data
        # Leere Antwort trotz STOP – nochmal versuchen
        reason = candidates[0].get("finishReason", "?")
        if attempt < 2:
            print(f"Gemini leere Antwort (Finish: {reason}) – Versuch {attempt + 2}/3 ...")
            time.sleep(15)
        else:
            raise ValueError(f"Gemini liefert nach 3 Versuchen keinen Text. Finish-Reason: {reason}")


# ── URL-Validierung (nur syntaktisch – kein HTTP, News-Sites blockieren HEAD) ─
def validate_url(url: str, title: str = "", source: str = "") -> str:
    if url and url.startswith("http") and len(url) > 15:
        return url
    query = urllib.parse.quote(f"{title} {source}")
    return f"https://www.google.com/search?q={query}"


def validate_all_urls(data: dict) -> dict:
    print("Validiere URLs (syntaktisch) ...")
    for item in data.get("top_news", []):
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
    "tool":    {"emoji": "🧰", "color": "#059669", "light": "#ecfdf5"},
    "claude":  {"emoji": "🤖", "color": "#7c3aed", "light": "#f5f3ff"},
    "prompt":  {"emoji": "🎯", "color": "#0891b2", "light": "#ecfeff"},
    "tipp":    {"emoji": "✨", "color": "#d97706", "light": "#fffbeb"},
}


def build_html(data: dict) -> str:
    top_news    = data.get("top_news", [])
    schnell     = data.get("schnelldurchlauf", [])
    podcast     = data.get("podcast", {})
    intro       = data.get("intro", "")
    claude_tipp  = data.get("claude_code_tipp", {})
    prompt_tages = data.get("prompt_des_tages", {})
    tool_tipp    = data.get("tool_tipp", {})
    day_of_year  = datetime.now().timetuple().tm_yday

    # Lesezeit-Schätzung (200 Wörter/Min)
    _words = sum(
        len((n.get('zusammenfassung','') + ' ' + n.get('take','')).split())
        for n in top_news
    )
    _words += sum(len(s.get('text','').split()) for s in schnell)
    _words += len(podcast.get('warum_hoeren','').split())
    _words += len(claude_tipp.get('beschreibung','').split())
    _words += len(tool_tipp.get('beschreibung','').split())
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
    if tool_tipp.get("name"):
        overview_rows += overview_row("🧰", f"Tool des Tages: {tool_tipp['name']}")
    if prompt_tages.get("titel"):
        overview_rows += overview_row("🎯", f"Prompt des Tages: {prompt_tages['titel']}")

    def blitz_row(item: dict, is_last: bool) -> str:
        quelle = item.get('quelle', '')
        link = (f'&ensp;<a href="{item.get("url","#")}" style="font-family:{FONT};font-size:12px;'
                f'font-weight:700;color:{SEC["blitz"]["color"]};text-decoration:none;'
                f'white-space:nowrap;">{quelle} &rarr;</a>') if quelle else ''
        border = '' if is_last else f'border-bottom:1px solid #fed7aa;'
        return (f'<tr><td style="padding:10px 0;vertical-align:top;width:22px;{border}">'
                f'<span style="font-size:13px;">⚡</span></td>'
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
    anw_badge  = badge(claude_tipp.get('anwendungsfall', ''), SEC['claude']['color'], '#ede9fe')
    pdt_badge  = badge(prompt_tages.get('kategorie', ''), SEC['prompt']['color'], '#cffafe')
    tool_kat_badge   = badge(tool_tipp.get('kategorie', ''), SEC['tool']['color'], '#d1fae5')
    tool_preis_badge = badge(tool_tipp.get('preis', ''), '#475569', '#e2e8f0')

    top_titel = top_news[0].get("titel", "") if top_news else ""
    preheader = f"{top_titel} – und mehr in der heutigen Ausgabe."

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
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
  <tr><td style="background:linear-gradient(135deg,#1e1b4b 0%,#4338ca 60%,#6d28d9 100%);
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
      {TODAY} &nbsp;&middot;&nbsp; Kuratiert von Gemini 2.5 Flash &nbsp;&middot;&nbsp; Täglich 04:00 Uhr
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

      <!-- AUF EINEN BLICK -->
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
      </td></tr>

      <!-- SEKTION 1: TOP NEWS -->
      {section_title(SEC['news'], 'Top News des Tages')}
      {news_rows}

      <!-- SEKTION 1B: SCHNELLDURCHLAUF -->
      {blitz_section}

      <!-- SEKTION 2: PODCAST -->
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
      </td></tr>

      <!-- SEKTION 3: PROMPT DES TAGES -->
      {section_title(SEC['prompt'], 'Prompt des Tages')}
      <tr><td style="padding:0 0 0;">
        <table width="100%" cellpadding="0" cellspacing="0"
               style="border-radius:12px;border:1px solid #a5f3fc;">
          <tr><td style="background:{SEC['prompt']['light']};border-radius:12px 12px 0 0;
                         padding:16px 18px 14px;">
            <div style="margin-bottom:10px;">{pdt_badge}</div>
            <h3 style="margin:0 0 14px;font-family:{FONT};font-size:16px;font-weight:700;
                       color:{C_TEXT};">{prompt_tages.get('titel','')}</h3>
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#0f172a;border-radius:8px;">
              <tr><td style="padding:10px 14px 6px;">
                <table cellpadding="0" cellspacing="0"><tr>
                  <td style="width:10px;height:10px;background:#ef4444;border-radius:50%;
                             font-size:0;line-height:0;">&thinsp;</td>
                  <td width="5">&thinsp;</td>
                  <td style="width:10px;height:10px;background:#fbbf24;border-radius:50%;
                             font-size:0;line-height:0;">&thinsp;</td>
                  <td width="5">&thinsp;</td>
                  <td style="width:10px;height:10px;background:#22c55e;border-radius:50%;
                             font-size:0;line-height:0;">&thinsp;</td>
                  <td style="padding-left:10px;">
                    <span style="font-family:{FONT};font-size:10px;color:#475569;
                                 letter-spacing:1px;text-transform:uppercase;">prompt</span>
                  </td>
                </tr></table>
              </td></tr>
              <tr><td style="padding:4px 16px 16px;">
                <p style="margin:0;font-family:'Courier New',Courier,monospace;font-size:13px;
                           color:#e2e8f0;line-height:1.7;">{prompt_tages.get('prompt','')}</p>
              </td></tr>
            </table>
          </td></tr>
          <tr><td style="background:{SEC['prompt']['light']};padding:10px 18px 16px;
                         border-top:1px solid #a5f3fc;border-radius:0 0 12px 12px;">
            <span style="font-family:{FONT};font-size:13px;color:#0e7490;line-height:1.6;">
              💡 {prompt_tages.get('tipp','')}
            </span>
          </td></tr>
        </table>
      </td></tr>

      <!-- SEKTION 4: TOOL DES TAGES -->
      {section_title(SEC['tool'], 'Tool des Tages')}
      <tr><td style="padding:0 0 0;">
        <table width="100%" cellpadding="0" cellspacing="0"
               style="background:{SEC['tool']['light']};border-radius:12px;
                      border:1px solid #a7f3d0;">
          <tr><td style="padding:18px 20px 0;">
            <table width="100%" cellpadding="0" cellspacing="0"><tr>
              <td>
                <a href="{tool_tipp.get('url','#')}"
                   style="font-family:{FONT};font-size:18px;font-weight:800;
                          color:{C_TEXT};text-decoration:none;">
                  {tool_tipp.get('name','')}
                </a>
              </td>
              <td style="text-align:right;vertical-align:top;">
                {tool_preis_badge}
              </td>
            </tr></table>
          </td></tr>
          <tr><td style="padding:8px 20px 10px;">
            {tool_kat_badge}
          </td></tr>
          <tr><td style="padding:0 20px 12px;">
            <span style="font-family:{FONT};font-size:14px;color:#374151;line-height:1.75;">
              {tool_tipp.get('beschreibung','')}
            </span>
          </td></tr>
          <tr><td style="padding:0 20px 14px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr><td style="background:#ffffff;border-left:4px solid {SEC['tool']['color']};
                             border-radius:0 8px 8px 0;padding:10px 14px;">
                <span style="font-family:{FONT};font-size:10px;font-weight:900;
                      color:{SEC['tool']['color']};letter-spacing:1.5px;text-transform:uppercase;">
                  TAKE&ensp;</span>
                <span style="font-family:{FONT};font-size:13px;color:#1e293b;line-height:1.65;">
                  {tool_tipp.get('take','')}</span>
              </td></tr>
            </table>
          </td></tr>
          <tr><td style="padding:10px 20px 16px;border-top:1px solid #a7f3d0;">
            <a href="{tool_tipp.get('url','#')}"
               style="font-family:{FONT};font-size:12px;font-weight:700;
                      color:{SEC['tool']['color']};text-decoration:none;">
              Tool ausprobieren &rarr;
            </a>
          </td></tr>
        </table>
      </td></tr>

      <!-- SEKTION 5: CLAUDE CODE TIPP -->
      {section_title(SEC['claude'], 'Claude Code im Projektalltag')}
      <tr><td style="padding:0 0 0;">
        <table width="100%" cellpadding="0" cellspacing="0"
               style="background:{SEC['claude']['light']};border-radius:12px;
                      border:1px solid #ddd6fe;">
          <tr><td style="padding:18px 20px;">
            <div style="margin-bottom:10px;">{anw_badge}</div>
            <h3 style="margin:0 0 10px;font-family:{FONT};font-size:16px;font-weight:700;
                       color:{C_TEXT};">{claude_tipp.get('titel','')}</h3>
            <p style="margin:0;font-family:{FONT};font-size:14px;
                      color:#374151;line-height:1.75;">{claude_tipp.get('beschreibung','')}</p>
          </td></tr>
        </table>
      </td></tr>

    </table>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="padding:28px 0 0;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="background:#f8fafc;border-radius:12px;padding:16px 20px;
                     border:1px solid #e2e8f0;text-align:center;">
        <p style="margin:0 0 6px;font-family:{FONT};font-size:14px;font-weight:700;color:{C_TEXT};">
          Gefällt dir der Newsletter? 📨
        </p>
        <p style="margin:0;font-family:{FONT};font-size:13px;color:#64748b;line-height:1.6;">
          Leite ihn einfach an Kollegen weiter, die KI-Entwicklungen im Blick behalten wollen.
        </p>
      </td></tr>
      <tr><td style="padding:18px 0 0;text-align:center;">
        <p style="margin:0 0 4px;font-family:{FONT};font-size:12px;color:#94a3b8;line-height:1.8;">
          🤖 Automatisch kuratiert von Gemini 2.5 Flash &middot; GitHub Actions
        </p>
        <p style="margin:0;font-family:{FONT};font-size:11px;color:#cbd5e1;">
          Täglich 04:00 Uhr &middot; 0&thinsp;€/Monat &middot; Ausgabe&thinsp;#{day_of_year}
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
        # Betreff: Top-Story als Aufhänger (AInauten/Finimize-Stil), Fallback generisch
        top_news = data.get("top_news", [])
        top_titel = top_news[0].get("titel", "").strip() if top_news else ""
        if top_titel:
            if len(top_titel) > 70:
                top_titel = top_titel[:67].rstrip() + "..."
            subject = f"🤖 {top_titel}"
        else:
            subject = f"🤖 KI-Newsletter {TODAY} – Top News, Podcast & KI-Tipps"
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
