# Deploying QEMS to AWS (free tier)

Single EC2 instance (nginx + the FastAPI backend as a systemd service) + one RDS Postgres
instance + one S3 bucket. No domain yet, so everything is reached over plain HTTP at the
EC2 instance's public IP — see "Adding a domain + HTTPS later" at the bottom for the
upgrade path once you have one.

Everything here is done through the AWS Console/CLI with **your** AWS account — I can't
do this part for you (no AWS credentials in this environment), but every step below is
concrete and copy-pasteable.

**Free tier math** (12 months from account creation): 1× `t3.micro` or `t2.micro` EC2
(750 hrs/month — one instance running 24/7 uses ~730 hrs, fits), 1× `db.t3.micro` RDS
(750 hrs/month, separate allowance from EC2's), 20GB RDS storage, 5GB S3, 15GB/month
outbound data transfer. Running exactly this (one EC2, one RDS, one small S3 bucket)
stays inside the free tier for normal QA-team-sized usage. Set a billing alarm anyway
(step 0) — it costs nothing and catches mistakes before they cost money.

---

## Step 0 — Billing alarm (do this first)

AWS Console → Billing → Budgets → Create budget → "Zero spend budget" (alerts you the
moment anything is charged). Takes two minutes and is the cheapest insurance you'll ever
buy.

---

## Step 1 — RDS Postgres

1. RDS Console → Create database → **Standard create** → Engine **PostgreSQL**, version
   **15.x or newer** (needed for `pgvector`, which this app uses for AI similarity search).
2. Templates → **Free tier**.
3. DB instance identifier: `qems-db`. Master username: `qems`. Set a strong password —
   save it, you'll need it in `.env`.
4. Instance class: `db.t3.micro` (free-tier eligible). Storage: 20 GiB gp2 (the free-tier
   max — don't enable storage autoscaling, it can push you past the free allowance).
5. Connectivity → **Don't** make it publicly accessible. VPC: default is fine. Under
   "VPC security group", create a new one: `qems-db-sg`.
6. Create the database (takes a few minutes).
7. Once it's up, note the **endpoint** (looks like `qems-db.xxxxxxxxxxxx.<region>.rds.amazonaws.com`).

## Step 2 — S3 bucket (evidence + message attachments)

1. S3 Console → Create bucket → name it something globally unique, e.g.
   `qems-evidence-<yourname>-<random>`. Region: same as your RDS/EC2.
2. Leave **Block all public access** ON (evidence is never served directly from the
   bucket — the app always mints short-lived presigned URLs, same as it already does
   against Supabase Storage locally).
3. IAM Console → Users → Create user `qems-app` → **Attach policies directly** → create
   an inline policy scoped to just this bucket (don't use a broad S3 policy):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
       "Resource": "arn:aws:s3:::qems-evidence-<yourname>-<random>/*"
     }]
   }
   ```
4. That user → Security credentials → Create access key → **Application running outside
   AWS** → save the Access Key ID and Secret Access Key.

## Step 3 — EC2 instance

1. EC2 Console → Launch instance. Name: `qems-app`.
2. AMI: **Ubuntu Server 22.04 LTS**.
3. Instance type: `t3.micro` (or `t2.micro` if `t3.micro` isn't in your free-tier list —
   check under EC2 → "Free tier eligible" filter).
4. Key pair: create a new one, download the `.pem`, `chmod 400` it locally.
5. Network settings → create a new security group `qems-app-sg`:
   - SSH (22) from **My IP** only (not 0.0.0.0/0 — don't leave SSH open to the world).
   - HTTP (80) from Anywhere (0.0.0.0/0).
6. Storage: default 8GB gp3 is fine.
7. Launch.
8. Back in **RDS** → the `qems-db-sg` security group → Inbound rules → Add rule:
   PostgreSQL (5432), source = `qems-app-sg` (the EC2 instance's security group, picked
   from the dropdown — not an IP). This is what lets the EC2 box reach the database while
   keeping RDS unreachable from the public internet.

## Step 4 — Connect and install dependencies

```bash
ssh -i your-key.pem ubuntu@<EC2-PUBLIC-IP>

sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv git nginx postgresql-client
```

## Step 5 — Get the code onto the box

If your work is pushed to GitHub:
```bash
git clone https://github.com/<you>/QEMS.git
```
Otherwise, from your **local machine**, upload it directly:
```bash
rsync -avz --exclude node_modules --exclude .venv --exclude dist \
  -e "ssh -i your-key.pem" /Users/somanadhk/Documents/QEMS/ ubuntu@<EC2-PUBLIC-IP>:~/QEMS/
```

## Step 6 — Backend

```bash
cd ~/QEMS/backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../deploy/.env.production.example .env
nano .env   # fill in every REPLACE_ME (RDS endpoint/password, JWT secret, OpenAI key,
            # S3 keys, Gmail OAuth values copied from your working local .env)
```

Generate a real JWT secret instead of typing one:
```bash
python3.11 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Enable pgvector on the fresh RDS database, then run migrations and seed it:
```bash
psql "$(grep DATABASE_URL .env | cut -d= -f2- | sed 's/+asyncpg//')" -c "CREATE EXTENSION IF NOT EXISTS vector;"
alembic upgrade head
python -m app.tasks.seed          # roles, SLA policies, departments, categories
python -m app.tasks.seed_users    # one demo user per role, password Password123!
```

Install the systemd service:
```bash
sudo cp ~/QEMS/deploy/qems-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now qems-backend
sudo systemctl status qems-backend     # should say "active (running)"
curl http://127.0.0.1:8000/health      # {"status":"ok"}
```

## Step 7 — Frontend (build locally, upload the static files)

Don't build on the EC2 box — Vite's build step is memory-hungry and a 1GB free-tier
instance can OOM partway through. Build on your own machine instead:

```bash
# on your local machine
cd frontend
VITE_API_URL=/api/v1 npm run build
rsync -avz -e "ssh -i your-key.pem" dist/ ubuntu@<EC2-PUBLIC-IP>:~/QEMS/frontend/dist/
```

`VITE_API_URL=/api/v1` (relative, not `http://localhost:8000/api/v1`) is what makes the
built app call the same origin nginx serves it from — no CORS to configure.

## Step 8 — nginx

```bash
sudo cp ~/QEMS/deploy/nginx.conf /etc/nginx/sites-available/qems
sudo ln -sf /etc/nginx/sites-available/qems /etc/nginx/sites-enabled/qems
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

## Step 9 — Test it

Visit `http://<EC2-PUBLIC-IP>` in a browser. Log in with `admin@qemscorp.dev` /
`Password123!` (change this password for real use — `python -m app.tasks.seed_users` is
a dev convenience, not meant to survive into a real deployment).

---

## Redeploying after a code change

```bash
# backend
ssh -i your-key.pem ubuntu@<EC2-PUBLIC-IP> \
  "cd ~/QEMS && git pull && cd backend && source .venv/bin/activate && pip install -r requirements.txt && alembic upgrade head && sudo systemctl restart qems-backend"

# frontend
cd frontend && VITE_API_URL=/api/v1 npm run build
rsync -avz -e "ssh -i your-key.pem" dist/ ubuntu@<EC2-PUBLIC-IP>:~/QEMS/frontend/dist/
```

## Adding a domain + HTTPS later

Once you have a domain: point an A record at the EC2 public IP (or use an Elastic IP
first, so the address doesn't change on instance stop/start — Elastic IP is free while
attached to a running instance, charged only if left unattached). Then:
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```
Certbot rewrites `nginx.conf` to redirect HTTP→HTTPS with a free, auto-renewing
Let's Encrypt certificate — no code change needed on either side.

## Known gaps in this deploy

- **No Mailpit in production** — harmless, since Gmail OAuth is the real provider once
  configured; SMTP is only the fallback and its failures are logged/retried, never fatal.
- **Single instance, no load balancer/autoscaling** — appropriate for this app's actual
  scale (a QA team, not public internet traffic); revisit if that changes.
- **APScheduler runs in-process** — if you ever run more than one backend instance behind
  a load balancer, the SLA/notification/Gmail-poll jobs would fire once per instance.
  Fine for the single-instance setup here; see `app/workers/scheduler.py`'s own docstring
  for the documented Celery/broker upgrade path if you scale out later.
