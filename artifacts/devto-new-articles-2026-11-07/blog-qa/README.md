# Blog visual QA

Ready: no required layout fixes.

Chromium rendered the four new pages at 1440×1100 in dark mode, and ARD plus HISTOR at 390×844 in light mode. All requests were fulfilled from local built pages, local images and locally mirrored production fonts; no external request or publication was made.

All four desktop screenshots and representative mobile title, code and table screenshots were visually inspected. No horizontal page overflow, missing images, missing local assets or JavaScript errors. ARD code scrolls within its block on mobile. HISTOR table fits its column; long reason codes wrap inside the cells.

qa.json contains measurements and the visual inspection summary. PNG files include top, full-page and mobile-detail captures. check_layout.py reproduces the local render. The first sandboxed Chromium launch was refused by the macOS process sandbox; the successful run used approved escalation. No browser settings or user sessions were changed.
