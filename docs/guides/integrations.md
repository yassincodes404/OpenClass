# External event ingestion

The existing integration webhook route supports generic bearer deliveries and
explicitly configured signed ingress. It does not execute vendor actions or
grant provider authority. See [durable outbound delivery](outbound-delivery.md)
for the separate opt-in HTTP sink.

Set a token in the **server process environment**, then store its environment
variable name as `secret_ref`. Names match `[A-Z][A-Z0-9_]*`. Plaintext tokens are
not configuration values. Missing or blank environment values fail closed.

```json
{
  "name": "Helpdesk events",
  "type": "webhook",
  "secret_ref": "OPENCLASS_INTEGRATION_SECRET_HELPDESK"
}
```

Create the configuration with `POST /api/v1/projects/{project}/integrations`.
Use the deployment's internal-token/workspace boundary for management access.
Webhook authentication is scoped to ingestion, not management authorization.

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
        token=os.environ["OPENCLASS_INTEGRATION_SECRET_HELPDESK"],
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
| Payload larger than 128,000 bytes           | 413  | Rejected before normalization                                                   |

Deduplication compares the logical JSON payload (source, exact content and metadata;
object key order is ignored). Identity is permanent within a project/integration:
use the same key for retries, and a new key for a new source revision. Receipts and
source/audit history survive restarts and are append-only. Deleting connection
configuration retains historical receipts and source events. Rotating credentials
requires the new credential even for a duplicate delivery. Ingestion does not
automatically classify, approve a candidate or execute an external action.

## Signed ingress

Persist `signature: {"mode": "zendesk", "replay_window_seconds": 300}` when creating
or patching a webhook. Supported modes:

- `bearer` (default): unchanged generic `WebhookDelivery` contract above.
- `zendesk`: `X-Zendesk-Webhook-Signature` is base64(HMAC-SHA256(secret,
  timestamp bytes + **exact raw body bytes**)); timestamp comes from
  `X-Zendesk-Webhook-Signature-Timestamp`. ISO-8601 timestamps must be timezone
  aware, within the configured window (30–900 seconds), including future skew.
  Normalization requires a top-level string event `id` and textual
  `detail.subject`/`title`/`description`/`comment.body`, or the same fields under
  `detail.ticket`. Custom Zendesk trigger payloads must include a stable event
  revision ID, not just a ticket ID.
- `intercom_sha1`: the documented legacy `X-Hub-Signature: sha1=<hex>` over exact
  raw body bytes using the app signing secret. This is **SHA-1, not SHA-256**.
  Top-level notification `id` is the stable key; text comes from `data.item`
  title/body, source body and conversation-parts bodies. Other event shapes
  without supported text fail with 422. Native SHA-1 notifications have no
  authenticated delivery timestamp: permanent scoped receipts prevent repeated
  ingestion, but cannot establish recency of a previously unseen notification.
- `customer_hmac_sha256`: a **non-native customer adapter envelope**, using the
  generic body and `X-OpenClass-Timestamp` / `X-OpenClass-Signature`, with the same
  timestamp + raw-body SHA-256/base64 construction as above. Only string `vendor`
  and `ticket_id` metadata are retained, plus a raw-body digest. A customer-owned
  Freshdesk adapter can emit this envelope. Freshdesk automation webhook docs do
  **not establish a native HMAC protocol**; native Freshdesk HMAC is unsupported.

All signed modes verify before JSON normalization. No missing or invalid signature
falls back to bearer. Missing operator credentials return 503; bad signatures or
replay timestamps return 401 without echoing submitted values. Payload/metadata
credential echoes are rejected, including ignored vendor fields. No authentication
headers or raw signatures are copied into normalized provenance. Signed payload
digests bind all original bytes: retries with identical bytes replay; the same key
with changed bytes conflicts, even if ignored fields or whitespace changed.
Cross-project and cross-integration receipt scopes remain independent.
The legacy `/webhooks/{source}` route remains bearer-authenticated and simulated;
it rejects configurations in signed mode instead of bypassing their authentication.

Protocol sources:
[Zendesk verification](https://developer.zendesk.com/documentation/webhooks/verifying/),
[Zendesk ticket event shapes](https://developer.zendesk.com/api-reference/webhooks/event-types/ticket-events/),
[Intercom webhook model](https://developers.intercom.com/docs/references/2.2/webhooks/webhook-models),
[Freshdesk automation webhooks](https://support.freshdesk.com/support/solutions/articles/132589-using-webhooks-in-the).
These establish a deliberately limited implementation, not support for every topic,
legacy transport, or vendor action.

## Honest health scope

`POST .../{integration}/test` persists `integration.tested`; a PATCH cannot set
`connected`/`degraded`. Endpoint, secret reference, capabilities, signature or
outbound policy changes invalidate recorded health. Configured capabilities are
never execution grants.

- Webhook: checks local credential availability and ingress implementation only,
  not external sender delivery.
- REST/provider: bounded GET reachability only; no fabricated inference grant.
  Non-2xx (including 401/403) is degraded; transport/configuration failure is
  disconnected. No response body or exception string is persisted.
- MCP: only HTTP JSON responses using protocol version `2025-03-26`, with real
  JSON-RPC `initialize`, `notifications/initialized` (202), then `tools/list`.
  IDs/results/protocol/tools/session headers are checked; session and protocol
  headers are sent on subsequent requests. At most three pages, 100 tools/page,
  64,000 bytes/response and eight seconds overall (three-second HTTP timeouts).
  RPC errors, wrong IDs, invalid JSON, repeated cursors, unavailable tools and
  unsupported SSE/legacy GET transports fail closed. Observed tool names are
  availability evidence, not permission to call them.
- Database: operator sets a dedicated environment reference such as
  `OPENCLASS_INTEGRATION_DATABASE_CUSTOMER_SECRET` to a
  `postgresql+asyncpg://...` DSN. Do not put the DSN/password in API configuration.
  `endpoint` and nonempty `metadata` are rejected: neither can override the
  operator target or provide SQL. A real read-only `SELECT 1` uses three-second
  connection/command/statement bounds and disposes its SQLAlchemy engine.
  SQLite/files, global application DB secrets and arbitrary SQL are unsupported.
  This explicit operator DSN may target an internal database; it is a separate
  trust boundary from untrusted public HTTP destinations. DB references cannot
  become HTTP bearer credentials.

Unconfigured drafts return pending, without capabilities. HTTP connections resolve
and validate all DNS answers at the transport boundary, pin a public IP and retain
the original Host/TLS SNI/certificate hostname. No proxies, credentialed URLs,
private/metadata targets, redirects or disabled TLS verification. Mock transports
are test-only injection. Real disposable PostgreSQL tests are marked `postgres`;
offline tests neither call vendors nor require online keys.

Migration `0030_outbound_deliveries` adds explicit signature/outbound configuration
with `{}` defaults preserving legacy bearer/simulated behavior. No startup schema
creation occurs. See the outbound guide for downgrade/data-preservation policy.
