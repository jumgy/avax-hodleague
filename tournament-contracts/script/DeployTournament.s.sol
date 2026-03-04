// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/TournamentRegistry.sol";

contract DeployTournamentScript is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerPrivateKey);
        
        console.log("==================================");
        console.log("Deploying to Abstract Mainnet");
        console.log("Deployer:", deployer);
        console.log("==================================\n");
        
        vm.startBroadcast(deployerPrivateKey);
        
        TournamentRegistry registry = new TournamentRegistry();
        
        console.log("TournamentRegistry deployed at:", address(registry));
        
        vm.stopBroadcast();
        
        console.log("\n==================================");
        console.log("DEPLOYMENT COMPLETE");
        console.log("==================================");
        console.log("Contract:", address(registry));
        console.log("\nSave this address to your backend config!");
    }
}