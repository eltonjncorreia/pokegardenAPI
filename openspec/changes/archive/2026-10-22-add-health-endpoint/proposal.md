## Why

The service currently has no way to confirm it is up and able to answer requests. A health endpoint gives deploy pipelines, container orchestrators, and load balancers a cheap, dependency-free signal to gate traffic and restarts. We need it first so the rest of the API can be built and operated on a running baseline.

## What Changes

- Add a `GET /health` endpoint that returns HTTP `200` with a small JSON body (e.g. `{"status": "ok"}`) whenever the process is serving requests.
- Keep the implementation to the simplest FastAPI pattern: a single route handler wired directly on the app (or a minimal router), no service/repository layering, no external dependency checks.
- Wire the endpoint into the FastAPI app so it appears in the generated OpenAPI docs.

## Capabilities

### New Capabilities
- `service-health`: Exposes a liveness endpoint that reports whether the service is running and able to respond.

### Modified Capabilities
<!-- None. No existing specs in openspec/specs/. -->

## Impact

- **Code**: FastAPI app entrypoint (`app/main.py` or equivalent) gains the `/health` route; no new modules or layers required.
- **APIs**: New public `GET /health` route, documented in OpenAPI.
- **Dependencies**: None beyond the existing FastAPI stack.
- **Operations**: Enables liveness/readiness probes in deploy and container configs.
