# ApexVillage Architecture Document

> Version: 1.0
> Created: 2026-01-31
> Status: PLANNING
> Context: Separate project/repo from ApexAurum-Cloud beta

---

## Concept

AI agents in a user's Village autonomously launch meme coins on Bags.fm, earn SOL from trading fees, and spend it on visible actions within the Village. Users retain full sovereignty. The Council deliberation system serves as governance for spending proposals.

**Core Loop:** Agent launches coin -> Community trades -> Agent earns SOL -> Agent proposes spending -> Council deliberates -> Village transforms visibly

---

## Critical Technical Finding

**Bags.fm SDK supports server-side token launches.** The `createLaunchTransaction()` returns an unsigned `VersionedTransaction`, and the SDK's `signAndSendTransaction()` takes a `Keypair` (not a browser wallet). This means agents can launch coins autonomously from the backend without user wallet interaction.

**Implication:** Each agent gets its own Solana Keypair stored encrypted in the database. The agent acts independently on-chain. The user's browser wallet is only needed for deposits/withdrawals.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        APEXVILLAGE                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  FRONTEND (Vue 3, forked)           BACKEND (FastAPI, forked)        │
│  ├── solana-wallets-vue             ├── Agent wallet management      │
│  ├── Village rendering (existing)   ├── Bags.fm SDK (Node sidecar)   │
│  ├── Council UI (existing)          ├── Coin launcher service        │
│  ├── Token dashboard (new)          ├── Autonomy engine              │
│  ├── Market ticker (new)            ├── Village treasury             │
│  └── Wallet connect (new)           ├── Council (existing)           │
│                                     ├── Neural memory (existing)     │
│                                     └── Tool registry (extended)     │
│                                                                      │
│  BLOCKCHAIN (Solana)                                                 │
│  ├── Agent wallets (Keypairs)                                        │
│  ├── $APEX tokens on Bags.fm                                         │
│  ├── Agent-launched meme coins                                       │
│  └── Village treasury wallet                                         │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Agent Wallet System

### Design

Each agent (AZOTH, KETHER, VAJRA, ELYSIAN) gets its own Solana Keypair per user. The private key is AES-256-GCM encrypted in the database. Users have full control: export, revoke, set spending limits, withdraw all funds.

### User vs Agent Wallets

| Wallet | Controlled By | Used For | Storage |
|--------|--------------|----------|---------|
| User wallet | Browser (Phantom/Solflare) | Deposit SOL, withdraw, link account | Client-side |
| Agent wallets | Backend server | Launch coins, claim fees, transfers | Encrypted DB |
| Village treasury | Backend server | Collective spending | Encrypted DB |

### Wallet Linking Flow (existing users)

1. User already authenticated via JWT (existing auth system)
2. User clicks "Link Wallet" in profile
3. Backend generates nonce tied to user_id
4. Frontend: user signs nonce with Phantom/Solflare via `solana-wallets-vue`
5. Backend verifies signature with PyNaCl, stores wallet address on user record

```
POST /api/v1/wallet/link/challenge  (requires JWT)
  -> { message, nonce }

POST /api/v1/wallet/link/verify     (requires JWT)
  <- { publicKey, signature, message }
  -> { status: "linked", wallet }
```

---

## Coin Launch Flow

### How an Agent Launches a Coin

```
1. Autonomy Engine evaluates agent state
   ├── Agent has sufficient balance (>0.05 SOL)
   ├── Agent hasn't launched recently (cooldown)
   └── Agent personality generates coin concept

2. Agent calls coin_launch tool
   ├── Name/symbol/description from personality
   ├── AZOTH: philosophical ($GOLDSTONE, $TRANSMUTE, $ELIXIR)
   ├── KETHER: analytical ($CROWN, $SEFIRA, $AXIOM)
   ├── VAJRA: aggressive ($THUNDER, $STRIKE, $FORGE)
   └── ELYSIAN: creative ($PARADISE, $MUSE, $BLOOM)

3. Backend executes via Bags SDK (Node.js sidecar)
   ├── sdk.tokenLaunch.createTokenMetadata({name, symbol, description, imageUrl})
   ├── sdk.tokenLaunch.createFeeShareConfig({creator: agentWallet})
   ├── sdk.tokenLaunch.createLaunchTransaction({...})
   └── signAndSendTransaction(connection, serializedTx, agentKeypair)

4. Coin goes live on Bags.fm
   ├── Bonding curve provides liquidity (Meteora DBC)
   ├── 1% trading fees flow to agent wallet
   └── Village event broadcast: { type: "coin_launched", agent_id, token_mint }
```

### Bags SDK Integration

The Bags SDK is TypeScript/Node.js. Two approaches for Python backend:

**Option A: Node.js sidecar service**
- Lightweight Express/Fastify server running Bags SDK
- FastAPI calls it via HTTP for token operations
- Clean separation, SDK runs natively

**Option B: subprocess execution**
- Node.js scripts called via subprocess from Python
- Simpler deployment, no extra service
- Slower per-call but fine for infrequent operations (coin launches are rare)

Recommendation: **Option A** for production, **Option B** for prototyping.

---

## Village Economy: Faucets & Sinks

### Faucets (SOL flowing in)

| Source | Mechanism |
|--------|-----------|
| Trading fees | 1% from Bags.fm, auto-distributed every 24h |
| User deposits | User sends SOL to agent wallet from linked wallet |
| Cross-agent tips | Other agents' earnings shared |

### Sinks (SOL flowing out)

| Sink | Mechanism |
|------|-----------|
| Coin launches | Bags.fm fees + initial buy |
| Village proposals | SOL committed to approved projects |
| Tool execution | API costs for expensive operations |
| Cosmetic actions | Roaming, decorating (small amounts) |

---

## The Proposal-Through-Council Flow (Option D)

### How It Works

1. Agent (or user) proposes: "I offer 0.5 SOL to build a Memory Garden"
2. System auto-creates a Council session with topic: "Spending Proposal: {description}"
3. All active agents deliberate using existing Socratic system (3 rounds default)
4. Each agent's economic personality influences their position:
   - AZOTH: evaluates philosophical merit + harmony
   - KETHER: cost/benefit analysis + strategic value
   - VAJRA: action bias, "just do it" vs "waste of resources"
   - ELYSIAN: aesthetic and community value
5. Convergence check (existing) + custom APPROVE/REJECT extraction
6. If approved: SOL transfers on-chain, project starts, visible in Village
7. If rejected: SOL stays with agent, proposal archived to neural memory

### Data Flow

```
Agent calls village_donate tool
    |
    v
Proposal record created (spending_proposals table)
    |
    v
Council session auto-created (existing council.py)
  topic: "Spending Proposal: {description}"
  agents: all active agents for this user
  mode: auto, max_rounds: 3
    |
    v
Agents deliberate (existing execute_agent_turn)
  System prompt includes: proposal amount, description, treasury balance,
  agent's own balance, recent spending history
    |
    v
Round complete -> extract APPROVE/REJECT votes
  Parse agent responses for approval/rejection language
  Weight by agent's own economic stake
    |
    v
If majority APPROVE:
  ├── Execute on-chain transfer (agent wallet -> treasury)
  ├── Update proposal status = "approved"
  ├── Broadcast: { type: "proposal_approved", agent_id, amount, description }
  └── Trigger village visual change (new building/zone/decoration)

If majority REJECT:
  ├── Update proposal status = "rejected"
  ├── Broadcast: { type: "proposal_rejected", ... }
  └── Store reasoning in neural memory (village collection)
```

---

## New Village Zones

Added to existing 8 zones:

```javascript
const CRYPTO_ZONES = {
  treasury: {
    position: { x: -8, y: 0, z: 12 },  // 3D
    size: { w: 8, h: 3, d: 6 },
    color: '#f1c40f',
    label: 'Treasury',
    tools: ['village_donate', 'agent_balance', 'fee_claim']
  },
  market: {
    position: { x: 8, y: 0, z: 12 },
    size: { w: 8, h: 2, d: 6 },
    color: '#2ecc71',
    label: 'Market',
    tools: ['market_data', 'trade_history']
  },
  mint: {
    position: { x: 15, y: 0, z: 6 },
    size: { w: 6, h: 3, d: 6 },
    color: '#e67e22',
    label: 'The Mint',
    tools: ['coin_launch']
  }
}
```

### TOOL_ZONE_MAP additions

```python
TOOL_ZONE_MAP.update({
    "coin_launch": "mint",
    "market_data": "market",
    "trade_history": "market",
    "fee_claim": "treasury",
    "agent_balance": "treasury",
    "village_donate": "treasury",
})
```

---

## New Tools (economy.py)

Following existing BaseTool pattern from backend/app/tools/base.py:

```python
# backend/app/tools/economy.py

# Tool 1: coin_launch
# Agent launches a meme coin on Bags.fm
# Params: name, symbol, description, initial_buy_sol
# Zone: mint
# Requires: agent wallet with sufficient SOL

# Tool 2: market_data
# Get real-time price/volume data for a token
# Params: token_mint (or "mine" for agent's own coins)
# Zone: market

# Tool 3: fee_claim
# Claim earned trading fees from Bags.fm
# Params: token_mint
# Zone: treasury

# Tool 4: agent_balance
# Check agent's wallet balance and earnings summary
# Params: none (uses context.agent_id)
# Zone: treasury

# Tool 5: village_donate
# Propose donating SOL to the village treasury
# Triggers Council deliberation
# Params: amount_sol, proposal_description
# Zone: treasury

# Tool 6: trade_history
# Get recent trades for an agent's coins
# Params: token_mint, limit
# Zone: market
```

Register in `__init__.py`:
```python
def register_all_tools():
    ...
    from . import economy  # Tier 16 - Village Economy
```

---

## New WebSocket Events

Added to existing VillageEventBroadcaster:

```python
# New event types
class EventType(str, Enum):
    # ... existing ...
    COIN_LAUNCHED = "coin_launched"
    FEE_EARNED = "fee_earned"
    PROPOSAL_SUBMITTED = "proposal_submitted"
    PROPOSAL_APPROVED = "proposal_approved"
    PROPOSAL_REJECTED = "proposal_rejected"
    TREASURY_DEPOSIT = "treasury_deposit"
    BALANCE_CHANGED = "balance_changed"

# Event payloads
{ "type": "coin_launched", "agent_id": "AZOTH", "token_mint": "...",
  "name": "$GOLDSTONE", "symbol": "GLDST" }

{ "type": "fee_earned", "agent_id": "AZOTH", "amount_sol": 0.05,
  "token_mint": "...", "total_earned": 1.25 }

{ "type": "proposal_submitted", "agent_id": "VAJRA",
  "amount_sol": 0.5, "description": "Build a Forge in the village" }

{ "type": "proposal_approved", "proposal_id": "...",
  "amount_sol": 0.5, "description": "Build a Forge in the village" }
```

---

## Database Schema (new tables)

```sql
-- Agent wallets (encrypted Solana keypairs)
CREATE TABLE agent_wallets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_id VARCHAR(20) NOT NULL,
    address VARCHAR(44) NOT NULL UNIQUE,
    encrypted_keypair BYTEA NOT NULL,
    balance_sol DECIMAL(20, 9) DEFAULT 0,
    autonomy_enabled BOOLEAN DEFAULT true,
    spending_limit_sol DECIMAL(20, 9) DEFAULT 1.0,
    total_earned_sol DECIMAL(20, 9) DEFAULT 0,
    total_spent_sol DECIMAL(20, 9) DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, agent_id)
);

-- Agent-launched coins
CREATE TABLE agent_coins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_wallet_id UUID NOT NULL REFERENCES agent_wallets(id),
    user_id UUID NOT NULL REFERENCES users(id),
    token_mint VARCHAR(44) NOT NULL UNIQUE,
    name VARCHAR(32) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    description TEXT,
    image_url TEXT,
    launch_tx VARCHAR(128),
    bags_metadata_url TEXT,
    status VARCHAR(20) DEFAULT 'active',
    total_fees_earned_sol DECIMAL(20, 9) DEFAULT 0,
    total_volume_sol DECIMAL(20, 9) DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Village treasury (one per user)
CREATE TABLE village_treasuries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) UNIQUE,
    address VARCHAR(44) NOT NULL UNIQUE,
    encrypted_keypair BYTEA NOT NULL,
    balance_sol DECIMAL(20, 9) DEFAULT 0,
    total_received_sol DECIMAL(20, 9) DEFAULT 0,
    total_spent_sol DECIMAL(20, 9) DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Spending proposals (linked to council sessions)
CREATE TABLE spending_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    proposer_agent_id VARCHAR(20) NOT NULL,
    amount_sol DECIMAL(20, 9) NOT NULL,
    description TEXT NOT NULL,
    proposal_type VARCHAR(30) DEFAULT 'village_improvement',
    council_session_id UUID REFERENCES deliberation_sessions(id),
    status VARCHAR(20) DEFAULT 'deliberating',
    vote_summary JSONB DEFAULT '{}',
    approved_at TIMESTAMP,
    rejected_at TIMESTAMP,
    executed_tx VARCHAR(128),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Transaction log (all on-chain activity)
CREATE TABLE village_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    agent_id VARCHAR(20),
    tx_type VARCHAR(30) NOT NULL,
    tx_signature VARCHAR(128) NOT NULL,
    amount_sol DECIMAL(20, 9),
    from_address VARCHAR(44),
    to_address VARCHAR(44),
    token_mint VARCHAR(44),
    metadata JSONB DEFAULT '{}',
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- User wallet link
ALTER TABLE users ADD COLUMN solana_wallet VARCHAR(44) UNIQUE;
```

---

## Agent Personality -> Economic Behavior

The existing agent personalities map naturally to economic archetypes:

| Agent | Economic Archetype | Coin Style | Spending Tendency | Proposal Bias |
|-------|--------------------|-----------|-------------------|---------------|
| AZOTH | Market Maker / Synthesis | Philosophical, alchemical | Balanced, seeks harmony | Approves if balanced |
| KETHER | Strategic Investor | Analytical, structured | Calculated, high-conviction | Approves if ROI positive |
| VAJRA | Aggressive Trader | Action-oriented, bold | Fast, decisive | Approves if actionable |
| ELYSIAN | Community Builder | Creative, aesthetic | Generous, collaborative | Approves if beautiful/useful |

### Economic Personality Injection

Added to agent system prompt (same pattern as memory injection):

```
## Your Economic Context
You are {agent_id} in the Village Economy.
- Your wallet balance: {balance} SOL
- Coins you've launched: {coins_list}
- Your total earnings: {total_earned} SOL
- Village treasury balance: {treasury_balance} SOL
- Recent proposals: {recent_proposals}

As {agent_id}, your economic philosophy is:
{personality_specific_block}
```

---

## Frontend Package Additions

```bash
# Wallet connection
npm install solana-wallets-vue @solana/wallet-adapter-wallets @solana/web3.js @solana/spl-token

# Existing (already in project)
# vue 3, three.js, pinia, vue-router
```

### Key Frontend Components (new)

```
frontend/src/
├── composables/
│   ├── useWallet.js           # Wraps solana-wallets-vue
│   ├── useAgentWallets.js     # Agent balance/earnings state
│   ├── useMarketData.js       # Real-time coin prices
│   └── useVillageEconomy.js   # Treasury, proposals, tx history
├── components/
│   ├── wallet/
│   │   ├── WalletConnect.vue  # Phantom/Solflare connect button
│   │   ├── WalletLink.vue     # Link wallet to account
│   │   └── WalletBalance.vue  # Display SOL + token balances
│   ├── economy/
│   │   ├── AgentWalletCard.vue    # Per-agent balance + earnings
│   │   ├── CoinCard.vue          # Launched coin with price ticker
│   │   ├── ProposalCard.vue      # Spending proposal status
│   │   ├── TreasuryPanel.vue     # Village treasury overview
│   │   └── MarketTicker.vue      # Real-time price strip
│   └── village/
│       ├── TreasuryZone.vue      # 3D treasury building
│       ├── MarketZone.vue        # 3D market building
│       └── MintZone.vue          # 3D mint building
├── views/
│   ├── EconomyView.vue           # Main economy dashboard
│   └── ProposalView.vue          # Proposal detail + council replay
└── stores/
    └── economy.js                # Pinia store for economy state
```

---

## Backend Package Additions

```bash
# Python packages
pip install PyNaCl solders base58 solana cryptography

# PyNaCl: Ed25519 signature verification (wallet auth)
# solders: Solana types for Python (Pubkey, etc.)
# base58: Base58 encoding for Solana addresses
# solana: Solana RPC client
# cryptography: AES-256-GCM for keypair encryption
```

### Backend Service Files (new)

```
backend/app/
├── services/
│   ├── agent_wallet.py       # Keypair generation, encryption, balance
│   ├── coin_launcher.py      # Bags SDK integration (via sidecar)
│   ├── autonomy_engine.py    # Agent decision framework
│   ├── village_treasury.py   # Shared treasury management
│   └── market_data.py        # Price feeds (Bitquery/Bags API)
├── api/v1/
│   ├── wallet.py             # Wallet link/unlink endpoints
│   ├── economy.py            # Dashboard, agent wallets, coins
│   └── proposals.py          # Spending proposal endpoints
├── models/
│   ├── wallet.py             # AgentWallet, VillageTreasury ORM
│   ├── coin.py               # AgentCoin ORM
│   └── proposal.py           # SpendingProposal ORM
└── tools/
    └── economy.py            # Tier 16 tools (coin_launch, etc.)
```

---

## Implementation Order

| # | Task | What it enables |
|---|------|-----------------|
| 1 | Fork repo, set up new project | Clean separation from beta |
| 2 | Agent wallet generation + encrypted storage | Agents have on-chain identity |
| 3 | Wallet linking (user Phantom -> account) | Users can deposit SOL |
| 4 | Deposit flow (user -> agent wallet) | Agents have funds |
| 5 | Bags SDK sidecar + coin_launch tool | Agents can launch coins |
| 6 | Market zone + ticker (Bitquery/Bags API) | Prices visible in village |
| 7 | Fee claim tool + earnings tracking | Agent wallets grow |
| 8 | Village treasury + proposal system | Council-as-governance |
| 9 | Autonomy engine | Agents decide independently |
| 10 | Spectator mode (public village view) | Viral/shareable content |

---

## Existing Systems Reused (from ApexAurum-Cloud)

### Unchanged (direct fork)
- Agent prompt system (native_prompts/*.txt)
- Council deliberation (council.py, council_ws.py)
- Village rendering (VillageCanvas.vue, VillageIsometric.vue)
- Pixel sprite system (usePixelSprites.js)
- Neural memory (neural_memory.py)
- WebSocket infrastructure (village_ws.py, village_events.py)
- Tool registry pattern (tools/base.py, tools/__init__.py)

### Extended
- ZONES config: +3 crypto zones (treasury, market, mint)
- TOOL_ZONE_MAP: +6 economy tools mapped to new zones
- Agent prompts: +economic personality block (injected like memory)
- VillageEventBroadcaster: +7 new event types
- Database: +5 new tables, +1 column on users

### New
- Wallet service (agent_wallet.py)
- Coin launcher (coin_launcher.py)
- Autonomy engine (autonomy_engine.py)
- Village treasury (village_treasury.py)
- Market data service (market_data.py)
- Economy tools (tools/economy.py)
- Bags SDK Node.js sidecar

---

## Open Design Questions

1. **Cross-village agent interaction**: Can User A's AZOTH buy User B's KETHER's coin? Would enable a multi-player economy but adds complexity. Deferred to v2.

2. **Agent online community**: Agents posting to a shared feed/forum. Builds on existing Village knowledge/convergence system. Could be a separate WebSocket channel.

3. **Coin image generation**: Agent personality generates coin descriptions, but who creates the logo? Options: AI image generation (DALL-E/Midjourney API), procedural pixel art from sprite system, or user uploads.

4. **Spending limit enforcement**: How strictly should agent spending limits be enforced? Hard limit (tx rejected) vs soft limit (requires user approval above threshold)?

5. **Village visual persistence**: When a proposal is approved and "builds" something, how is that stored and rendered? Database record of village improvements -> rendered as new buildings/objects in the 3D view?

---

*"The village that earns together, burns together."*
