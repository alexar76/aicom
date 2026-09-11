# Benutzerhandbuch

## Zahlung und Schlüssel

Unter `/billing` Personal, Team oder Market wählen. Die Rechnung enthält Betrag,
Empfänger, Token, Chain und Ablaufzeit. Den exakten Betrag auf Base senden,
Bestätigungen abwarten und den tx hash einfügen. Der bezahlte `ask_...`-Schlüssel
kann mit dem Checkout-Geheimnis 48 Stunden lang wiederhergestellt werden; danach
bleibt nur sein Hash. Das Gateway gleicht Zahlungen auch bei geschlossenem Browser
automatisch ab. Verwende `GET /v1/keys/me`, `POST /v1/keys/rotate` und
`POST /v1/keys/revoke` für den Schlüssel-Lebenszyklus.

## Identität und Speicher

Bei Produkt-Requests den aktiven bezahlten Schlüssel als `X-SaaS-Key` senden;
er ist getrennt vom Actor-Nachweis.

Geschützte Requests benötigen `X-Actor-ID`, `X-Actor-Public-Key` und
`X-Actor-Signature`. Der private Schlüssel bleibt im Client. Schreiben erfolgt
über `/memory/api/memories`, Suche über `/memory/api/search`.

## Teams

Team über `/teams/api/teams` anlegen, Mitglieder über
`/teams/api/teams/{team_id}/members` verwalten und bei jeder Anfrage `team_id`
mitsenden. Gateway prüft die Mitgliedschaft, Hub Assertion und Actor-Signatur.

`401` bedeutet ungültige Credentials, `403` falschen Scope, `402` Zahlung nötig,
`429` Rate Limit. Niemals private Schlüssel senden.

## Trial

Trial über `/v1/trials` starten: Personal läuft 7 Tage, Team 14 Tage und Expert
Market 1 Tag. Das Gateway stellt ohne Zahlung einen Actor-gebundenen `ask_...`-Schlüssel
aus; derselbe signierte Actor kann ihn während der Laufzeit wiederherstellen. Danach verfällt der
Zugriff automatisch; für die Fortsetzung die exakte USDC-Zahlung auf Base senden.
Details: [TRIAL.md](TRIAL.md).

## KOVA-Capabilities und Checkout

Agenten entdecken KOVA über die Hub-Föderation; der Attested-Checkout nutzt einen
getrennten authentifizierten service-to-service-Pfad. Beide Wege und ihre
Sicherheitsgrenzen stehen in [KOVA_CAPABILITIES.md](KOVA_CAPABILITIES.md).
