# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

ApexAurum-Bags is the crypto-village extension of ApexAurum Cloud. AI agents autonomously launch meme coins on Bags.fm (Solana), earn SOL from trading fees, and spend it on visible actions within a Village world. The Council deliberation system serves as governance for spending proposals.

**Always read `HANDOVER.md` first for current deployment state and known issues.**

**Parent project:** ApexAurum-Cloud (the SaaS beta, separate repo/deployment, DO NOT modify)
**Architecture doc:** See `docs/ARCHITECTURE.md` for the full technical blueprint.

## Workflow

**Commit, push, done.** Railway auto-deploys both backend and frontend on push to `main`.

```bash
# Standard workflow
git add <files> && git commit -m "message" && git push origin main
# Then verify:
curl -s https://<BACKEND_URL>/health | python3 -m json.tool
```

## Railway Deployment

**Railway auto-deploys from GitHub on push to main.** Manual GraphQL deploy only needed for special operations.

**Railway IDs:** (to be configured when Railway project is created)
- Token: `TBD`
- Backend Service: `TBD`
- Frontend Service: `TBD`
- Environment: `TBD`
- Bags Sidecar Service: `TBD`

**Cache Busting:** Frontend Dockerfile has `ARG CACHE_BUST=N`. Increment to force fresh builds.

## Architecture

```
backend/
├── app/
│   ├── main.py                # FastAPI entry, /health
│   ├── config.py              # Settings, tier config
│   ├── api/v1/
│   │   ├── auth.py            # JWT login/register (from parent)
│   │   ├── chat.py            # Chat with agents (from parent)
│   │   ├── council.py         # Council deliberation (from parent)
│   │   ├── council_ws.py      # Council WebSocket (from parent)
│   │   ├── village.py         # Village knowledge (from parent)
│   │   ├── village_ws.py      # Village events WS (from parent)
│   │   ├── wallet.py          # NEW: Wallet link/unlink
│   │   ├── economy.py         # NEW: Dashboard, agent wallets, coins
│   │   └── proposals.py       # NEW: Spending proposals
│   ├── services/
│   │   ├── agent_wallet.py    # NEW: Keypair generation, encryption
│   │   ├── coin_launcher.py   # NEW: Bags SDK integration
│   │   ├── autonomy_engine.py # NEW: Agent decision framework
│   │   ├── village_treasury.py# NEW: Shared treasury management
│   │   ├── market_data.py     # NEW: Price feeds
│   │   └── village_events.py  # Extended with economy events
│   ├── models/
│   │   ├── wallet.py          # NEW: AgentWallet, VillageTreasury
│   │   ├── coin.py            # NEW: AgentCoin
│   │   └── proposal.py        # NEW: SpendingProposal
│   └── tools/
│       └── economy.py         # NEW: Tier 16 - coin_launch, market_data, etc.

bags-sidecar/                  # Node.js service wrapping Bags SDK
├── package.json
├── index.js                   # Express server
├── services/
│   ├── token-launch.js        # createTokenMetadata, createLaunchTransaction
│   ├── fee-claim.js           # claimVirtualPoolFees, getClaimablePositions
│   └── market-data.js         # getSwapQuote, price feeds
└── Dockerfile

frontend/src/
├── composables/
│   ├── useWallet.js           # NEW: Wraps solana-wallets-vue
│   ├── useAgentWallets.js     # NEW: Agent balance/earnings
│   ├── useMarketData.js       # NEW: Real-time coin prices
│   ├── useVillageEconomy.js   # NEW: Treasury, proposals, tx history
│   ├── useVillage.js          # From parent (extended)
│   └── useVillageIsometric.js # From parent (extended)
├── components/
│   ├── wallet/                # NEW: WalletConnect, WalletLink, WalletBalance
│   ├── economy/               # NEW: AgentWalletCard, CoinCard, ProposalCard
│   └── village/               # From parent + TreasuryZone, MarketZone, MintZone
├── views/
│   ├── VillageGUIView.vue     # From parent (extended)
│   ├── EconomyView.vue        # NEW: Economy dashboard
│   └── ProposalView.vue       # NEW: Proposal detail + council replay
└── stores/
    └── economy.js             # NEW: Pinia store for economy state
```

## Key Concepts

### Agent Wallets
Each agent (AZOTH, KETHER, VAJRA, ELYSIAN) gets a Solana Keypair per user. Private keys are AES-256-GCM encrypted in the database. Users have full control: export, revoke, set spending limits, withdraw.

### Bags.fm Integration
Agents launch meme coins via the Bags SDK (`@bagsfm/bags-sdk`). The SDK runs in a Node.js sidecar service. Key flow: `createTokenMetadata` -> `createFeeShareConfig` -> `createLaunchTransaction` -> `signAndSendTransaction`. All server-side with agent Keypairs.

### Council-as-Governance (Option D)
Spending proposals trigger Council deliberation sessions. Agents debate using the existing Socratic system. Approval/rejection is extracted from agent responses. Approved proposals execute on-chain transfers.

### Village Economy
Three new zones: Treasury, Market, The Mint. Six new tools: coin_launch, market_data, fee_claim, agent_balance, village_donate, trade_history. Seven new WebSocket event types for real-time economy visualization.

## Tech Stack

**Backend (Python):**
- FastAPI, SQLAlchemy, PostgreSQL + pgvector
- PyNaCl (signature verification), solders (Solana types), cryptography (AES)
- solana-py (RPC client)

**Bags Sidecar (Node.js):**
- @bagsfm/bags-sdk, @solana/web3.js
- Express (HTTP API for backend to call)

**Frontend (Vue 3):**
- solana-wallets-vue (Phantom/Solflare connection)
- @solana/web3.js, @solana/spl-token
- Three.js (Village 3D), Pinia (state)

## Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| "Not authenticated" | Use `get_current_user_optional` for testing |
| Deploy succeeds but old code | Increment `CACHE_BUST` in Dockerfile |
| API returning HTML | Check `https://` prefix in VITE_API_URL |
| "undefined" in localStorage | Auth store auto-cleans bad values |
| Wallet signature fails | Check base58 vs base64 encoding mismatch |
| Bags SDK timeout | Check Helius RPC endpoint and rate limits |
| Agent wallet balance stale | Balance is cached in DB, call refresh endpoint |
| Council proposal stuck | Check council_ws.py end event guarantee |

## Key Patterns

**HTTPS Fix (inherited from parent):**
```javascript
let apiUrl = import.meta.env.VITE_API_URL || ''
if (apiUrl && !apiUrl.startsWith('http://') && !apiUrl.startsWith('https://')) {
  apiUrl = 'https://' + apiUrl
}
```

**Token Validation (inherited from parent):**
```javascript
function getValidToken(key) {
  const value = localStorage.getItem(key)
  if (!value || value === 'undefined' || value === 'null') {
    if (value) localStorage.removeItem(key)
    return null
  }
  return value
}
```

**Wallet Signature Verification (new):**
```python
import nacl.signing
from solders.pubkey import Pubkey

def verify_solana_signature(public_key_str, signature_b64, message_b64):
    pubkey = Pubkey.from_string(public_key_str)
    verify_key = nacl.signing.VerifyKey(bytes(pubkey))
    signature = base64.b64decode(signature_b64)
    message = base64.b64decode(message_b64)
    verify_key.verify(message, signature)
    return True
```

## Environment Variables

**Backend:**
```
DATABASE_URL=postgresql+asyncpg://...
ANTHROPIC_API_KEY=...
JWT_SECRET=...
BAGS_SIDECAR_URL=http://bags-sidecar:3001
WALLET_ENCRYPTION_KEY=...          # 32-byte key for AES-256-GCM
HELIUS_RPC_URL=https://mainnet.helius-rpc.com/?api-key=...
```

**Bags Sidecar:**
```
BAGS_API_KEY=...                   # From dev.bags.fm
HELIUS_RPC_URL=...                 # Same RPC endpoint
PORT=3001
```

**Frontend:**
```
VITE_API_URL=https://...
VITE_SOLANA_NETWORK=mainnet-beta
VITE_SOLANA_RPC_URL=https://...
```

## Repository Structure

- `CLAUDE.md` - This file (Claude Code guidance)
- `HANDOVER.md` - Session-to-session state (read this first!)
- `docs/ARCHITECTURE.md` - Full technical blueprint
- `docs/MASTERPLAN.md` - Tokenomics and launch strategy
- `backend/` - FastAPI backend (forked from ApexAurum-Cloud + economy extensions)
- `bags-sidecar/` - Node.js Bags SDK service
- `frontend/` - Vue 3 frontend (forked from ApexAurum-Cloud + wallet/economy UI)

## Related Projects

- **ApexAurum-Cloud** (`/home/hailo/claude-root/Projects/ApexAurum-Cloud`) - Parent SaaS project. DO NOT modify from this repo.
- **Knowledge Base** (`/home/hailo/claude-root/knowledge-base/bags-fm/`) - Bags.fm docs, crypto masterplan, architecture doc.

## URLs

- Frontend: `TBD` (Railway deployment pending)
- Backend: `TBD`
- Bags Sidecar: `TBD` (internal service, not public)
- Bags.fm: https://bags.fm
- Bags Dev Portal: https://dev.bags.fm
- Bags Docs: https://docs.bags.fm

---

*"The village that earns together, burns together."*
