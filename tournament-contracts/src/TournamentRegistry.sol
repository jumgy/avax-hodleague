// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title TournamentRegistry
/// @notice Stores deck registration commitments per tournament and user.
contract TournamentRegistry {
    mapping(uint256 => mapping(address => bytes32)) public registrations;

    event Registered(uint256 indexed tournamentId, address indexed user, bytes32 deckHash);
    event Unregistered(uint256 indexed tournamentId, address indexed user);

    /// @notice Registers a deck commitment for the sender in the given tournament.
    /// @param tournamentId Id of the tournament.
    /// @param deckHash Commitment hash of the deck (must be non-zero).
    function registerDeck(uint256 tournamentId, bytes32 deckHash) external {
        require(deckHash != bytes32(0), "Invalid hash");
        require(registrations[tournamentId][msg.sender] == bytes32(0), "Already registered");

        registrations[tournamentId][msg.sender] = deckHash;
        emit Registered(tournamentId, msg.sender, deckHash);
    }

    /// @notice Removes the sender's registration for the given tournament.
    /// @param tournamentId Id of the tournament.
    function unregisterDeck(uint256 tournamentId) external {
        require(registrations[tournamentId][msg.sender] != bytes32(0), "Not registered");

        registrations[tournamentId][msg.sender] = bytes32(0);
        emit Unregistered(tournamentId, msg.sender);
    }
}