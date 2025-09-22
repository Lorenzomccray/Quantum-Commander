# Quantum Commander: Premium-ready deployment notes

This folder contains templates and scripts to help you scale the app.

What’s included
- nginx.conf — Reverse proxy for TLS, WS, and SSE. Replace {{YOUR_DOMAIN}} and install via deploy/render_nginx.sh.
- caddy.template.json — Alternative Caddy setup for automatic TLS. Replace {{YOUR_DOMAIN}}.
- scripts/setup_gunicorn_service.sh — Create a systemd user service using gunicorn + uvicorn workers.
- scripts/migrate_to_supabase.py — Move local JSON data (bots, chats, kb, skills) into Supabase.

Steps (quick start)
1) App server via gunicorn
   - Ensure venv: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
   - Start service: ./scripts/setup_gunicorn_service.sh 8000
   - Check: systemctl --user status quantum-commander-gunicorn.service --no-pager -l

2) Reverse proxy (Nginx)
   - sudo ./deploy/render_nginx.sh your.domain.tld
   - Make sure Let’s Encrypt certs exist (or run certbot separately).

3) Supabase migration
   - Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env
   - python scripts/migrate_to_supabase.py --dry-run
   - If tables missing, copy the SQL printed into Supabase SQL editor, run it, then rerun without --dry-run.

4) Health/readiness
   - curl -s https://your.domain.tld/ready | jq .
   - curl -s https://your.domain.tld/health | jq .

Notes
- WebSocket requires sticky sessions in multi-instance setups. For single host this config is enough.
- SSE buffering must be disabled in the proxy (already done in nginx.conf).
- Keep /home/USER/quantum-commander/.env out of version control.
