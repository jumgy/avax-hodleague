# Hodleague (Backend)

Backend API and services for **Hodleague**: a fantasy league where you collect token cards, build decks, and compete for rewards.

## What is it?

Hodleague is a game where your intuition and market understanding decide everything. Collect cards, build your deck, and compete in weekly tournaments. Results are driven by real token dynamics — those who read the market best come out on top.

This repository is the **backend** of Hodleague: a FastAPI app that serves the API, manages packs and tournaments, and verifies on-chain actions (card mints, tournament registration).

## What this repo contains
- **On-chain contract** for cards (ERC‑721) on Avalanche (`HodleagueCards`; packs are off-chain)
- **Backend API** (FastAPI + async SQLAlchemy + PostgreSQL)
- **Scheduler jobs** for scoring, tournaments and blockchain listeners
- **Dev tooling** for migrations, scripts and monitoring

---

## Tournament contracts (start here)

On-chain logic lives in the `tournament-contracts` subproject. If you want to understand how packs and cards work on-chain, start there:

- [`tournament-contracts/README.md`](tournament-contracts/README.md)

Key ideas:

- [`HodleagueCards.sol` (ERC‑721)](https://testnet.snowtrace.io/address/0x848dDC58cb7A8376cDb814c83db8F3B925374f90/contract/43113/code)
  - Each NFT represents a fantasy card linked to a token in the game DB.
  - On-chain state is minimal: only `tokenId` and owner.
  - Metadata (name, stats, images, rarity) is served by the backend at `NFT_METADATA_BASE_URL` → `/nft/cards/{id}`.

- [`TournamentRegistry.sol`](https://testnet.snowtrace.io/address/0x2Fa5F1C94061Ff8d1D8706D7FC184F9162C7d444/contract/43113/code)
  - Stores one deck commitment (hash) per user per tournament on-chain.
  - User calls `registerDeck(tournamentId, deckHash)` or `unregisterDeck(tournamentId)`; the backend returns `deck_hash` and contract info from `POST /api/tournaments/{id}/validate-deck`. After the on-chain tx, the client sends the `tx_hash` to `POST /api/tournaments/{id}/register` (or `.../unregister`), and the backend verifies the tx and writes to PostgreSQL.
  - Configure `TOURNAMENT_CONTRACT_ADDRESS` in `.env` to point to the deployed contract.

- Packs (off-chain)
  - User packs are stored in PostgreSQL (`UserPack`, `PackOpening`) and managed by the backend.
  - When a user opens a pack, the backend:
    - deterministically selects `card_ids` based on pack configuration and seeds,
    - stores the exact result in `PackOpening` (`status="prepared"`),
    - signs a `mintWithSignature` payload for `HodleagueCards`,
    - returns that payload to the client; the client calls `HodleagueCards.mintWithSignature` and then `POST /api/packs/openings/{id}/confirm` with `tx_hash`, and the API returns the full opening with cards in one response. A background job also polls `PackOpened` events every 10 seconds so `UserCard` rows are created even if the client never sends `tx_hash`.
  - A legacy `HodleaguePacks.sol` ERC‑1155 contract exists in the `tournament-contracts` folder for historical reference, but it is not used by the current backend flow.

The contract README describes roles, events, and `TournamentRegistry` in more detail.

---

## High-level architecture

The system is split into three layers:

- **Smart contracts (Avalanche C‑Chain)** – source of truth for card ownership and tournament registration:
  - ERC‑721 cards (`HodleagueCards`) – mint via `mintWithSignature`, metadata from backend.
  - Tournament registration (`TournamentRegistry`) – store deck commitment per user per tournament; backend verifies tx and syncs to DB.
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
   - After the transaction is mined, the client calls `POST /api/packs/openings/{id}/confirm` with the `tx_hash`. The backend parses the `PackOpened` event, creates `UserCard` records, marks the opening as `completed`, and returns the full opening (including `cards_received` with images) in the same response so no extra GET is needed.
   - A scheduler job runs every 10 seconds and polls recent blocks for `PackOpened` events; if the client never sends `tx_hash`, the backend still creates `UserCard` rows when it sees the mint, and the user will see the cards on the next profile or opening request.

### Tournament registration (on-chain)

1. **Validate deck** – Client sends `POST /api/tournaments/{id}/validate-deck` with `deck_composition` (list of `user_card_id`). Backend validates the deck (5 cards, weight limit, no duplicate tokens, etc.) and returns `deck_hash` plus `chain_id` and `contract_address` for the frontend.
2. **On-chain commit** – User calls `TournamentRegistry.registerDeck(tournamentId, deckHash)` on Avalanche (same `tournamentId` as in the API, same `deckHash` from the validate response).
3. **Backend register** – Client sends `POST /api/tournaments/{id}/register` with the same `deck_composition` and `tx_hash`. Backend verifies the transaction (correct function, user, and `deck_hash`), then creates `TournamentDeck` in PostgreSQL and locks the cards for the tournament. Unregistration: user calls `unregisterDeck(tournamentId)`, then `POST /api/tournaments/{id}/unregister` with `tx_hash`.

Backend requires `TOURNAMENT_CONTRACT_ADDRESS` and `WEB3_PROVIDER_URL` in `.env` for verification.

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

## Running the backend locally

For a quick local run (e.g. to try the API or run scripts):

1. Clone the repo and create a `.env` file (see required vars in `config.py`; at minimum: `POSTGRES_*`, `DATABASE_URL`, `SECRET_KEY`).
2. From the project root:

```bash
docker-compose up -d postgres
# Apply migrations, then:
docker-compose up backend
```

API will be at `http://localhost:8000` (or the port set in `.env`). Contract deployment and production setup are not covered here.

---

## Monitoring and health checks

The `monitoring/` folder contains a Prometheus + Grafana stack for PostgreSQL metrics (see `monitoring/README.md` for details).

Additional health checks keep on-chain and DB inventories in sync:

- `logs/pack_health.log` – warnings when ERC‑1155 `balanceOf` does not match the count of unopened `UserPack` records.
- `logs/card_health.log` – warnings when ERC‑721 `ownerOf` does not match `UserCard` ownership.


