// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/HodleagueCards.sol";
import "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

/**
 * @title DeployHodleagueCards
 * @notice Deploys HodleagueCards (ERC-721) behind a UUPS proxy to Avalanche C-Chain.
 *         Use this script ONLY if you need to deploy Cards separately from Packs.
 *         For the full stack (Cards + Packs), use DeployHodleague.s.sol instead.
 *
 * Required env vars:
 *   PRIVATE_KEY  — deployer private key
 *
 * Optional env vars:
 *   DEFAULT_ADMIN — address for DEFAULT_ADMIN_ROLE (defaults to deployer)
 *   MINTER        — address for MINTER_ROLE (defaults to deployer)
 *   BASE_URI      — metadata base URL (defaults to https://api.hodleague.com/nft/cards/)
 *
 * Fuji:
 *   forge script script/DeployHodleagueCards.s.sol \
 *     --rpc-url https://api.avax-test.network/ext/bc/C/rpc \
 *     --broadcast --verify
 *
 * Mainnet:
 *   forge script script/DeployHodleagueCards.s.sol \
 *     --rpc-url https://api.avax.network/ext/bc/C/rpc \
 *     --broadcast --verify
 */
contract DeployHodleagueCards is Script {
    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        address defaultAdmin = vm.envOr("DEFAULT_ADMIN", deployer);
        address minter = vm.envOr("MINTER", deployer);
        string memory baseURI = vm.envOr(
            "BASE_URI",
            string("https://api.hodleague.com/nft/cards/")
        );

        console.log("========== Deploy HodleagueCards ==========");
        console.log("Deployer:      ", deployer);
        console.log("DEFAULT_ADMIN: ", defaultAdmin);
        console.log("MINTER:        ", minter);
        console.log("BASE_URI:      ", baseURI);
        console.log("============================================\n");

        vm.startBroadcast(deployerKey);

        // 1. Deploy implementation
        HodleagueCards implementation = new HodleagueCards();

        // 2. Deploy proxy with initializer
        bytes memory initData = abi.encodeCall(
            HodleagueCards.initialize,
            (defaultAdmin, minter, baseURI)
        );
        ERC1967Proxy proxy = new ERC1967Proxy(
            address(implementation),
            initData
        );

        vm.stopBroadcast();

        console.log("Implementation: ", address(implementation));
        console.log("Proxy:          ", address(proxy));
        console.log("\n> Set CARDS_CONTRACT_ADDRESS=%s in .env", address(proxy));
    }
}