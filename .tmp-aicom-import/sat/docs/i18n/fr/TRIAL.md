# Essai gratuit et mise à niveau

Personal offre 7 jours gratuits, Team 14 jours et Expert Market 1 jour. Une
identité actor vérifiée peut activer l’essai une fois par produit.

Le navigateur crée une preuve actor Ed25519. Le Gateway émet une clé `ask_...`
sans paiement. La clé expire automatiquement et suit les mêmes règles
d’introspection, de rotation et de révocation qu’une clé payée.

Lors de la mise à niveau, le Gateway crée une facture exacte en USDC canonical
sur Base. KOVA vérifie la transaction et la nouvelle clé payée est émise
automatiquement après les confirmations requises.
