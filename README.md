# KI-Newsletter – Vollautomatisiert via GitHub Actions

Täglich um 07:00 Uhr (MESZ) ein frischer KI-Newsletter in deinem Postfach.
Komplett kostenlos, läuft in der Cloud – dein Laptop kann aus sein.

## Was das Projekt macht

Das Script ruft täglich die Gemini 2.5 Flash API auf, recherchiert mit Google Search
aktuelle KI-Nachrichten und schickt einen kuratierten HTML-Newsletter an deine
E-Mail-Adresse – vollautomatisch, ohne Server, ohne Kosten.

## Features

- **Gemini 2.5 Flash + Google Search Grounding** – findet wirklich aktuelle Inhalte (max. 3 Tage alt)
- **4 Sektionen**: Top News · Podcast-Empfehlung · Inspiration & Monetarisierung · Gemini Pro Tipp
- **Blacklist**: AInauten, TAAFT, Doppelgänger, AI Daily Brief – werden nie verwendet
- **Bevorzugte Quellen**: TechCrunch, The Verge, Ars Technica, Hacker News, Reddit, Hugging Face uvm.
- **Gmail SMTP-Versand** – zuverlässig, kein externer Dienst nötig
- **GitHub Actions Scheduler** – läuft täglich automatisch, ohne Server
- **Fehler-Mails** – bei Problemen bekommst du eine Diagnose-Mail

## Kosten

**0 €/Monat** – GitHub Actions (2.000 Freiminuten/Monat), Gemini API Free Tier
und Gmail SMTP sind alle kostenlos.

## Setup

Alle Einrichtungsschritte findest du in der **[SETUP.md](SETUP.md)**.
