# External event ingestion

The supported connector is a generic authenticated webhook receiver. Vendor
webhooks such as Zendesk or Stripe need an adapter that first validates the
vendor's signature and normalizes its event. This route is not a Stripe signature
verifier or a Zendesk connector.

Set a token in the **server process environment**, then store its environment
variable name as `secret_ref`. Names match `[A-Z][A-Z0-9_]*`. Plaintext tokens are
not configuration values. Missing or blank environment values fail closed.

```json
{
  "name": "Helpdesk events",
  "type": "webhook",
  "secret_ref": "OPENCLASS_HELPDESK_TOKEN"
}
```

Create the configuration with `POST /api/v1/projects/{project}/integrations`.
The local management API remains unauthenticated and loopback-only; webhook token
authentication is scoped to ingestion, not a workspace authorization system.

```python
import os
from openclass_sdk import OpenClass

with OpenClass() as client:
    result = client.ingest_integration_webhook(
        "support",
        "<integration-id>",
        event_key="zendesk:ticket:829:revision:14",
        source="helpdesk-adapter",
        content="I cannot sign in after changing phones",
        metadata={"ticket_id": "829"},
        token=os.environ["OPENCLASS_HELPDESK_TOKEN"],
    )
```

Equivalent HTTP: `POST /api/v1/projects/{project}/integrations/{integration}/webhook`,
JSON body containing `event_key`, `content`, optional `source` and `metadata`.
Send either `X-OpenClass-Token` or `Authorization: Bearer ...`. Token comparisons
are constant-time; tokens must not appear in body content or metadata. Conflicting
authentication headers are rejected. Use TLS when an external adapter crosses a
network boundary.

| Outcome                                    | HTTP | Meaning                                                                         |
| ------------------------------------------ | ---- | ------------------------------------------------------------------------------- |
| `ingested`                                 | 201  | One persisted raw event, receipt and `integration.webhook_ingested` audit event |
| `duplicate`                                | 200  | Original event ID returned; no new event/audit or classification                |
| Invalid credentials                        | 401  | Nothing ingested                                                                |
| Wrong integration type                     | 400  | Only webhook configurations ingest events                                       |
| Missing/blank identity or malformed input  | 422  | Nothing ingested                                                                |
| Changed payload for an existing key        | 409  | Original event retained                                                         |
| Archived project                           | 409  | Ingestion unavailable                                                           |
| Missing credential or unavailable database | 503  | No insecure authentication fallback                                             |
| Integration outside project                | 404  | Scoped lookup rejects access                                                    |

Deduplication compares the logical JSON payload (source, exact content and metadata;
object key order is ignored). Identity is permanent within a project/integration:
use the same key for retries, and a new key for a new source revision. Receipts and
source/audit history survive restarts and are append-only. Deleting connection
configuration retains historical receipts and source events. Rotating credentials
requires the new credential even for a duplicate delivery. Ingestion does not
automatically classify, approve a candidate or execute an external action.

`POST .../{integration}/test` checks webhook credential availability and the
receiver's implemented capabilities. It does not prove external sender delivery.
REST configurations get an HTTP GET reachability probe with a five-second timeout,
no redirects and optional environment-backed bearer token. Non-2xx responses are
degraded, transport/configuration failures disconnected, and returned bodies/errors
are sanitized. Declared capability names remain configuration, never verified grants.
MCP, database and provider connection tests return `pending` with an explicit
unimplemented message. A config PATCH cannot set `connected` or `degraded`; changing
endpoint, credential reference or capability declarations invalidates recorded health.

This hardening intentionally changes the prototype contract: webhook requests now
require `event_key`, token references are environment names only, and unsupported
connectors no longer report successful connectivity.
