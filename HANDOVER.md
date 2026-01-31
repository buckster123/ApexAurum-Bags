# HANDOVER.md - ApexAurum-Bags

## Current State

**Build:** v0 - Project initialization
**Status:** PLANNING - Architecture complete, repo scaffolded, no code yet
**Last Session:** 1 (2026-01-31)

## Quick Context

ApexAurum-Bags is a separate project from the ApexAurum Cloud beta. AI agents launch meme coins on Bags.fm, earn SOL, and spend it visibly in a Village world. Council deliberation governs spending.

**Parent project:** ApexAurum-Cloud (live beta, 5+ testers, DO NOT touch)

## What Exists

- [x] GitHub repo: `buckster123/ApexAurum-Bags`
- [x] Local working folder: `/home/hailo/claude-root/Projects/ApexAurum-Bags`
- [x] CLAUDE.md with full project guidance
- [x] Architecture doc at `docs/ARCHITECTURE.md`
- [x] Masterplan at `docs/MASTERPLAN.md`
- [x] .gitignore configured

## What's Needed Next

### Before Writing Code
- [ ] Set up Railway project (3 services: backend, frontend, bags-sidecar)
- [ ] Get Bags.fm API key from dev.bags.fm
- [ ] Get Helius RPC endpoint for Solana mainnet
- [ ] Generate WALLET_ENCRYPTION_KEY for agent keypair storage
- [ ] Fork ApexAurum-Cloud codebase into this repo's backend/ and frontend/

### Implementation Order (from Architecture doc)
1. Fork repo structure from ApexAurum-Cloud
2. Agent wallet generation + encrypted storage
3. Wallet linking (user Phantom -> account)
4. Deposit flow (user -> agent wallet)
5. Bags SDK sidecar + coin_launch tool
6. Market zone + ticker
7. Fee claim tool + earnings tracking
8. Village treasury + proposal system
9. Autonomy engine
10. Spectator mode

## Architecture Summary

```
User's Village
  Agent (AZOTH) --launches--> $GOLDSTONE (meme coin on Bags.fm)
    |                              |
    |                              v
    |                        Community trades
    |                              |
    |                              v
    <--1% fees-----------  Bags.fm DividendsBot
    |
    v
  Agent Wallet (SOL)
    |
    +--> "Build a tool" (spends SOL via Council proposal)
    +--> "Donate to Village" (shared treasury)
    +--> "Launch another coin" (reinvest)
```

## Key Technical Decisions

- **Agent wallets are server-side Keypairs** (not browser wallets) - enables autonomous on-chain actions
- **Bags SDK runs in Node.js sidecar** - SDK is TypeScript, backend is Python
- **Council-as-Governance** (Option D) - spending proposals trigger deliberation sessions
- **Meme coins only** - agents only interact with Bags.fm, no DeFi/DEX
- **User sovereignty** - full control over agent wallets, export, revoke, spending limits

## Knowledge Base

All planning docs live in `/home/hailo/claude-root/knowledge-base/bags-fm/`:
- `APEX_CRYPTO_MASTERPLAN.md` - Tokenomics, governance, launch strategy
- `bags-fm-complete-guide.md` - Bags.fm API + SDK reference
- `APEXVILLAGE_ARCHITECTURE.md` - Full technical blueprint

## Session Log

### Session 1 (2026-01-31) - Project Genesis
- Explored crypto-village concept with user
- Researched existing AI+token projects (Truth Terminal, Virtuals, ElizaOS, RALPH/GAS)
- Deep-dived Village/Council/Tools architecture of parent project
- Researched Solana wallet integration (solana-wallets-vue, PyNaCl, wallet linking)
- Confirmed Bags SDK supports server-side token launches with Keypairs
- Designed Option D: Council-as-Governance for spending proposals
- Designed village economy (faucets/sinks, agent personalities as economic archetypes)
- Wrote full architecture document (APEXVILLAGE_ARCHITECTURE.md)
- Created repo, CLAUDE.md, HANDOVER.md, project structure

---

*Next session: Set up accounts (Bags, Helius), fork parent codebase, begin Step 1.*
