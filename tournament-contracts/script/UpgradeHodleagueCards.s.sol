// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/HodleagueCards.sol";

/**
 * @title UpgradeHodleagueCards
 * @notice Upgrades the HodleagueCards proxy to a new implementation (UUPS).
 *
 * Required in tournament-contracts/.env:
 *   PRIVATE_KEY   — key of account with DEFAULT_ADMIN_ROLE on the Cards proxy
 *   CARDS_PROXY   — proxy address (same as backend CARDS_CONTRACT_ADDRESS)
 *
 * After the first upgrade that adds mintWithSignature(), grant SIGNER_ROLE to the
 * backend signer address (derived from PACK_SIGNER_PRIVATE_KEY), e.g.:
 *   cast send <CARDS_PROXY> "grantRole(bytes32,address)" $(cast keccak "SIGNER_ROLE()") <SIGNER_ADDRESS> --private-key <ADMIN_KEY>
 *
 * Fuji:
 *   forge script script/UpgradeHodleagueCards.s.sol \
 *     --rpc-url https://api.avax-test.network/ext/bc/C/rpc \
 *     --broadcast
 *
 * Mainnet:
 *   forge script script/UpgradeHodleagueCards.s.sol \
 *     --rpc-url https://api.avax.network/ext/bc/C/rpc \
 *     --broadcast
 */
contract UpgradeHodleagueCards is Script {
    function run() external {
        uint256 adminKey = vm.envUint("PRIVATE_KEY");
        address proxyAddress = vm.envAddress("CARDS_PROXY");

        console.log("Cards proxy (upgrading):", proxyAddress);

        vm.startBroadcast(adminKey);

        HodleagueCards newImpl = new HodleagueCards();
        console.log("New implementation:     ", address(newImpl));

        HodleagueCards proxy = HodleagueCards(proxyAddress);
        proxy.upgradeToAndCall(address(newImpl), "");

        vm.stopBroadcast();

        console.log("Upgrade complete.");
    }
}
