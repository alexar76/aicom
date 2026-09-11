# KOVA-Capabilities in Attested

## Was KOVA ist

KOVA ist ein unabhängiger Base- und USDC-Dienst und läuft nicht im Attested Hub.
Sechs Produkte werden im Hub veröffentlicht und über die Föderation entdeckt,
bepreist und aufgerufen.

## Aufruf durch Agenten

Der Agent ruft den Hub über `POST /ai-market/v2/invoke` auf, nicht KOVAs private
Provider-URL. Der Hub prüft Zugriff und Abrechnung, protokolliert den Invoke und routet ihn.

Verfügbar sind `kova.network.status@v1`, `kova.asset.balance@v1`,
`kova.usdc.invoice.create@v1`, `kova.usdc.invoice.status@v1`,
`kova.usdc.invoice.cancel@v1` und `kova.usdc.webhook.register@v1`.

## Warum der Checkout anders läuft

Attested ruft KOVAs Invoice-API über eine authentifizierte service-to-service-Verbindung
auf. Eine bezahlte Capability prüft nicht die Zahlung für ihren eigenen Kauf. Das
verhindert rekursive Abrechnung und bindet einen Auftrag an ein Entitlement.

## Wer KOVA bezahlt

Bei einem Attested-Abo geht das USDC des Käufers direkt an
`SAAS_PAYMENT_RECIPIENT`. Diese Übertragung enthält keinen automatischen Split und
keinen KOVA-Prozentsatz. Das Gateway nutzt einen eigenen `KOVA_API_KEY`; stammt er
aus einem kostenpflichtigen KOVA-Pro- oder Business-Plan, kauft oder erneuert der
Betreiber ihn separat. Föderierte Capability-Aufrufe sind ein dritter, getrennt
gemessener Fluss: Preis pro Aufruf und Hub-Routing-Fee werden als Nutzung verbucht
und nie von einer Attested-Abozahlung abgezogen.

## Sichtbarkeit

Der Hub protokolliert Preis, Status und Receipt jedes föderierten Invoke. Das geschützte
Operator ledger zeigt Attested-Aufträge, Trial/Paid-Keys und Requests. KOVAs Settlement
desk zeigt eigene Aufträge, Key-Präfixe und Nutzung. Vollständige Keys werden nie gelistet.

## Sicherheitsgrenze

Der Provider verlangt `X-AIMarket-Internal-Token`, gleicht Route und Body ab und begrenzt
Schreiboperationen strenger. `X-Provider-Signature` bindet mit Ed25519 `product_id`,
`capability_id`, Input-Hash und Ergebnis und verhindert Replay für einen anderen Input.

## Sichere Einrichtung

`KOVA_CAPABILITY_TOKEN` muss zufällig, mindestens 32 Zeichen lang und gleich dem
`AIMARKET_CAPABILITY_TOKEN` des Hubs sein. `KOVA_HUB_URL` und `KOVA_INVOKE_BASE`
setzen und Provider-Endpunkte nur im privaten Servicenetz halten.
