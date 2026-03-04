// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/HodleagueCards.sol";
import "../src/HodleaguePacks.sol";
import "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

/**
 * @title DeployHodleague
 * @notice Deploys the full Hodleague NFT stack:
 *           1. HodleagueCards  (ERC-721)  — UUPS proxy
 *           2. HodleaguePacks  (ERC-1155) — UUPS proxy
 *         Then grants HodleaguePacks the MINTER_ROLE on HodleagueCards
 *         so that openPack() can mint cards.
 *
 * Required env vars:
 *   PRIVATE_KEY  — deployer private key (deployer must be DEFAULT_ADMIN or same address)
 *
 * Optional env vars:
 *   DEFAULT_ADMIN — DEFAULT_ADMIN_ROLE recipient (defaults to deployer)
 *   MINTER        — MINTER_ROLE on Packs for server grants (defaults to deployer)
 *   SIGNER        — SIGNER_ROLE on Packs for openPack/claimPack signatures (defaults to deployer)
 *   BASE_URI      — Cards metadata base URL (defaults to https://api.hodleague.com/nft/cards/)
 *
 * Fuji:
 *   forge script script/DeployHodleague.s.sol \
 *     --rpc-url https://api.avax-test.network/ext/bc/C/rpc \
 *     --broadcast --verify
 *
 * Mainnet:
 *   forge script script/DeployHodleague.s.sol \
 *     --rpc-url https://api.avax.network/ext/bc/C/rpc \
 *     --broadcast --verify
 */
contract DeployHodleague is Script {
    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        address defaultAdmin = vm.envOr("DEFAULT_ADMIN", deployer);
        address minter = vm.envOr("MINTER", deployer);
        address signerAddr = vm.envOr("SIGNER", deployer);
        string memory baseURI = vm.envOr(
            "BASE_URI",
            string("https://api.hodleague.com/nft/cards/")
        );

        console.log("========== Deploy Hodleague Stack ==========");
        console.log("Deployer:      ", deployer);
        console.log("DEFAULT_ADMIN: ", defaultAdmin);
        console.log("MINTER:        ", minter);
        console.log("SIGNER:        ", signerAddr);
        console.log("BASE_URI:      ", baseURI);
        console.log("=============================================\n");

        vm.startBroadcast(deployerKey);

        // ----- 1. HodleagueCards (ERC-721) behind UUPS proxy -----
        HodleagueCards cardsImpl = new HodleagueCards();
        bytes memory cardsInit = abi.encodeCall(
            HodleagueCards.initialize,
            (
                defaultAdmin,
                address(0), // MINTER granted to Packs contract below
                baseURI
            )
        );
        ERC1967Proxy cardsProxy = new ERC1967Proxy(
            address(cardsImpl),
            cardsInit
        );
        HodleagueCards cards = HodleagueCards(address(cardsProxy));

        // ----- 2. HodleaguePacks (ERC-1155) behind UUPS proxy -----
        HodleaguePacks packsImpl = new HodleaguePacks();
        bytes memory packsInit = abi.encodeCall(
            HodleaguePacks.initialize,
            (defaultAdmin, minter, signerAddr, address(cards))
        );
        ERC1967Proxy packsProxy = new ERC1967Proxy(
            address(packsImpl),
            packsInit
        );
        HodleaguePacks packs = HodleaguePacks(address(packsProxy));

        // ----- 3. Cross-contract permissions -----
        // Packs contract needs MINTER_ROLE on Cards to mint cards during openPack
        cards.grantRole(cards.MINTER_ROLE(), address(packs));

        // Optionally grant MINTER on Cards to hot-wallet for direct mints
        if (minter != address(0)) {
            cards.grantRole(cards.MINTER_ROLE(), minter);
        }

        vm.stopBroadcast();

        console.log("--- HodleagueCards (ERC-721) ---");
        console.log("Implementation: ", address(cardsImpl));
        console.log("Proxy:          ", address(cards));

        console.log("\n--- HodleaguePacks (ERC-1155) ---");
        console.log("Implementation: ", address(packsImpl));
        console.log("Proxy:          ", address(packs));

        console.log("\n--- Roles granted ---");
        console.log("Cards MINTER_ROLE -> Packs contract: ", address(packs));
        console.log("Cards MINTER_ROLE -> hot-wallet:     ", minter);
        console.log("Packs MINTER_ROLE -> hot-wallet:     ", minter);
        console.log("Packs SIGNER_ROLE -> signer:         ", signerAddr);

        console.log("\n> Add to backend .env:");
        console.log(">   CARDS_CONTRACT_ADDRESS=%s", address(cards));
        console.log(">   PACKS_CONTRACT_ADDRESS=%s", address(packs));
    }
}