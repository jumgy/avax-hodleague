## Hodleague Tournament Contracts

This folder contains the Solidity contracts and Foundry project used by Fantasy Crypto Tournament.

Current production setup:
- `HodleagueCards.sol` – ERC‑721 cards, used in production (mintWithSignature + PackOpened).
- `TournamentRegistry.sol` – stores deck registration commitments per tournament; backend verifies tx and writes to DB.
- `HodleaguePacks.sol` – legacy ERC‑1155 packs, kept for reference and tests only (not used by the backend flow anymore).

Helper scripts:
- Foundry scripts under `script/` for local testing and experimental deployments.

## HodleagueCards (ERC‑721)

`HodleagueCards` is an upgradeable ERC‑721 contract:
- Stores minimal state: token owner and `tokenId`.
- All metadata is served off-chain by the backend:
  - `baseTokenURI` is set to `NFT_METADATA_BASE_URL` from the API (`/nft/cards/{id}`).
  - `tokenURI(tokenId)` = `baseURI + tokenId`.
- Access control:
  - `DEFAULT_ADMIN_ROLE` – upgrades, base URI changes, role management.
  - `MINTER_ROLE` – backend signer or hot-wallet for direct mints.
  - `BURNER_ROLE` – reserved for future crafting / upgrade flows.

In the current architecture packs are off-chain only. The backend signs `mintWithSignature` payloads and listens for the `PackOpened` event to create `UserCard` records.

## TournamentRegistry

`TournamentRegistry` is a simple contract that stores one deck commitment per user per tournament on-chain.

- **Purpose:** Commit to a deck (by hash) so that the deck cannot be changed after the registration window closes. The backend generates the hash from `(tournament_id, user_id, sorted deck_composition)` and returns it from `POST /api/tournaments/{id}/validate-deck`.
- **Functions:**
  - `registerDeck(uint256 tournamentId, bytes32 deckHash)` – caller commits their deck hash for the given tournament. Reverts if already registered or hash is zero.
  - `unregisterDeck(uint256 tournamentId)` – removes the caller’s registration for the tournament.
- **Events:** `Registered(tournamentId, user, deckHash)`, `Unregistered(tournamentId, user)`.
- **Backend:** The API expects the user to call `registerDeck` (or `unregisterDeck`) on this contract, then send the transaction hash to `POST /api/tournaments/{id}/register` (or `.../unregister`). The backend verifies the tx and then writes or updates `TournamentDeck` in PostgreSQL.

## HodleaguePacks (legacy ERC‑1155)

`HodleaguePacks` is an upgradeable ERC‑1155 contract that originally implemented on-chain packs with a commit‑reveal flow.

In the current version of the game:

- Packs are managed purely off-chain in PostgreSQL (`UserPack`, `PackOpening`).
- Only `HodleagueCards` is used in the live backend flow.
- `HodleaguePacks` and its tests are kept for historical reference and local experiments, but the production API does not call this contract.

## Using this project

This is a standard Foundry project. You can use your own deployment and upgrade scripts or reuse the ones under `script/` for local testing and staging environments.

## Foundry quick start

From `tournament-contracts/`:

```bash
forge build
forge test
```

Core tests:
- `test/HodleagueCards.t.sol` – ERC‑721 behaviour, access control, PackOpened events.
- `test/HodleaguePacks.t.sol` – legacy commit‑reveal logic and UUPS upgrades (not used in production).

