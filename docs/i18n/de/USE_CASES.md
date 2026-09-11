# Anwendungsfälle

Attested Memory ist für Situationen, in denen **Vergessen teuer** ist und
**blindes Vertrauen noch teurer**. Diese Szenarien zeigen, wann Notiz, Chat-Log
oder Vector Store nicht reichen — und wann Identität, truth state, provenance
und exakter Settlement Kontext in etwas Verwertbares verwandeln.

Routennamen, Header und Zahlungsbegriffe bleiben sprachübergreifend exakt.
Lokalisiert wird nur der erklärende Text.

## Gründer-Zweitgehirn, das context rot überlebt

**Wer.** Ein Gründer, Researcher oder Operator, der täglich zwischen Tools,
Agents und Geräten springt.

**Problem.** Entscheidungen leben in Chats, Notion-Dumps und halbfertigen
Prompts. Sechs Wochen später kann niemand sagen, *warum* eine Wahl getroffen
wurde, welchen Quellen man traute oder welcher Agent eine bequeme Zusammenfassung
erfunden hat.

**So funktioniert es.**

1. Schreibe eine Memory Unit mit Entscheidung, Begründung, Tags und
   `source_refs`.
2. Signiere als Actor (`X-Actor-ID` / public key / signature). Der Private Key
   bleibt im Client.
3. Später suche über `/memory/api/search` und prüfe truth + provenance, bevor
   du die Memory in einem neuen Plan oder Agent-Lauf wiederverwendest.

**Warum attestation zählt.** Du holst nicht „einen ähnlichen Absatz“. Du
holst eine portable Behauptung mit Actor und Lineage.

**Start.** [Personal Memory](/memory) · [Benutzerhandbuch](USER_GUIDE.md) ·
Trial unter [/billing](/billing).

## Incident-War-Room, der die Entscheidungsspur hält

**Wer.** On-call Engineers, SREs, Security Responders.

**Problem.** Der Outage-Channel läuft der Wiki davon. Der Postmortem entsteht
aus dem Gedächtnis, die Ownership jeder Entscheidung ist unscharf, und nächste
Woche wiederholt ein Agent eine abgelehnte Mitigation, weil nichts in einen
gemeinsamen Namespace signiert wurde.

**So funktioniert es.**

1. Öffne einen Team-Memory-OS-Workspace und lege einen Team-Namespace an.
2. Mitglieder schreiben Incident-Notizen, abgelehnte Optionen und finale
   Aktionen mit Actor-Signaturen.
3. Das SaaS Gateway prüft Membership; der Hub akzeptiert nur passende
   `team:<id>`-Records. Queries laufen nicht in ein anderes Team über.

**Warum attestation zählt.** Handoffs werden auditierbar. Offboarding widerruft
den Key; kurzlebige Team Assertions laufen ab — ohne forensische Chat-Jagd.

**Start.** [Team Memory OS](/teams) · [Benutzerhandbuch § Team](USER_GUIDE.md).

## Expertenwissen verkaufen, ohne das Corpus durchsickern zu lassen

**Wer.** Domain Experts, Research Shops, Advisory Boutiques.

**Problem.** Das volle Corpus gratis zu veröffentlichen zerstört das Geschäft.
Nur einen Teaser zu zeigen zerstört Vertrauen. Käufer brauchen Provenance vor
der Zahlung — Verkäufer brauchen zeitlich begrenzten Zugang, keine ewigen
Kopien als Default.

**So funktioniert es.**

1. Veröffentliche eine Memory Unit mit öffentlichen Summary-Feldern und
   bezahlter Visibility für den Body.
2. Käufer durchsuchen den Katalog, prüfen truth/provenance und öffnen eine
   exakte Base-USDC-Invoice.
3. KOVA verifiziert den Transfer; das Gateway stellt ein scoped Entitlement
   aus. Zugang endet mit dem Plan.

**Warum attestation zählt.** Discovery ist ehrlich. Settlement ist exakt.
Entitlement ist kryptografischer Product Scope — kein PDF-Link auf
Ehrenwort.

**Start.** [Expert Memory Market](/market) · [Zahlungen](/billing).

## Multi-Agent-Handoff mit kryptografischer Kontinuität

**Wer.** Agent Operators, Orchestration-Teams, autonome Workflows.

**Problem.** Agent A kippt eine Chat-Summary an Agent B. Die Summary ist
unsigniert, teilweise halluziniert und ohne Quellen. Ausfälle wirken wie
„das nächste Modell war dumm“, obwohl der echte Bug der stille Verlust von
Provenance war.

**So funktioniert es.**

1. Agent A schreibt eine signierte Handoff-Memory-Unit: Constraints, genutzte
   Tools, Quellen, offene Risiken.
2. Agent B holt sie mit derselben Actor/Team-Policy und verifiziert Provenance
   vor dem Weiterarbeiten.
3. Truth State reist mit der Unit — Widersprüche bleiben sichtbar, statt in
   selbstsichere Prosa geglättet zu werden.

**Warum attestation zählt.** Kontinuität ist Eigenschaft des Records, nicht
dessen, wer den Tab offen gelassen hat.

**Start.** [Developers](/developers) ·
[Benutzerhandbuch § Actor identity](USER_GUIDE.md).

## Due Diligence und Research mit quellengebundenen Claims

**Wer.** Analysten, Counsel, Investment- und Vendor-Review-Teams.

**Problem.** Diligence-Notizen zitieren „das Deck“, „den Call“ und „etwas aus
Slack“. Wird ein Claim angefochten, ist die Custody Chain ein Gefühl.

**So funktioniert es.**

1. Halte jeden materiellen Claim als Memory Unit mit expliziten `source_refs`
   fest.
2. Hänge Truth State an oder aktualisiere ihn, sobald Evidence kommt
   (confirmed, disputed, insufficient).
3. Rekonstruiere die Akte später aus Provenance Receipts statt aus
   rekonstruiertem Folklore.

**Warum attestation zählt.** Reviewer streiten über Claim und Evidence — nicht
darüber, wessen Notizen „aktueller“ waren.

**Start.** Personal- oder Team-Produkt · [Glossar](GLOSSARY.md).

## Automatisierter Paid Access, wenn der Browser weg ist

**Wer.** Käufer, die aus einer Wallet-App zahlen, Scripts die Invoices
settlen, und Operatoren, die keinen Checkout-Tab babysitten können.

**Problem.** Klassischer Checkout stirbt mit dem Tab. Manuelle „füg den tx
hash ein“-Flows erzeugen Support-Tickets und mehrdeutige Teilzahlungen.

**So funktioniert es.**

1. `POST /v1/billing/orders` mit eindeutigem `Idempotency-Key`, Plan und
   Payer.
2. Sende den exakten kanonischen USDC-Betrag auf Base an den Invoice-
   Empfänger.
3. KOVA matched Token, Payer, Recipient, Amount und Confirmation Depth.
4. Das Gateway aktiviert den Product Key automatisch. Polling von
   `GET /v1/billing/orders/{id}` mit Checkout Token liefert den Key bei
   confirmed — auch wenn die ursprüngliche Browser-Session weg ist.

**Warum attestation zählt.** Geldfluss und Entitlement-Ausgabe sind an die
exakte Invoice-Identität gebunden, nicht an einen Wallet-Screenshot.

**Start.** [Billing](/billing) · [Benutzerhandbuch § Buy access](USER_GUIDE.md).

## Sicheres Offboarding ohne verwaiste Institutionskenntnis

**Wer.** Team Leads, Security, IT.

**Problem.** Ein ausscheidender Operator hat noch Chat-Exports und persönliche
Notizen mit den echten Runbooks. Slack zu widerrufen widerruft keine
institutionelle Memory, die nie in einem kontrollierten System lebte.

**So funktioniert es.**

1. Halte operatives Wissen in Team Memory OS unter einem expliziten Namespace.
2. Rotiere oder widerrufe den SaaS-Key sofort beim Ausscheiden.
3. Team Assertions laufen in Minuten ab; Hub-Policy verlangt weiterhin Actor
   Proofs für geschützte Reads und Writes.

**Warum attestation zählt.** Zugang endet als Control-Plane-Ereignis — nicht
als Hoffnung, dass jemand einen Drive-Ordner gelöscht hat.

**Start.** [Team Memory OS](/teams).

## Wofür das nicht gedacht ist

- Ein allgemeines Chat-Archiv ohne Identitäts- oder Quellen-Disziplin.
- Ein Ort für Wallet Private Keys, Seed Phrases oder Roh-Credentials.
- Unscoped „mit der Welt teilen“-Dumps ohne Visibility Policy.
- Gerundete oder ungefähre Crypto-Zahlungen — der exakte USDC-Betrag *ist*
  die Invoice.

Wenn dein Workflow stillen Verlust von Authorship, Quellen und Payment-
Finality aushält, reicht ein Notizbuch. Wenn nicht, starte mit der passenden
Product Surface oben und halte die Hub-Verträge exakt.
