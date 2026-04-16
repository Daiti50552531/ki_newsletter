# Einrichtungsanleitung – KI-Newsletter

## Schritt 1: Gemini API-Key holen (kostenlos)

1. Öffne https://aistudio.google.com/app/apikey
2. Klicke auf „Create API key"
3. Wähle ein Google Cloud Projekt (oder erstelle ein neues)
4. Key kopieren und sicher notieren

## Schritt 2: Gmail App-Passwort erstellen

Voraussetzung: 2-Faktor-Authentifizierung muss aktiv sein.

1. Öffne https://myaccount.google.com/apppasswords
2. App-Name eingeben: KI Newsletter → „Erstellen"
3. Das 16-stellige Passwort kopieren – Leerzeichen weglassen

## Schritt 3: Die 4 GitHub Secrets setzen

1. Öffne https://github.com/daiti50552531/ki_newsletter
2. Tab „Settings" → „Secrets and variables" → „Actions"
3. „New repository secret" – diese 4 anlegen:

| Name | Wert |
|------|------|
| `GEMINI_API_KEY` | Dein Gemini API-Key |
| `GMAIL_ADDRESS` | z. B. dein.name@gmail.com |
| `GMAIL_APP_PASSWORD` | 16-stelliges App-Passwort (ohne Leerzeichen) |
| `RECIPIENT_EMAIL` | Ziel-E-Mail-Adresse |

## Schritt 4: Ersten Test-Run starten

1. Tab „Actions" → „Täglicher KI-Newsletter"
2. „Run workflow" → bestätigen
3. Nach ~60 Sek. grün = Postfach prüfen!

## Zeitplan

05:00 UTC = 07:00 MESZ (Sommer) / 06:00 MEZ (Winter)
