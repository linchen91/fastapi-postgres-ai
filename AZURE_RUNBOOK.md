# Azure Deployment Runbook

Live deployment on the **Free Trial** subscription `e3fba42e-66f5-48e3-8950-dd72016da2bf`
("Azure subscription 1", tenant `174cc61a-d946-4fe4-a087-64d9809e04ba`, owner `linchen91@hotmail.com`).

All secrets live outside the repo in `~/.config/fastapi-postgres-ai/azure.env` (`chmod 600`).
Source it before any command below:

```bash
set -a; . ~/.config/fastapi-postgres-ai/azure.env; set +a
export PATH=/tmp/opencode/azcli/bin:$PATH   # az CLI installed in a venv
```

## Live URL

| | |
|---|---|
| **App** | https://ca-fastapi-ai.jollywave-3dee1d3c.germanywestcentral.azurecontainerapps.io |
| **Swagger** | https://ca-fastapi-ai.jollywave-3dee1d3c.germanywestcentral.azurecontainerapps.io/docs |
| **Login** | `admin` / `admin123` (seeded on startup — change `ADMIN_PWD_HASH` in [main.py](main.py)) |

## Inventory

| Resource | Name | Region | SKU |
|---|---|---|---|
| Resource group | `rg-fastapi-postgres-ai` | germanywestcentral | — |
| Container Registry | `acrfastapiai001` | germanywestcentral | Basic |
| Container Apps env | `cae-fastapi-ai` | germanywestcentral | Consumption |
| Container App | `ca-fastapi-ai` | germanywestcentral | 0.5 vCPU / 1 Gi, 0–3 replicas |
| PostgreSQL flexible | `pg-fastapi-ai` | **switzerlandnorth** | Burstable `Standard_B1ms`, 32 GB, PG 16 |
| Log Analytics | `workspace-rgfastapipostgresaiznNg` | germanywestcentral | — |

Image: `acrfastapiai001.azurecr.io/fastapi-postgres-ai:adb5ce6-openapifix` (also tagged `latest`).

### Why PostgreSQL is in Switzerland North

Your subscription is a **Free Trial** (`quotaId: FreeTrial_2014-09-01`). Azure reports
`restricted: Enabled` for `Microsoft.DBforPostgreSQL` in every nearby region —
Germany West Central, West Europe, East US, Canada East, Switzerland West and others all fail with
`The location is restricted from performing this operation` (underlying ARM code: `BadGatewayConnection` /
`LocationIsOfferRestricted`). Scanning `/providers/Microsoft.DBforPostgreSQL/locations/<r>/capabilities`
for every region the subscription may use showed Switzerland North is unrestricted, so the database
lives there (~5 ms from Frankfurt). Everything else is in Germany West Central; the cross-region hop
is on Azure's backbone.

**Probe a region before trusting it:**

```bash
az rest --method get --url \
 "https://management.azure.com/subscriptions/$AZ_SUBSCRIPTION_ID/providers/Microsoft.DBforPostgreSQL/locations/<region>/capabilities?api-version=2024-08-01" \
 | python3 -c "import sys,json;v=json.load(sys.stdin)['value'][0];print(v['restricted'], v['reason'])"
```

## Configuration

The app reads **everything** from container environment variables — `.env` is in `.dockerignore`,
so it is never baked into the image. Injected on `ca-fastapi-ai`:

| Variable | Value |
|---|---|
| `POSTGRES_USER` | `postgres` |
| `POSTGRES_PASSWORD` | *see `PG_ADMIN_PASSWORD` in `azure.env`* |
| `POSTGRES_HOST` | `pg-fastapi-ai.postgres.database.azure.com` |
| `POSTGRES_PORT` | `5432` |
| `POSTGRES_DB` | `dzservice` |
| `SECRET_KEY`, `OPENROUTER_*`, `TAVILY_API_KEY` | from repo `.env` |
| `DB_ECHO` | `false` |

Postgres firewall rule `AllowAllAzureServicesAndResourcesWithinAzureIps_*` accepts Azure-internal IPs.
The server is otherwise **publicly reachable on 5432** with password auth — tighten before real traffic.

## Redeploy (code changes)

```bash
set -a; . ~/.config/fastapi-postgres-ai/azure.env; set +a
export PATH=/tmp/opencode/azcli/bin:$PATH
az acr login --name $ACR_NAME

IMG=$ACR_LOGIN_SERVER/fastapi-postgres-ai:$(git rev-parse --short HEAD)
docker build -t "$IMG" -t $ACR_LOGIN_SERVER/fastapi-postgres-ai:latest .
docker push "$IMG"
docker push $ACR_LOGIN_SERVER/fastapi-postgres-ai:latest

az containerapp update -g $AZ_RESOURCE_GROUP -n $CA_NAME --image "$IMG"
```

Changing env vars (no image change):

```bash
az containerapp env var set -g $AZ_RESOURCE_GROUP -n $CA_NAME \
  --image ...   # or use --set-vars KEY=VALUE pairs
```

Scaling (currently `min=0`, so the app cold-starts on the first request):

```bash
az containerapp update -g $AZ_RESOURCE_GROUP -n $CA_NAME \
  --min-replicas 1 --max-replicas 3   # keep it always warm (~+$15/mo)
```

Logs / status:

```bash
az containerapp logs show -g $AZ_RESOURCE_GROUP -n $CA_NAME --tail 100 --follow
az containerapp replica list -g $AZ_RESOURCE_GROUP -n $CA_NAME -o table
az postgres flexible-server show -g $AZ_RESOURCE_GROUP -n $PG_SERVER --query state -o tsv
```

## Verify

Run on demand after any deploy — both suites hit the live URL, both are intentionally **not** in
`bitbucket-pipelines.yml` (the app scales to zero and Azure pauses the Free Trial subscription when its
credit runs out, so a live check must not block a push).

```bash
./scripts/test-azure.sh              # HTTP smoke — 22 assertions
cd frontend && npm run test:azure    # browser e2e — 6 tests, no mocks
```

`test-azure.sh` waits out a cold start (10 attempts × 6 s by default), then checks the SPA, its bundle,
`config.json`, `/docs`, `redoc`, `openapi.json`, `/news` (with and without a trailing slash, and with
`?force=true`), an https redirect, a `401` on `/events`, a real admin login, and an authenticated read of
`/users/`. Each assertion targets one of the regressions in [Fixed](#fixed).

Page-like checks are sent with a **browser `Accept: text/html,…` header**. That matters: the SPA middleware
serves `index.html` for any GET accepting `text/html`, so probing `/docs` with curl's default `Accept: */*`
gets real Swagger UI even when a browser gets a blank page. Both the shell check and the
`swagger-ui-bundle` content check are needed to catch that.

`npm run test:azure` uses `frontend/playwright.azure.config.js` (no `webServer`, 90 s timeout) and logs in
for real, so `/home` and `/news` are actually rendered against production data.

Overrides: `AZURE_BASE_URL`, `AZURE_ADMIN_ACCOUNT`, `AZURE_ADMIN_PASSWORD`,
`AZURE_SMOKE_RETRIES`, `AZURE_SMOKE_RETRY_DELAY`, `AZURE_SMOKE_TIMEOUT`.

## Costs (estimate)

| Item | Approx. |
|---|---|
| PostgreSQL flexible `B1ms` + 32 GB (24/7) | ~€12–15 / month |
| Container Apps environment | ~€3 / month |
| Container App at `min-replicas=0` | ~€0 idle, ~€0.50/day when running |
| ACR Basic | ~€5 / month |
| Log Analytics (first 5 GB) | €0 |

Roughly **€20–25 / month** idle-scaled; ~€35–40 if kept warm at 1 replica.

> Your subscription has **`spendingLimit: On`** with a `$200` free credit (offer `freetier`,
> ends 2027-10-29). Azure **pauses the subscription** when the credit runs out — that stops billing
> but takes the whole deployment offline.

## Teardown

Everything lives in one resource group, so a single delete clears it (the PostgreSQL server in
Switzerland North is included):

```bash
az group delete -n rg-fastapi-postgres-ai --yes --no-wait
```

Partial cleanup:

```bash
az containerapp delete -g $AZ_RESOURCE_GROUP -n $CA_NAME --yes
az postgres flexible-server delete -g $AZ_RESOURCE_GROUP -n $PG_SERVER --yes
az acr delete -n $ACR_NAME --yes
```

## Known issues / follow-ups

1. **Default admin `admin123`** (seeded via `ADMIN_PWD_HASH` in [main.py](main.py)) and the Postgres
   password in a local file. Rotate both for anything beyond a demo.
2. **Postgres is publicly accessible on 5432.** Move it into a VNet with private endpoints, or at
   least restrict the firewall rule to the Container Apps outbound IPs.
3. **No Terraform/Helm coverage** for this path — `terraform/`, `helm/`, `k8s/` still target the
   generic-Kubernetes (minikube) deployment. Azure is provisioned via `az` CLI only.

### Fixed

- **`/news` "network error".** The frontend called `/news` while the route was registered as
  `/news/`, so Starlette 307-redirected to `http://…` (uvicorn saw plain HTTP behind the TLS
  terminator) and the browser blocked the HTTPS→HTTP downgrade as mixed content.
  [routers/news.py](routers/news.py) now registers both paths, so nothing redirects.
- **`openapi.json` returned `null` on the first request after every cold start.** `custom_openapi()`
  in [main.py](main.py) cached the schema but never returned it on the cache-miss path. Added
  `return openapi_schema`.
- **Slash-less redirects downgraded to `http://`.** The [Dockerfile](Dockerfile) now runs uvicorn with
  `--proxy-headers --forwarded-allow-ips=*` so `X-Forwarded-Proto` from Container Apps makes
  redirects absolute over `https://` (`/users`, `/devices`, `/roles` still redirect — to the right
  scheme now — because the frontend calls them with a trailing slash).
- **`/docs` rendered a blank page in a browser** (HTTP 200, no Swagger UI). `SPAMiddleware` in
  [main.py](main.py) fell back to `index.html` for *every* GET whose `Accept` contained `text/html` —
  `/docs` included — so the browser got the SPA shell, React Router matched no route, and the page stayed
  empty. `curl` with its default `Accept: */*` got real Swagger UI, which is why it went unnoticed.
  Doc routes (`/docs`, `/redoc`, `/openapi.json`) now return early to FastAPI before the fallback.
- **Two orphaned Log Analytics workspaces** left by interrupted environment creates were deleted;
  `workspace-rgfastapipostgresaiznNg` is the one `cae-fastapi-ai` is wired to.
