## Fantasy Crypto Tournament – Overview

Fantasy Crypto Tournament is a fantasy game for the crypto market. Players collect card decks that represent real tokens and compete in time‑boxed tournaments based on real price movements.

This repository contains:
- **On-chain contract** for cards (ERC‑721) on Avalanche (`HodleagueCards`; packs are off-chain)
- **Backend API** (FastAPI + async SQLAlchemy + PostgreSQL)
- **Scheduler jobs** for scoring, tournaments and blockchain listeners
- **Dev tooling** for migrations, scripts and monitoring

---

## Tournament contracts (start here)

On-chain logic lives in the `tournament-contracts` subproject. If you want to understand how packs and cards work on-chain, start there:

- [`tournament-contracts/README.md`](tournament-contracts/README.md)

Key ideas:

- `HodleagueCards.sol` (ERC‑721)
  - Each NFT represents a fantasy card linked to a token in the game DB.
  - On-chain state is minimal: only `tokenId` and owner.
  - Metadata (name, stats, images, rarity) is served by the backend at `NFT_METADATA_BASE_URL` → `/nft/cards/{id}`.

- Packs (off-chain)
  - User packs are stored in PostgreSQL (`UserPack`, `PackOpening`) and managed by the backend.
  - When a user opens a pack, the backend:
    - deterministically selects `card_ids` based on pack configuration and seeds,
    - stores the exact result in `PackOpening` (`status="prepared"`),
    - signs a `mintWithSignature` payload for `HodleagueCards`,
    - listens for the on-chain `PackOpened` event to create `UserCard` rows.
  - A legacy `HodleaguePacks.sol` ERC‑1155 contract exists in the `tournament-contracts` folder for historical reference, but it is not used by the current backend flow.

The contract README describes roles and events for `HodleagueCards` and the legacy packs contract in more detail.

---

## High-level architecture

The system is split into three layers:

- **Smart contracts (Avalanche C‑Chain)** – source of truth for card ownership:
  - ERC‑721 cards (`HodleagueCards`)
  - A legacy ERC‑1155 packs contract (`HodleaguePacks`) remains in the repo but is not used in the live game flow.

- **Backend API (FastAPI)** – game logic and API surface:
  - Registration and auth (`api/routes/auth.py`)
  - Pack flows (`api/routes/packs.py`, `api/routes/admin/packs.py`)
  - Tournament lifecycle, scoring, user profiles, history

- **Database (PostgreSQL + SQLAlchemy models)** – game state and indexing:
  - `UserPack` – pack inventory per user (mirrors on-chain events + legacy off-chain packs)
  - `PackOpening` – log of pack opens and resulting NFT ids
  - `UserCard` – individual cards with links to `cards`, `tokens`, `rarities`, tournaments
  - Additional tables for tournaments, rewards, leaderboards, etc.

### Pack lifecycle (off-chain + cards contract)

1. **Pack inventory**
   - The backend manages user packs in PostgreSQL (`UserPack`), completely off-chain.
   - Packs can be granted by admin tools or game logic; each record has `user_id`, `pack_type_id`, `is_opened` and timestamps.

2. **Prepare open (off-chain)**
   - Client calls `/api/packs/prepare-open` with a specific `user_pack_id` and a 32‑byte client seed.
   - The backend:
     - verifies ownership and that the pack is not opened yet,
     - deterministically selects `card_ids` based on pack configuration and seeds,
     - stores the exact result in `PackOpening` (`status="prepared"`),
     - signs a `mintWithSignature` payload for `HodleagueCards` and returns it to the client.
   - If `prepare-open` is called again for the same `user_pack_id`, the backend returns the same `PackOpening` (no reroll).

3. **Mint cards on-chain**
   - The client sends a transaction to `HodleagueCards.mintWithSignature` with the data from `prepare-open`.
   - After the transaction is mined, the client calls `/api/packs/openings/{id}/confirm` with the `tx_hash`.
   - The backend:
     - parses the on-chain `PackOpened` event,
     - verifies it matches the stored opening,
     - creates `UserCard` records and marks the opening as `completed`,
     - sets `UserPack.is_opened = true` so the pack disappears from the unopened inventory.

### Cards and metadata

- Each `UserCard` row connects:
  - a blockchain NFT (`nft_token_id`, `chain_id`, `contract_address`),
  - a game card template (`card_id` → `cards` table),
  - optional tournament usage and expiry (`expires_at`).
- When wallets, explorers or marketplaces resolve `tokenURI`, they hit `/nft/cards/{tokenId}`, which uses DB tables (`cards`, `tokens`, `rarities`) to render the JSON metadata (name, description, image, attributes).

---

## Repository structure

- `api/` – FastAPI routers (HTTP API)
- `services/` – business logic (tournaments, packs, scoring, blockchain listeners, health checks)
- `models/` – SQLAlchemy models and DB schema
- `migrations/` – Alembic migrations
- `scripts/` – CLI utilities (tests, migrations, E2E, NFT base URI)
- `tournament-contracts/` – Solidity contracts and Foundry project
- `monitoring/` – Prometheus + Grafana stack for PostgreSQL monitoring
- `config.py` – application configuration (reads from `.env`)
- `main.py` – FastAPI entry point

---

## Monitoring and health checks

The `monitoring/` folder contains a Prometheus + Grafana stack for PostgreSQL metrics (see `monitoring/README.md` for details).

Additional health checks keep on-chain and DB inventories in sync:

- `logs/pack_health.log` – warnings when ERC‑1155 `balanceOf` does not match the count of unopened `UserPack` records.
- `logs/card_health.log` – warnings when ERC‑721 `ownerOf` does not match `UserCard` ownership.


