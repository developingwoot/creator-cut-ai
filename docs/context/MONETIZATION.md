# Monetization

## v1 — BYOK (Bring Your Own Key)

The v1 desktop app is free to download and run. Users supply their own Anthropic API key.

**Rationale:** Removes the need for payment infrastructure in v1. The target user
(technically confident creator) is comfortable with API keys. This also means zero
marginal cost to the developer — Claude usage is billed directly to the user's account.

**API key storage:** Resolved in this order:
1. `ANTHROPIC_API_KEY` environment variable
2. OS keychain (service `"creatorcut-ai"`, macOS `security` CLI)
3. `~/.creatorcut/config.json` (mode 0600)

The UI will include a settings screen for key entry that calls `key_manager.store_key()`.

**Approximate cost to user per edit (5 clips, 30 min footage):**
- With prompt caching: ~$0.02–$0.05
- Without caching: ~$0.08–$0.20
This is cheap enough that individual project cost is not a meaningful friction point.

---

## v2 — Subscription Tiers

> **Build status:** Not started. Do not implement until v2 milestone is approved.
> Stripe integration lives in `routes/billing.py` (file exists as a stub).

### Tiers

| Tier | Price | Limits | API key |
|---|---|---|---|
| Free | $0 | 3 edits/month, max 5 clips per project | BYOK only |
| Creator | $12/month | 20 edits/month, max 20 clips | Hosted (included) or BYOK |
| Pro | $29/month | Unlimited edits, max 50 clips | Hosted (included) or BYOK |

BYOK users on any paid tier get a 30% cost reduction (we're not paying for their API usage).

### Edit Limit Enforcement

Tracked in a new `usage` table (v2 schema change). The `SubscriptionError` /
`EditLimitReachedError` exception hierarchy is already defined in `exceptions.py`.

Limit check runs at the start of `POST /api/projects/{id}/analyze`.
If the user is over their edit limit: HTTP 402 with a clear upgrade message.

### Stripe Integration (`routes/billing.py`)

- Webhook receiver for `checkout.session.completed` and `customer.subscription.deleted`
- Stores subscription status in the `usage` table
- Stripe Checkout hosted page for upgrades (no custom payment form in v1)

### BYOK as a Power-User Feature

Users who supply their own key on a paid tier bypass the hosted-key cost allocation.
They still count against edit limits but don't consume hosted API budget.
This is a retention feature: power users who would churn over cost stay on a paid plan.

---

## Cost Structure (Hosted Tiers)

Per-edit Claude cost at moderate usage (10 clips, 1 hour footage):
- Pass 1 (10 clips × claude-sonnet-4-6, cached): ~$0.04
- Pass 2 (claude-opus-4-7, single call): ~$0.02
- Total per edit: ~$0.06 with caching

At $12/month with 20 edits/month ceiling: max API cost is ~$1.20, leaving $10.80 gross
margin before infrastructure. This only works if prompt caching is always on — breaking
caching makes the unit economics unviable.
