# Kostenlose Testphase und Upgrade

Personal bietet 7 kostenlose Tage, Team 14 Tage und Expert Market 1 Tag. Eine
verifizierte Actor-Identität kann den Test pro Produkt einmal aktivieren.

Der Browser erstellt einen Ed25519-Actor-Nachweis. Das Gateway stellt ohne
Zahlung einen `ask_...`-Schlüssel aus. Der Schlüssel läuft automatisch ab und
verwendet dieselben Introspection-, Rotate- und Revoke-Regeln wie ein
bezahlter Schlüssel.

Beim Upgrade erstellt das Gateway eine exakte Rechnung in canonical USDC auf
Base. KOVA prüft die Transaktion; danach wird der bezahlte Schlüssel automatisch
ausgestellt.
