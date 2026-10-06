# Running fast-store with Docker

One `docker-compose.yaml` runs everything: Traefik (API gateway), Postgres,
RabbitMQ, all 4 backend services, the React frontend, and a full
observability stack (OTel Collector, Prometheus, Loki/Promtail, Jaeger,
Grafana, cAdvisor, node-exporter).

## 1. Run it

```bash
cp .env.example .env   # JWT_SECRET_KEY - a real one is pre-filled, fine for local dev
docker compose up -d --build
```

First build takes a while — 4 separate Python services, a Vite/React build,
and several third-party images to pull. Watch progress:

```bash
docker compose logs -f
```

Then open:

- **`http://localhost`** — the storefront (React frontend, routed through Traefik)
- **`http://localhost/docs`** — user-service's Swagger UI
- **`http://localhost:8080`** — Traefik's own dashboard (see what's routed where)
- **`http://localhost:3000`** — Grafana (`admin` / `admin`)
- **`http://localhost:9090`** — Prometheus
- **`http://localhost:16686`** — Jaeger

Log in with the seeded admin account: `admin@example.com` / `password123`.

## 2. How this project is wired

There's no custom gateway service — **Traefik is the API gateway**,
discovering routes from Docker labels on each service (see
`docker-compose.yaml`). The frontend and every backend service share the
same origin (port 80), so the React app calls relative paths like
`/products` and `/orders/` with no CORS configuration and no
build-time API URL needed at all.

| Path | Routed to |
|---|---|
| `/`, static assets | `frontend` |
| `/users`, `/login`, `/products`, `/docs`, `/openapi.json` | `user-service` |
| `/orders` | `order-service` |
| `/inventory` | `inventory-service` |

`product-service` is **not** reachable through Traefik — per this project's
own design, it only speaks gRPC internally. `user-service` proxies
`/products` and `/products/{id}` to it over gRPC so the frontend (and
anything else outside the Docker network) can reach it over plain HTTP.

**One shared Postgres database (`appdb`), four tables.** Each service still
only ever reads/writes its own table (`user`, `product`, `order`,
`inventory`) — this isn't a return to a shared-database anti-pattern so much
as a pragmatic simplification: it lets Grafana's "total users" / "total
products" panels use a single Postgres datasource instead of needing
cross-database queries (which Postgres doesn't support in one connection
anyway). See `docker/postgres/init/`.

## 3. Database tables + the admin login are created automatically

`docker/postgres/init/` is mounted into the Postgres container and runs
automatically — but only the **first time** it starts with an empty data
volume, in filename order:

1. **`01-schema.sql`** — creates the `user`, `product`, `order`, and
   `inventory` tables. (Every service also runs
   `SQLModel.metadata.create_all()` on its own startup — idempotent, so
   that's a no-op once this file has already created them.)
2. **`02-seed.sql`** — 3 sample products with matching inventory stock, and
   the admin login:

   ```
   email:    admin@example.com
   password: password123
   ```

   Stored as a bcrypt hash, not plaintext — generated the same way
   user-service hashes passwords (`passlib`'s `CryptContext(["bcrypt"])`),
   so it verifies correctly at login.

## 4. What was audited and fixed

This was a real audit, not a from-scratch build — most of the project
already worked. Here's what was actually broken:

### A dead debug endpoint

`user-service`'s `/users/{user_id}/purchases/{product_id}` had a leftover
`print("HOLA")` followed by an unconditional `raise HTTPException(403)` —
**the endpoint always failed**, before ever reaching the real authorization
check or the gRPC call to product-service. Removed the dead code.

### An unauthenticated `place_order` that trusted the client

`order-service`'s `POST /orders/` accepted `user_id` as a plain parameter
from the request — meaning **anyone could place an order "as" any other
user** just by passing a different id. Fixed by deriving `user_id` from the
verified JWT instead (`Depends(verify_token)`), the same pattern
user-service already used elsewhere.

### Two services had no real persistence at all

- `product-service` didn't have a database — `GetProduct` always returned
  the same hardcoded fake laptop regardless of the requested id, and there
  was no way to list products. Added a real Postgres-backed catalog and a
  new `ListProducts` gRPC method (the proto only had `GetProduct` before).
- `inventory-service` tracked stock in an **in-memory Python dict that reset
  on every restart**, seeded with exactly one product (id 99). Replaced
  with a Postgres-backed `inventory` table that tracks real stock per real
  product id.
- `order-service` published an event and returned "processing" but never
  stored the order anywhere — there was no way to list past orders. Added
  an `order` table and a `GET /orders/` endpoint scoped to the logged-in
  user.

### The JWT secret was duplicated as a literal in two files

`shared/jwt_utils.py` and `services/user-service/auth.py` each hardcoded
the identical string `"my_super_secret_jwt_key_for_microservices"`, with a
comment warning they "must match." They did, but only because no one had
edited one without the other yet. Both now read a `JWT_SECRET_KEY` env var
with that same string as a fallback default, so they can never drift.

### Traefik wasn't actually reachable for login, or for order/inventory at all

The original Traefik rule for `user-service` only matched `/users`,
`/docs`, and `/openapi.json` — but `/login` lives at the root path, not
under `/users`, so **the login endpoint was never reachable through the
gateway**, only by exposing user-service's port directly (which the
original compose file didn't even do). `order-service` and
`inventory-service` had no Traefik labels at all — only direct port
mappings. Fixed the routing rule and added labels for both.

### product-service's own Dockerfile didn't copy the `shared` package

Every service imports from a repo-level `shared/` directory. Three of the
four Dockerfiles copy the whole build context across stages
(`COPY --from=builder /app /app`), so `shared` comes along automatically.
product-service's Dockerfile instead copied specific subdirectories
selectively, and `shared` wasn't one of them — harmless before, since
product-service didn't import from `shared`, but it does now (for
telemetry setup below), so this would have failed at container startup.
Fixed the Dockerfile, and while in there, fixed `PYTHONPATH` on
order-service and inventory-service's Dockerfiles too, which had the same
gap once they started needing `shared` imports.

## 5. OpenTelemetry, observability, and the dashboard

All 4 services now share one telemetry setup (`shared/telemetry.py`),
auto-instrumenting FastAPI (and gRPC, for product-service and
user-service's client calls) for traces, metrics, and logs, all exported
via OTLP to a central OTel Collector. See **`observability/README.md`** for
the full pipeline, the dashboard's panels, the alerting setup, and — importantly —
a couple of things that couldn't be verified without actually running the
stack.

## 6. Validation

Maven Central has blocked every Java project I've worked on in this
environment, but **PyPI was reachable here**, so this got real validation,
not just a syntax check:

- `uv lock` regenerated cleanly against real PyPI for the whole workspace.
- Each of the 4 services was installed into its own isolated venv (matching
  how Docker actually builds them) and its dependencies resolved without
  conflicts.
- **product-service**: imported `main.py` for real, seeded a SQLite DB, and
  called `GetProduct`/`ListProducts` directly against real data — both
  returned correct results.
- **order-service**: verified the ownership-scoping fix directly — two
  different JWTs, two different users' orders, confirmed each user only
  sees their own.
- **inventory-service**: fed a real order event through `process_message()`
  against a real DB and confirmed stock decremented correctly, then fed a
  `product_id: 999` event through and confirmed the dead-letter path
  triggers as designed.
- **user-service**: imported cleanly with all routes present, including the
  fixed/new ones.
- The frontend was built for real — `npm run build` completes clean with
  zero TypeScript errors.

What I couldn't verify: an actual live gRPC call across two separate
processes (sandbox tooling here doesn't keep background processes alive
between tool calls, so that specific cross-process test kept getting killed
before it could run) — but both sides of that call were independently
verified working, and it's the same `grpc.insecure_channel(...)` pattern
the codebase already used successfully before these changes. Also
unverified: RabbitMQ connectivity, and the actual shape of OTel metric
names once real telemetry is flowing — see `observability/README.md` for
specifics on that second one.

## 7. Common operations

```bash
# Rebuild a single service after a code change
docker compose up -d --build order-service

# Tear everything down (keeps Postgres/Grafana/Prometheus/Loki data)
docker compose down

# Tear down AND wipe all data (re-runs docker/postgres/init/* next start)
docker compose down -v
```

## 8. Product images & the admin role (added after the initial build)

Products now have an `image_url` field, editable through the UI by admins.

**How to use it:** log in as `admin@example.com` / `password123`, and each
product card gets a pencil button next to "Order". Click it, paste an image
URL, save. The card updates immediately. Non-admin users never see the
button — and the server enforces it independently (see below), so hiding
the button is convenience, not the actual security boundary.

**The API**, if you'd rather use it directly:

```bash
# Log in and grab a token
TOKEN=$(curl -s -X POST http://localhost/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"password123"}' | jq -r .access_token)

# Update just the image - other fields are left untouched
curl -X PUT http://localhost/products/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"image_url":"https://example.com/laptop.jpg"}'
```

`PUT /products/{id}` accepts any subset of `name`, `price`, `description`,
`image_url`. Omitted fields are left alone — this is real partial-update
semantics via proto3 explicit presence (`optional` fields + `HasField()`),
not "empty string means clear it".

### The role system

Users now have a `role` column (`"user"` or `"admin"`, defaulting to
`"user"`). The role is embedded in the JWT at login, and
`shared/jwt_utils.py`'s `require_admin` dependency checks it on protected
routes. The seeded `admin@example.com` is created with `role='admin'`; every
other account is a regular user.

To promote someone to admin, do it in the database — there's deliberately no
API for it:

```bash
docker compose exec db psql -U postgres -d appdb \
  -c "UPDATE \"user\" SET role='admin' WHERE email='someone@example.com';"
```

They'll need to log out and back in to get a token carrying the new role.

### Two security bugs fixed while adding this

Both were pre-existing, and both became more dangerous the moment roles
existed:

- **`POST /users/` accepted the whole `User` model, including `role`.** That
  meant anyone could self-register as an admin by posting
  `{"role": "admin"}`. Registration now uses a separate `UserCreate` model
  that has no `role` field at all, and always creates users as `"user"`.
- **`GET /users/` returned raw `User` rows — including every user's bcrypt
  password hash.** Now constrained by `response_model=list[UserPublic]`.

### Validated

Verified against a real database and a real FastAPI test client, not just
type-checked:

- Partial updates genuinely leave other fields untouched, and `image_url`
  persists across unrelated edits to the same product.
- A non-admin token gets `403` from `PUT /products/{id}`; a request with no
  token at all gets `401`; an admin token succeeds.
- A token with no `role` claim is rejected (fails closed, rather than
  defaulting to allowing).
- Registering with `{"role":"admin"}` produces a user with `role: "user"`.
- `GET /users/` responses contain no `password` field.

Frontend `npm run build` also passes clean with no TypeScript errors.

## 9. Creating products (cross-service write)

Admins can now create products from the UI — a "New product" button above
the grid opens a form (name, price, description, image URL with live
preview, initial stock).

### Why this is more than a normal POST

Creating a product touches **two services that own separate tables**:
product-service (the catalog, over gRPC) and inventory-service (stock
levels, over HTTP). A product with no inventory row would show up in the UI
as permanently un-orderable, so both writes need to land — but there's no
distributed transaction available across a gRPC service and an HTTP service
writing different tables.

So `POST /products` uses a **compensating action** instead:

1. Create the product via product-service's `CreateProduct` RPC.
2. Set initial stock via `PUT /inventory/{id}` on inventory-service.
3. If step 2 fails, delete the product again (`DeleteProduct` RPC) so
   nothing is left stranded, and return `502` saying it's safe to retry.
4. If the rollback *also* fails, return `500` naming the specific product id
   that now needs manual cleanup — rather than silently pretending the
   system is consistent.

That third and fourth case are the reason `DeleteProduct` exists on the
proto at all.

```bash
TOKEN=$(curl -s -X POST http://localhost/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"password123"}' | jq -r .access_token)

curl -X POST http://localhost/products \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Desk Mat","price":29.99,"description":"Large felt mat","image_url":"https://example.com/mat.jpg","initial_stock":50}'
```

### Editing

`PUT /products/{id}` already supported editing every field (name, price,
description, image_url) — but the UI still only exposes the image-URL
editor via the pencil button. Editing name/price/description currently has
to go through the API. Worth knowing if you expected a full edit form.

### Validated

Tested against real databases and FastAPI's test client, with the two
cross-service failure modes simulated explicitly:

- Happy path: returns `201`, and inventory-service really is called with the
  right stock value.
- Inventory write fails → product is rolled back (`DeleteProduct` called
  with the correct id), caller gets `502`.
- Inventory write fails *and* rollback fails → caller gets `500` whose
  message names the orphaned product id.
- Non-admin gets `403`; unauthenticated gets `401`.
- Negative price, negative stock, and blank name are all rejected with
  `400`.
- product-service: create works; delete actually removes the row; deleting
  a nonexistent id returns `deleted=False` instead of crashing.
- inventory-service: `PUT` inserts when absent and updates when present;
  negative stock rejected; delete is a safe no-op when the row is missing.

## 10. Known limitations (updated)

- **inventory-service's write endpoints are not admin-guarded.**
  `PUT /inventory/{id}` and `DELETE /inventory/{id}` are reachable through
  Traefik by any caller, authenticated or not. They exist so user-service
  can perform the second half of a product creation, and user-service *is*
  admin-guarded — but nothing stops someone calling inventory-service
  directly and rewriting stock levels. Fixing this properly means either
  putting these endpoints behind the same `require_admin` dependency (they
  currently carry no JWT because the call originates server-side), or
  service-to-service auth, or simply not routing `/inventory` writes
  through Traefik at all. Worth closing before any real deployment.
- Everything previously listed in §8 and observability/README.md still
  applies.

## 11. Full product edit, delete, and admin-only write enforcement

The pencil button now opens a full edit form — name, price, description,
and image URL, with a live image preview — not just the image field. A
trash icon next to it deletes the product after a two-click confirmation.

### Every write endpoint that manages the catalog is now admin-only

Specifically: `POST /products`, `PUT /products/{id}`, `DELETE
/products/{id}` (user-service), and `PUT /inventory/{id}`, `DELETE
/inventory/{id}` (inventory-service) — all guarded by `require_admin`.

**Two endpoints deliberately stayed public**, and I want to be upfront that
"all PUT/DELETE/CREATE should be admin-only" doesn't literally cover these,
because it can't without breaking the app:

- `POST /users/` — registration. If this were admin-only, nobody could ever
  create the first account, including the admin.
- `POST /orders/` — placing an order is a normal user's own action, scoped
  to *their* JWT (`verify_token`, not `require_admin`) since the earlier
  security fix in §4. Making this admin-only would mean regular users could
  never buy anything.

If you actually want `POST /orders/` restricted somehow (e.g. certain users
blocked from ordering), that's a different, narrower feature than "make it
admin-only" — happy to build it if that's what you meant.

### The part that made this non-trivial: locking down inventory-service broke user-service

`inventory-service`'s write endpoints were the flagged gap from §10 — reachable
by anyone, no guard at all. Adding `require_admin` there directly is the
obvious fix, but user-service calls `PUT /inventory/{id}` **internally**
during product creation (see §9), and that internal call was carrying no
JWT of its own. Naively guarding inventory-service would have made every
product creation fail with a 401, silently.

The fix: user-service now **forwards the calling admin's own bearer token**
on to inventory-service for both the create and delete flows — the same
token that got the request past `require_admin` on user-service is what
authorizes the write on inventory-service's side. There's no separate
service-to-service credential; it's the same JWT, same shared secret,
reused end to end. This also closes the gap for good: inventory-service no
longer trusts *any* caller, including user-service itself, without a valid
admin token attached.

### Validated

- inventory-service: no token → `401`; a valid non-admin token → `403`; a
  valid admin token → succeeds. Checked on both `PUT` and `DELETE`.
- user-service → inventory-service token forwarding: captured the actual
  outgoing request in a test and confirmed the `Authorization` header
  matches the admin's own token exactly, on both create and delete.
- Delete: happy path removes both rows; a non-admin token is rejected
  before either service is touched; deleting a nonexistent product returns
  `404`.
- Registration (`POST /users/`) and order placement (`POST /orders/`)
  confirmed still working for non-admin users — i.e., confirmed the
  deliberate exceptions above didn't get accidentally locked down too.

A caught-and-fixed bug along the way: `Security` is exported from
`fastapi` itself, not `fastapi.security` (only the credential types like
`HTTPAuthorizationCredentials` live there) — got this wrong on the first
pass, and the very act of running the token-forwarding test against a real
`TestClient` caught it immediately as an `ImportError` before it could ship.
