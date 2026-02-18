// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/TournamentRegistry.sol";

/**
 * Deploy TournamentRegistry to Avalanche C-Chain.
 * Run: forge script script/DeployTournamentAvalanche.s.sol --rpc-url avalanche --broadcast --private-key $PRIVATE_KEY
 * Or with foundry.toml RPC: --rpc-url https://api.avax.network/ext/bc/C/rpc
 */
contract DeployTournamentAvalancheScript is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerPrivateKey);

        console.log("==================================");
        console.log("Deploying to Avalanche C-Chain");
        console.log("Deployer:", deployer);
        console.log("==================================\n");

        vm.startBroadcast(deployerPrivateKey);

        TournamentRegistry registry = new TournamentRegistry();

        console.log("TournamentRegistry deployed at:", address(registry));

        vm.stopBroadcast();

        console.log("\n==================================");
        console.log("DEPLOYMENT COMPLETE (Avalanche C-Chain)");
        console.log("==================================");
        console.log("Contract:", address(registry));
        console.log("\nSet TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE in backend .env to this address.");
    }
}
