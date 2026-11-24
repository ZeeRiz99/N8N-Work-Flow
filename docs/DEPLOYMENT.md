# Deploying Replyline

A runbook for one Linux server (Ubuntu 24.04 LTS or similar) with Docker. Everything runs in
`infra/compose.prod.yml`: PostgreSQL, n8n, the backend, the frontend and Caddy (automatic HTTPS).
Only Caddy is public. Verified locally with `TLS_MODE=internal` (see "Local rehearsal" below).

## 1. Choose a server

Minimum: 2 vCPU, 4 GB RAM, 40 GB disk (the stack uses about 1.5 GB of RAM at rest; image
builds need more briefly). Prices researched on 2026-11-24 from public comparisons; **confirm on
the provider's own pricing page before buying**, as prices change and some sources disagree.

| Provider | 4 GB plan, monthly | Notes |
|---|---|---|
| Hetzner Cloud (shared vCPU, e.g. CX23) | about €6 (≈ $6.5) excl. VAT ([findstack](https://findstack.com/resources/vps-price-tracker), [Better Stack review](https://betterstack.com/community/guides/web-servers/hetzner-cloud-review/)) | Best price for EU/US East; prices were adjusted in 2026, check the current tier |
| DigitalOcean (Basic droplet, 2 vCPU / 4 GB / 80 GB) | about $24 ([tech-insider comparison](https://tech-insider.org/hetzner-cloud-vs-digitalocean-vultr-linode-4gb-pricing-2026/)) | Simplest UI, many regions, managed extras |
| Contabo | not verified in this research | Very low prices for more RAM; check reliability reviews and current pricing |

Recommendation for a demo or a first client: a Hetzner 4 GB instance. Reliability and
maintenance are similar across the three for a single server; the work is the same runbook.

## 2. Domain and DNS

1. Use a domain you own (any registrar). Create an **A record** `app.example.com → <server IPv4>`
   (and AAAA for IPv6 if the server has one). Wait until `nslookup app.example.com` returns the IP.
2. Caddy requests the Let's Encrypt certificate on first start; ports 80 and 443 must be open.

## 3. Real email (only if you will send to real people)

Mailpit is for development only. Use an SMTP service (Brevo, Resend, Postmark, Amazon SES, …)
with a sending domain you control, and add the DNS records the service gives you:

- **SPF**: one TXT record on the sending domain, e.g. `v=spf1 include:<provider> ~all`
  (merge with any existing SPF record; only one is allowed).
- **DKIM**: the CNAME or TXT records from the provider.
- **DMARC**: TXT on `_dmarc.example.com`, start with `v=DMARC1; p=none; rua=mailto:you@example.com`,
  tighten to `quarantine` once reports look clean.

Every email Replyline sends needs a human approval and carries an opt-out line; you remain
responsible for consent and lawful basis where your leads live.

## 4. Prepare the server (once)

```bash
# as root on a fresh server
adduser deploy && usermod -aG sudo deploy
# copy your SSH key to deploy, then in /etc/ssh/sshd_config: PasswordAuthentication no, PermitRootLogin no
apt update && apt -y upgrade && apt -y install git curl python3 ufw unattended-upgrades
curl -fsSL https://get.docker.com | sh && usermod -aG docker deploy
ufw default deny incoming && ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable
```

Do **not** open 5678 (n8n) or 5432 (PostgreSQL); compose binds n8n to the server's localhost and
never publishes PostgreSQL. Note: Docker can bypass ufw for published ports; this stack publishes
only Caddy's 80/443 publicly.

## 5. First deploy

```bash
sudo mkdir -p /opt/replyline && sudo chown deploy /opt/replyline
git clone <your repository URL> /opt/replyline && cd /opt/replyline
cp .env.production.example .env.production && chmod 600 .env.production
nano .env.production        # fill every REPLACE_ME; generate secrets with:
                            # openssl rand -base64 48 | tr -d '/+=' | cut -c1-48
./scripts/deploy.sh
```

`deploy.sh` refuses to run while a `REPLACE_ME` is left, builds the images (tagged with the git
commit), starts the stack, waits for the backend (migrations run on start), registers the demo
organization and the n8n service key, imports the n8n credentials (output hidden) and all
workflows, activates them, and finally runs the checks below.

Create your login (password typed hidden):

```bash
docker compose -f infra/compose.prod.yml --env-file .env.production exec backend python -m app.cli set-demo-owner
```

Further team members join through **Settings → Team → Invite**.

## 6. Checks (the P11 gate)

`./scripts/deploy.sh --check` verifies:

- HTTPS serves the app;
- `/api/v1/internal/*` returns 404 from outside (n8n reaches the backend on the private network);
- the API docs are hidden;
- the backend answers through the proxy;
- n8n is bound to the server's 127.0.0.1 only (no public port);
- PostgreSQL is not published at all.

Then run the journey against production by hand (form → AI → alert → draft → approve →
email arrives), following `docs/DEMO_SCRIPT.md`. In the local rehearsal (2026-11-24) the
journey passed on the production stack: form 201 → AI done (high) → draft → approve → sent →
email in Mailpit, with W1 and W4b both successful. The built images contain no `.env` file
and no secret values (only variable names such as `PATH`, `NODE_ENV`).

## 7. n8n editor (private)

```bash
ssh -L 5678:127.0.0.1:5678 deploy@app.example.com
# then open http://localhost:5678 on your own computer; create the n8n owner account on first visit
```

## 8. Backups and restore

```bash
crontab -e
15 3 * * * /opt/replyline/scripts/backup-prod.sh >> /var/log/replyline-backup.log 2>&1
```

Dumps both databases nightly into `backups/` (14 days kept). Copy them off the server too
(provider snapshots, `rclone`, `restic`). **Back up `.env.production` separately and securely**:
without `N8N_ENCRYPTION_KEY` the n8n credentials cannot be decrypted after a restore.

Restore (tested by `scripts/restore-drill.ps1` locally; same commands on the server):

```bash
C="docker compose -f infra/compose.prod.yml --env-file .env.production"
$C stop backend n8n
$C exec -T postgres dropdb -U postgres --if-exists replyline
$C exec -T postgres createdb -U postgres -O replyline_app replyline
$C exec -T postgres pg_restore -U postgres -d replyline --no-owner --role=replyline_app < backups/replyline-<stamp>.dump
$C start backend n8n
```

## 9. Updates and rollback

```bash
cd /opt/replyline && git pull && ./scripts/deploy.sh      # new release, tagged with the commit
# rollback: check out the previous tag/commit and deploy again
git checkout v0.2.0 && ./scripts/deploy.sh
```

Database migrations only move forward; before an update with migrations, take a backup
(`scripts/backup-prod.sh`) so a rollback can restore it.

## 10. Monitoring

- **Errors:** W9 emails `ALERT_EMAIL_TO` when any workflow fails (throttled), W9b retries stalled
  deliveries every 10 minutes, and the Automation Center shows every run.
- **Uptime:** add a free external monitor (e.g. UptimeRobot, Better Stack) on
  `https://app.example.com/login` and on `/api/v1/public/forms/<slug>`.
- **Logs:** `docker compose -f infra/compose.prod.yml logs -f backend` (metadata only; no
  customer text).

## 11. Public demo instance

For a demo anyone may try: `ALLOW_REGISTRATION=true`, keep the rate limits, fictional data only,
`AI_PROVIDER=fake` or a dedicated low-quota key, and reset the data nightly:

```bash
0 4 * * * /opt/replyline/scripts/reset-demo.sh >> /var/log/replyline-demo.log 2>&1
```

## Local rehearsal (no server needed)

On the development machine, a `.env.production` with `DOMAIN=localhost`, `TLS_MODE=internal`,
`HTTP_PORT=8080`, `HTTPS_PORT=8443`, `AI_PROVIDER=fake` and `SMTP_HOST=host.docker.internal`,
`SMTP_PORT=1025` (Mailpit) runs the real production stack: `bash scripts/deploy.sh`. Stop the dev
n8n first (both use 5678). Tear down with
`docker compose -f infra/compose.prod.yml --env-file .env.production down -v`.
