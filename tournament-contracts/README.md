## Hodleague Tournament Contracts

This folder contains the Solidity contracts and Foundry project used by Fantasy Crypto Tournament.

Current production setup:
- `HodleagueCards.sol` – ERC‑721 cards, used in production (mintWithSignature + PackOpened).
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

