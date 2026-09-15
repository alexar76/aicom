# Implementierungsleitfaden für Expert Memory Market

Dieser Leitfaden beschreibt die realen Production-Pfade für Käufer, Publisher
und Agent-Integratoren. Öffentliche Discovery, bezahlte Lieferung,
Publisher-Buchhaltung und Proof sind absichtlich getrennte Verträge.

## Zugriffspfad vor der Integration wählen

- Der 1-Tages-Trial prüft UX und API ohne Wallet-Transaktion.
- Expert Pass bietet sieben Tage Markterkundung mit begrenztem `ask_`-Schlüssel.
- Pay-per-read ordnet jede gelieferte Memory Unit ihrem Publisher und dessen Anteil zu.
- Pass und Publisher-Umsatz nicht vermischen: Der Pass finanziert den Markt, Meter Capture den Split.

## Listing vor dem Kauf prüfen

`GET /market/v1/listings?q=<thema>` braucht keinen Schlüssel. Jeder Eintrag zeigt
Zusammenfassung, `rank_score`, `rank_reasons`, Truth, Provenance, Preis und
Publisher. `GET /market/v1/listings/<memory_id>` gibt nie den bezahlten Inhalt aus.

Lehnen Sie Listings ohne ausreichende öffentliche Belege ab. Ein hoher Score
ist kein Vertrauensbefehl. Ein rejected Claim liegt unter einem unverified Claim;
Popularität ist kein Ranking-Signal.

## Mit dem kostenlosen Trial starten

Öffnen Sie `/` mit `trial=expert-market` oder den Assistenten. Der Browser
erstellt die Actor Identity und hält den privaten Signaturschlüssel lokal.
Gateway stellt einen Trial pro Actor und Produkt aus. `ask_` gehört in einen
Secret Vault, nie in URL, Logs oder Client Analytics.

Der Trial prüft den Product Fit, erzeugt aber keine Zahlung, keinen Split und
kein dauerhaftes Entitlement.

## Pass oder gelieferte Lektüre kaufen

Für Expert Pass öffnen Sie `/billing?plan=expert.pass.7d`, erstellen die exakte
Rechnung, senden canonical USDC auf Base und warten auf KOVA Finality. Gateway
stellt den Schlüssel sieben Tage aus; Checkout-Recovery gilt 48 Stunden.

Für Pay-per-read erstellen und laden Sie ein Attested-Meter-Konto, halten `amk_`
serverseitig und rufen `POST /market/v1/read` mit `x-meter-key` und
`{"memory_id":"<id>"}` auf. Meter reserviert den Preis und erfasst ihn erst
nach Lieferung; Fehler oder Ablehnung geben die Reservierung frei.

## Experten-Memory veröffentlichen und bepreisen

- Erstellen Sie eine Memory Unit mit präzisem Titel, nützlicher Zusammenfassung, Tags und `source_refs`.
- Ergänzen Sie vor der Bepreisung Truth- und Provenance-Belege.
- Registrieren Sie sich über `POST https://meter.attestedmemory.net/v1/publishers` mit signierter Identity und Base-Adresse.
- Halten Sie den Publisher Key privat und bepreisen Sie nur eigenes `expert.read:<memory_id>` über `/v1/publishers/me/prices`.
- Prüfen Sie das Listing öffentlich, bevor Sie Käufer dorthin senden.

Standard sind 70% Publisher / 30% Plattform; Publisher Pro ändert auf 85% / 15%.
Über dem Minimum erstellt der Operator eine signierte `attested.payout/v1` und
erfasst den Transaktionshash.

## Autonomen Agenten integrieren

- Discovery und Kauf trennen; Ausgaben erst nach Metadata-Prüfung erlauben.
- Maximalpreis, zulässige Publisher, Truth States und Quellenregeln festlegen.
- `ask_` und `amk_` in Server Secrets halten und aus Traces entfernen.
- `401` bedeutet Credential, `402` Zugriff/Guthaben, `403` Scope, `429` Backoff.
- Listing ID, Rank Reasons, Charge ID und Provenance Receipt mit dem Ergebnis speichern.
- Rechnungen idempotent erstellen; Überweisungen nie mit erfundenem Betrag wiederholen.

## Im Team einführen

- Eine erste Wissenskategorie und die verbesserte Entscheidung definieren.
- Vor Einladungen 10–20 starke Listings bereitstellen.
- Mindeststandard für öffentliche Zusammenfassung und Quellen vereinbaren.
- Erfolg, unbekannte Memory, zu wenig Guthaben, Upstream-Fehler und Widerruf testen.
- Discovery-to-read, Refusals, Capture/Release, Accrual und Payout-Backlog messen.

## Vertrauens- und Geldgrenzen beachten

Memory Market ordnet und liefert berechtigte Memory. Attested Meter verwaltet
Reserve, Capture, Publisher-Buchhaltung und Payouts. Attested Prove macht
Belege ohne API-Schlüssel prüfbar. KOVA prüft exaktes Settlement über
authentifiziertes Service-to-Service und bleibt föderiert verfügbar.

Kein Dienst fragt nach Seed Phrase oder Private Key. USDC geht direkt zum
Empfänger; Payouts werden separat ausgeführt. Siehe
[KOVA_CAPABILITIES.md](KOVA_CAPABILITIES.md) und [MARKET_USE_CASES.md](MARKET_USE_CASES.md).
