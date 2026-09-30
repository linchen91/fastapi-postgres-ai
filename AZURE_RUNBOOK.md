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

Image: `acrfastapiai001.azurecr.io/fastapi-postgres-ai:69f2e12` (also tagged `latest`).

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

## CI/CD (Bitbucket Pipelines)

[bitbucket-pipelines.yml](bitbucket-pipelines.yml) runs the same deploy as
[Redeploy](#redeploy-code-changes), through the single entrypoint
[scripts/deploy-azure.sh](scripts/deploy-azure.sh) — identical commands locally and in CI.

| Trigger | Steps |
|---|---|
| any push / PR | terraform, helm, ansible, Playwright e2e — all offline, never touches Azure |
| push to `main` | the four test steps, then **build & push → deploy → verify** |
| Pipelines → Run pipeline → `deploy-azure` | build & push → deploy → verify only (redeploy, no code change) |

| Step | Image | Runs |
|---|---|---|
| Build & push image to ACR | `docker:27.5-cli` + `services: [docker]` | `./scripts/deploy-azure.sh build` |
| Deploy image to Container Apps | `mcr.microsoft.com/azure-cli:2.79.0` | `./scripts/deploy-azure.sh update` |
| Verify live deployment | `alpine:3.22` (`apk add curl`) | `./scripts/deploy-azure.sh verify` |

The image tag is the first 7 chars of `$BITBUCKET_COMMIT` (locally `git rev-parse --short HEAD`), plus
`latest`. The Docker service is set to `memory: 3072` — the 1024 MB default is too small for the
multi-stage build (`npm ci` + `pip install`), and 3072 is the maximum for a 1x step.

### Repository variables

Bitbucket → Repository settings → Variables. Mark the two secret ones as **secured** (they are masked in
build logs); everything else can stay plain.

| Variable | Secured | Value |
|---|---|---|
| `ACR_LOGIN_SERVER` | no | `acrfastapiai001.azurecr.io` |
| `ACR_USERNAME` | no | `az acr credential show --name acrfastapiai001 --query username -o tsv` |
| `ACR_PASSWORD` | **yes** | `az acr credential show --name acrfastapiai001 --query 'passwords[0].value' -o tsv` |
| `AZ_RESOURCE_GROUP` | no | `rg-fastapi-postgres-ai` |
| `CA_NAME` | no | `ca-fastapi-ai` |
| `AZURE_TENANT_ID` | no | `174cc61a-d946-4fe4-a087-64d9809e04ba` |
| `AZURE_CLIENT_ID` | no | service principal `appId` |
| `AZURE_CLIENT_SECRET` | **yes** | service principal `password` |
| `AZURE_SUBSCRIPTION_ID` | no | `e3fba42e-66f5-48e3-8950-dd72016da2bf` |

### Service principal

`az containerapp update` needs ARM access, so CI logs in as a service principal scoped to the resource
group (ACR push uses the admin credentials above):

```bash
az ad sp create-for-rbac --name sp-fastapi-postgres-ai-ci \
  --role contributor \
  --scopes /subscriptions/e3fba42e-66f5-48e3-8950-dd72016da2bf/resourceGroups/rg-fastapi-postgres-ai \
  --years 2
```

`appId` → `AZURE_CLIENT_ID`, `password` → `AZURE_CLIENT_SECRET`, `tenant` → `AZURE_TENANT_ID`. The
`password` is shown **once** — paste it into Bitbucket immediately and delete this line from your shell
history if you care. A local copy of all three lives in `~/.config/fastapi-postgres-ai/bitbucket-ci.env`
(`chmod 600`, gitignored by virtue of living outside the repo). Revoke with `az ad sp delete --id <appId>`;
secrets older than the `--years` window stop working silently (the deploy step then fails at `az login`).

Locally nothing changes: `./scripts/deploy-azure.sh` uses your own `az` login plus
`~/.config/fastapi-postgres-ai/azure.env`, and only falls back to the service principal when the three
`AZURE_*` variables are set (i.e. in CI).

### Secrets never reach the image

`.dockerignore` excludes `terraform/`, `helm/`, `k8s/` and `ansible/`: none is needed at runtime, and
`COPY . .` would otherwise bake their credentials into an image that then gets pushed to ACR. The real
values are in `terraform/terraform.tfvars`, `ansible/vars/vault.yml` and `k8s/secret.yml` (`secret_key`,
`postgres_password`, OpenRouter and Tavily keys); `.env` was already excluded. `terraform/terraform.tfstate`
ships in the old tags as well — its sensitive entries are stored as `"status": "unknown"`, so no usable
value leaks from that file, but a state file has no business inside a runtime image either. Keep all of it
excluded.

Images tagged before the exclusion — `adb5ce6`, `adb5ce6-newsfix`, `adb5ce6-openapifix`, `swaggerfix` —
contain the real `terraform/terraform.tfvars`, `ansible/vars/vault.yml` and `k8s/secret.yml` (confirmed by
unpacking `adb5ce6-openapifix`: `secret_key = 1064f…`, `openrouter_api_key = sk-or…`,
`tavily_api_key = AIzaS…`). `69f2e12` and later are clean — confirmed the same paths are absent from that
image. Remove the old tags and rotate the values:

```bash
az acr repository show-tags -n acrfastapiai001 --repository fastapi-postgres-ai -o tsv
az acr repository delete -n acrfastapiai001 --image fastapi-postgres-ai:adb5ce6-openapifix --yes
```

## Verify

Run on demand after any deploy — both suites hit the live URL. Neither runs in the `default`
(test-only) pipeline: the app scales to zero and Azure pauses the Free Trial subscription when its credit
runs out, so a live check must not block a plain push. The HTTP smoke suite does run automatically as the
last step of an Azure deploy (`main` push or the manual `deploy-azure` pipeline) with
`AZURE_SMOKE_RETRIES=20`; the browser suite stays manual.

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
