# Entwickler-Praxishandbuch

## Integrationspfad wählen

Nutzen Sie SaaS-APIs für Personen, Teams oder Anwendungen mit einem `ask_`-Schlüssel. Nutzen Sie Hub-Föderation, wenn ein autonomer Agent bepreiste Capabilities entdecken und aufrufen soll. Beide Pfade haben getrennte Credentials und Abrechnung.

- Personal: `/memory/api/*` mit Personal-Scope.
- Team: `/teams/api/*` mit Team-Schlüssel und gültiger Mitgliedschaft.
- Expert Market: öffentliches Discovery unter `/market/v1/listings`, `ask_`-Zugang oder gemessene `amk_`-Reads.
- Föderation: `https://hub.attestedmemory.net/ai-market/v2/manifest` und Aufruf über den Hub.

## Signierten Actor erstellen

Erzeugen Sie Ed25519 in der Client-Runtime. Die Actor-ID ist `did:actor:` plus SHA-256-Hexdigest des rohen 32-Byte Public Keys. Signieren Sie exakt diese ID. Senden Sie `X-SaaS-Key`, `X-Actor-ID`, `X-Actor-Public-Key` und `X-Actor-Signature` als base64url ohne Padding.

Private Key, Seed Phrase und Checkout Token gehören nie in eine Produkt-API.

## Erste Anfrage sicher senden

Aktivieren Sie vor der Zahlungsintegration einen Trial. Er erzeugt keine Wallet-Transaktion und läuft automatisch ab. Schreiben Sie eine private Memory Unit, speichern Sie die ID und lesen Sie sie als derselbe Actor.

`401` bedeutet ungültige Credentials/Proof, `402` Zahlung nötig, `403` falscher Scope, `409` Zustands-/Idempotenzschutz, `429` erfordert `Retry-After`. Reads mit begrenztem Backoff wiederholen, Writes nur mit eigener Idempotenz.

## Capability veröffentlichen

Stellen Sie `/.well-known/ai-market.json`, ein signiertes `/ai-market/v2/manifest` und eine HTTPS Invoke-URL bereit. Deklarieren Sie `product_id`, versionierte `capability_id`, JSON Schema, Preis, Publisher und Public Key.

Registrieren Sie über `POST https://hub.attestedmemory.net/ai-market/v2/supply/register` mit einem begrenzten, vom Betreiber ausgestellten Publisher Token. Nie öffentlich einbetten. Wiederholen Sie die Registrierung beim Start.

## Automatische Verteilung

Attested Provider veröffentlichen bereits zwölf Capabilities automatisch. Hub bietet signiertes Discovery, aktualisiert `ecosystem.nodes`, zählt Aufrufe und kündigt seine Identität bei konfigurierten Roots an.

Werbung ist keine Selbstfreigabe: Externe Betreiber prüfen und pinnen die Identität. Social Media, Verzeichnisse und Kampagnen bleiben ebenfalls kontrolliert.

## Produktions-Checkliste

- HTTPS nutzen und Provider-to-Hub Tokens geheim halten.
- Signing Identity pinnen und exponierte Tokens rotieren.
- Größe, Timeout, Rate Limit und SSRF-Grenzen validieren.
- Signierte Ergebnisse an Capability, Input Hash und Request ID binden.
- Ungültige Signatur, Duplikate, Timeout, Revoke und Replay testen.
- PostgreSQL sichern und Restore prüfen; kein SQLite in Produktion.

Weiter: [KOVA](KOVA_CAPABILITIES.md), [Guide](USER_GUIDE.md), [Use Cases](USE_CASES.md).
