"""hunt_root_link.py NGINX_FILE — give hunt.modelmarket.dev's front page the ARD Link, nothing else.

Adds an exact `location = /` that proxies to the game like `location /` and repeats the server-level security
headers (an add_header in a location drops the inherited ones), plus Link rel="ard". Refuses to run twice.
"""
import sys

path = sys.argv[1]
text = open(path, encoding="utf-8").read()
anchor = "    location / {\n        # Crawler-visible text inside"
if text.count(anchor) != 1:
    sys.exit(f"anchor found {text.count(anchor)} times — stop")
if "location = / {" in text:
    sys.exit("an exact root location already exists — stop")
block = """    # The game's front page with the ARD link relation (draft-jimenez-dawn-ard-initial-contact-00 4.3.2): a client
    # that knows only this origin sends HEAD / and reads Link. Exact match, so every other game path is unchanged;
    # an add_header here drops the server-level ones, so they are repeated.
    location = / {
        include /etc/nginx/snippets/spa-text/hunt.modelmarket.dev.conf;
        proxy_pass http://signal_hunt_game;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 120s;
        add_header Strict-Transport-Security "max-age=31536000" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        add_header Link '<https://hunt.modelmarket.dev/.well-known/ard.json>; rel="ard"' always;
    }
"""
open(path, "w", encoding="utf-8").write(text.replace(anchor, block + anchor))
print("inserted")
