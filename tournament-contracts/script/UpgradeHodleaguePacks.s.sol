// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/HodleaguePacks.sol";

/**
 * @title UpgradeHodleaguePacks
 * @notice Upgrades the HodleaguePacks proxy to a new implementation (UUPS).
 *
 * Required in tournament-contracts/.env:
 *   PRIVATE_KEY  — key of account with DEFAULT_ADMIN_ROLE on the Packs proxy
 *   PACKS_PROXY  — proxy address (same as backend PACKS_CONTRACT_ADDRESS)
 *
 * Fuji:
 *   forge script script/UpgradeHodleaguePacks.s.sol \
 *     --rpc-url https://api.avax-test.network/ext/bc/C/rpc \
 *     --broadcast
 *
 * Mainnet:
 *   forge script script/UpgradeHodleaguePacks.s.sol \
 *     --rpc-url https://api.avax.network/ext/bc/C/rpc \
 *     --broadcast
 */
contract UpgradeHodleaguePacks is Script {
    function run() external {
        uint256 adminKey = vm.envUint("PRIVATE_KEY");
        address proxyAddress = vm.envAddress("PACKS_PROXY");

        console.log("Packs proxy (upgrading):", proxyAddress);

        vm.startBroadcast(adminKey);

        HodleaguePacks newImpl = new HodleaguePacks();
        console.log("New implementation:    ", address(newImpl));

        HodleaguePacks proxy = HodleaguePacks(proxyAddress);
        proxy.upgradeToAndCall(address(newImpl), "");

        vm.stopBroadcast();

        console.log("Upgrade complete.");
    }
}
