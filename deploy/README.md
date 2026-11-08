# deploy/

Everything needed to run SSUET RideShare on a single Linux VPS. The full walkthrough,
including the reasoning and the verification evidence, is
[`documentation/17-production-deployment.md`](../documentation/17-production-deployment.md).

| File | What it is |
| --- | --- |
| `env.production.example` | the complete production environment file — copy to `/etc/ssuet-rideshare/api.env` |
| `ssuet-api.service` | systemd unit: gunicorn + uvicorn workers, hardened (no new privileges, read-only filesystem except `MEDIA_ROOT`) |
| `nginx/ssuet-rideshare.conf` | one origin for the console, the API, uploads and the chat WebSocket; TLS, security headers, upload cap, edge rate limits |
| `backup.sh` | database **and** uploaded documents, with checksums, manifest and retention |
| `restore.sh` | restores a backup, refuses to run while the API is live |
| `smoke.sh` | post-deploy check: TLS, health, readiness, headers, SPA, API, login, upload cap |

Quick start (details in doc 17):

```bash
sudo adduser --system --group --home /srv/ssuet-rideshare ssuet
sudo mkdir -p /var/lib/ssuet-rideshare/media /etc/ssuet-rideshare
sudo -u ssuet git clone <repo> /srv/ssuet-rideshare
python3 -m venv /srv/ssuet-rideshare/backend/.venv
sudo -u ssuet /srv/ssuet-rideshare/backend/.venv/bin/pip install -r /srv/ssuet-rideshare/backend/requirements-prod.txt
sudo cp deploy/env.production.example /etc/ssuet-rideshare/api.env   # then edit
sudo cp deploy/ssuet-api.service /etc/systemd/system/ && sudo systemctl enable --now ssuet-api
sudo cp deploy/nginx/ssuet-rideshare.conf /etc/nginx/sites-available/ && sudo nginx -t && sudo systemctl reload nginx
./deploy/smoke.sh https://rideshare.ssuet.edu.pk
```
