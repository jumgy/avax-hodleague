// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts-upgradeable/token/ERC1155/ERC1155Upgradeable.sol";
import "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import {HodleagueCards} from "./HodleagueCards.sol";

/**
 * @title HodleaguePacks
 * @notice ERC-1155 contract for Hodleague card packs.
 *
 * IMPORTANT: This contract is currently not used by the backend pack-opening
 * flow. Packs now live purely off-chain in the database, and cards are minted
 * directly via HodleagueCards.mintWithSignature. HodleaguePacks is kept in the
 * codebase as a potential future building block for on-chain packs (buy/claim),
 * but is not wired into the current system.
 *
 * Each pack type maps to an ERC-1155 token ID (DB packTypeId 1 → tokenId 1).
 * Packs are soulbound: transfers between wallets are blocked; only mint and burn
 * are allowed.
 *
 * Pack lifecycle (when used):
 *   1. Acquire  — via mint() (server grant), buyPack() (pay AVAX), or claimPack() (signed claim).
 *   2. Open     — two-step commit-reveal: commitOpen() burns the pack; then backend signs
 *                 card drops; user calls revealOpen() to mint ERC-721 cards.
 *
 * Access control:
 *   - MINTER_ROLE         → server hot-wallet (grants packs).
 *   - SIGNER_ROLE         → backend signing key (authorises open and claim operations).
 *   - DEFAULT_ADMIN_ROLE  → multisig; manages roles, prices, upgrades, withdrawals.
 *
 * Upgradeability: UUPS proxy pattern (OpenZeppelin).
 */
contract HodleaguePacks is
    Initializable,
    ERC1155Upgradeable,
    AccessControlUpgradeable,
    UUPSUpgradeable
{
    using MessageHashUtils for bytes32;

    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 public constant SIGNER_ROLE = keccak256("SIGNER_ROLE");

    /// @notice Reference to the HodleagueCards ERC-721 contract.
    HodleagueCards public cards;

    /// @notice Auto-incrementing counter for unique ERC-721 card token IDs.
    uint256 private _nextCardTokenId;

    /// @notice Native-token price per pack type in wei. 0 means not for sale.
    mapping(uint256 packTypeId => uint256 price) public packPrices;

    /// @notice Tracks used claim IDs to prevent replay of claimPack signatures.
    mapping(bytes32 claimId => bool used) public usedClaimIds;

    /// @notice Tracks used reveal message hashes to prevent signature replay.
    mapping(bytes32 messageHash => bool used) public usedRevealHashes;

    /// @notice Commit for two-step open: user burned a pack, awaiting reveal.
    struct Commit {
        address user;
        uint256 packTypeId;
        uint256 timestamp;
    }

    /// @notice Next commit ID (incremented on each commitOpen).
    uint256 private _nextCommitId;

    /// @notice Active commits by ID. Cleared when revealOpen is called.
    mapping(uint256 commitId => Commit) public commits;

    // ---------------------------------------------------------------
    //  Events
    // ---------------------------------------------------------------

    /// @notice Emitted when user commits to opening a pack (pack burned).
    event PackCommitted(
        address indexed user,
        uint256 indexed packTypeId,
        uint256 indexed commitId
    );

    /// @notice Emitted when reveal is executed and cards are minted.
    event PackRevealed(
        address indexed user,
        uint256 indexed commitId,
        uint256[] nftTokenIds,
        uint256[] cardIds,
        bytes32 serverSeed
    );

    /// @notice Emitted once per openPack call after all cards are minted (deprecated; use PackRevealed).
    event PackOpened(
        address indexed user,
        uint256 indexed packTypeId,
        uint256[] nftTokenIds,
        uint256[] cardIds,
        bytes32 serverSeed
    );

    /// @notice Emitted for each individual card minted during pack opening.
    event CardMinted(
        address indexed to,
        uint256 indexed nftTokenId,
        uint256 cardId
    );

    /// @notice Emitted when a pack is purchased via buyPack.
    event PackPurchased(
        address indexed buyer,
        uint256 indexed packTypeId,
        uint256 amount,
        uint256 totalPaid
    );

    /// @notice Emitted when a pack is claimed via claimPack.
    event PackClaimed(
        address indexed user,
        bytes32 indexed claimId,
        uint256 packTypeId,
        uint256 amount
    );

    // ---------------------------------------------------------------
    //  Initializer
    // ---------------------------------------------------------------

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /**
     * @notice Initializes the proxy. Called once at deployment.
     * @param defaultAdmin  Receives DEFAULT_ADMIN_ROLE (use multisig in production).
     * @param minter        Receives MINTER_ROLE (server hot-wallet).
     * @param signer        Receives SIGNER_ROLE (backend signing key).
     * @param cards_        Deployed HodleagueCards contract. This contract must hold
     *                      MINTER_ROLE on HodleagueCards.
     */
    function initialize(
        address defaultAdmin,
        address minter,
        address signer,
        address cards_
    ) public initializer {
        __ERC1155_init("");
        __AccessControl_init();

        cards = HodleagueCards(cards_);

        _grantRole(DEFAULT_ADMIN_ROLE, defaultAdmin);
        _grantRole(MINTER_ROLE, minter);
        _grantRole(SIGNER_ROLE, signer);
    }

    // ---------------------------------------------------------------
    //  Acquiring Packs
    // ---------------------------------------------------------------

    /**
     * @notice Mints packs to an address. Server-initiated grant.
     * @param to          Recipient wallet.
     * @param packTypeId  Pack type (maps to ERC-1155 token ID).
     * @param amount      Number of packs to mint.
     */
    function mint(
        address to,
        uint256 packTypeId,
        uint256 amount
    ) external onlyRole(MINTER_ROLE) {
        _mint(to, packTypeId, amount, "");
    }

    /**
     * @notice Purchases packs by sending native token (AVAX). User pays gas.
     *         Reverts if pack type has no price set or payment is insufficient.
     *         Excess payment is refunded automatically.
     * @param packTypeId  Pack type to buy.
     * @param amount      Number of packs (capped at 50 per transaction).
     */
    function buyPack(uint256 packTypeId, uint256 amount) external payable {
        require(amount > 0 && amount <= 50, "HodleaguePacks: invalid amount");

        uint256 price = packPrices[packTypeId];
        require(price > 0, "HodleaguePacks: pack not for sale");

        uint256 total = price * amount;
        require(msg.value >= total, "HodleaguePacks: insufficient payment");

        _mint(msg.sender, packTypeId, amount, "");

        emit PackPurchased(msg.sender, packTypeId, amount, total);

        if (msg.value > total) {
            (bool ok, ) = msg.sender.call{value: msg.value - total}("");
            require(ok, "HodleaguePacks: refund failed");
        }
    }

    /**
     * @notice Claims packs using a backend-signed authorisation. User pays gas.
     *         Each claimId can only be used once.
     * @param claimId     Unique claim identifier generated by the backend.
     * @param packTypeId  Pack type to claim.
     * @param amount      Number of packs.
     * @param signature   Backend signature over keccak256(abi.encode(caller, claimId, packTypeId, amount)).
     */
    function claimPack(
        bytes32 claimId,
        uint256 packTypeId,
        uint256 amount,
        bytes calldata signature
    ) external {
        require(!usedClaimIds[claimId], "HodleaguePacks: claim already used");

        bytes32 messageHash = keccak256(
            abi.encode(msg.sender, claimId, packTypeId, amount)
        );
        bytes32 digest = messageHash.toEthSignedMessageHash();
        address recovered = ECDSA.recover(digest, signature);
        require(
            hasRole(SIGNER_ROLE, recovered),
            "HodleaguePacks: invalid signature"
        );

        usedClaimIds[claimId] = true;
        _mint(msg.sender, packTypeId, amount, "");

        emit PackClaimed(msg.sender, claimId, packTypeId, amount);
    }

    // ---------------------------------------------------------------
    //  Opening Packs (commit-reveal)
    // ---------------------------------------------------------------

    /**
     * @notice Step 1: Commit to opening a pack. Burns 1 pack and stores a commit.
     *
     * @param packTypeId  Pack type token ID to burn.
     * @return commitId   Id of the created commit (also in PackCommitted event).
     */
    function commitOpen(uint256 packTypeId) external returns (uint256 commitId) {
        address user = msg.sender;
        require(
            balanceOf(user, packTypeId) >= 1,
            "HodleaguePacks: insufficient pack balance"
        );

        _burn(user, packTypeId, 1);

        commitId = ++_nextCommitId;
        commits[commitId] = Commit({
            user: user,
            packTypeId: packTypeId,
            timestamp: block.timestamp
        });

        emit PackCommitted(user, packTypeId, commitId);
    }

    /**
     * @notice Step 2: Reveal and mint cards for a prior commit.
     * @param commitId   Id from PackCommitted event.
     * @param cardIds    Card-type IDs from backend. Length = number of ERC-721 to mint.
     * @param serverSeed Server seed (32 bytes). Published in PackRevealed.
     * @param signature  Backend signature over keccak256(abi.encode(user, commitId, cardIds, serverSeed)).
     */
    function revealOpen(
        uint256 commitId,
        uint256[] calldata cardIds,
        bytes32 serverSeed,
        bytes calldata signature
    ) external {
        Commit storage c = commits[commitId];
        require(c.user != address(0), "HodleaguePacks: commit not found");
        require(c.user == msg.sender, "HodleaguePacks: not your commit");

        address user = msg.sender;

        bytes32 messageHash = keccak256(
            abi.encode(user, commitId, cardIds, serverSeed)
        );
        require(
            !usedRevealHashes[messageHash],
            "HodleaguePacks: signature already used"
        );

        bytes32 digest = messageHash.toEthSignedMessageHash();
        address recovered = ECDSA.recover(digest, signature);
        require(
            hasRole(SIGNER_ROLE, recovered),
            "HodleaguePacks: invalid signature"
        );

        usedRevealHashes[messageHash] = true;

        uint256 count = cardIds.length;
        uint256[] memory nftTokenIds = new uint256[](count);
        uint256 startId = _nextCardTokenId;

        for (uint256 i = 0; i < count; ) {
            uint256 nftTokenId = startId + i;
            cards.mint(user, nftTokenId);
            nftTokenIds[i] = nftTokenId;

            emit CardMinted(user, nftTokenId, cardIds[i]);

            unchecked {
                ++i;
            }
        }

        _nextCardTokenId = startId + count;

        delete commits[commitId];

        emit PackRevealed(user, commitId, nftTokenIds, cardIds, serverSeed);
    }

    /**
     * @notice Relayer reveal: SIGNER can reveal on behalf of a user for abandoned commits.
     *         Same checks as revealOpen but caller is SIGNER; cards mint to commit.user.
     * @param commitId   Id from PackCommitted.
     * @param cardIds    Card-type IDs (must match backend-signed payload).
     * @param serverSeed Server seed from backend.
     * @param signature  Backend signature over keccak256(abi.encode(commit.user, commitId, cardIds, serverSeed)).
     */
    function relayerRevealOpen(
        uint256 commitId,
        uint256[] calldata cardIds,
        bytes32 serverSeed,
        bytes calldata signature
    ) external onlyRole(SIGNER_ROLE) {
        Commit storage c = commits[commitId];
        require(c.user != address(0), "HodleaguePacks: commit not found");

        address user = c.user;

        bytes32 messageHash = keccak256(
            abi.encode(user, commitId, cardIds, serverSeed)
        );
        require(
            !usedRevealHashes[messageHash],
            "HodleaguePacks: signature already used"
        );

        bytes32 digest = messageHash.toEthSignedMessageHash();
        address recovered = ECDSA.recover(digest, signature);
        require(
            hasRole(SIGNER_ROLE, recovered),
            "HodleaguePacks: invalid signature"
        );

        usedRevealHashes[messageHash] = true;

        uint256 count = cardIds.length;
        uint256[] memory nftTokenIds = new uint256[](count);
        uint256 startId = _nextCardTokenId;

        for (uint256 i = 0; i < count; ) {
            uint256 nftTokenId = startId + i;
            cards.mint(user, nftTokenId);
            nftTokenIds[i] = nftTokenId;

            emit CardMinted(user, nftTokenId, cardIds[i]);

            unchecked {
                ++i;
            }
        }

        _nextCardTokenId = startId + count;

        delete commits[commitId];

        emit PackRevealed(user, commitId, nftTokenIds, cardIds, serverSeed);
    }

    // ---------------------------------------------------------------
    //  Admin
    // ---------------------------------------------------------------

    /**
     * @notice Sets the native-token price for a pack type. Admin only.
     * @param packTypeId  Pack type ID.
     * @param price       Price in wei. Set to 0 to disable direct purchase.
     */
    function setPackPrice(
        uint256 packTypeId,
        uint256 price
    ) external onlyRole(DEFAULT_ADMIN_ROLE) {
        packPrices[packTypeId] = price;
    }

    /**
     * @notice Withdraws the contract's native-token balance. Admin only.
     * @param to  Recipient address (e.g. treasury multisig).
     */
    function withdraw(
        address payable to
    ) external onlyRole(DEFAULT_ADMIN_ROLE) {
        (bool ok, ) = to.call{value: address(this).balance}("");
        require(ok, "HodleaguePacks: withdraw failed");
    }

    /**
     * @notice Returns the next ERC-721 token ID that will be assigned.
     */
    function nextCardTokenId() external view returns (uint256) {
        return _nextCardTokenId;
    }

    /**
     * @notice Returns commit data for a given commitId. Used by backend to verify commit before signing.
     * @return user      Address that committed.
     * @return packTypeId Pack type that was burned.
     * @return timestamp Block timestamp when commit was made.
     */
    function getCommit(uint256 commitId)
        external
        view
        returns (address user, uint256 packTypeId, uint256 timestamp)
    {
        Commit storage c = commits[commitId];
        return (c.user, c.packTypeId, c.timestamp);
    }

    // ---------------------------------------------------------------
    //  Soulbound Enforcement
    // ---------------------------------------------------------------

    /**
     * @dev Blocks wallet-to-wallet transfers. Only mint (from == address(0))
     *      and burn (to == address(0)) are permitted.
     */
    function _update(
        address from,
        address to,
        uint256[] memory ids,
        uint256[] memory values
    ) internal override {
        if (from != address(0) && to != address(0)) {
            revert("HodleaguePacks: packs are soulbound");
        }
        super._update(from, to, ids, values);
    }

    // ---------------------------------------------------------------
    //  Internals & Overrides
    // ---------------------------------------------------------------

    /// @dev Restricts UUPS upgrades to DEFAULT_ADMIN_ROLE.
    function _authorizeUpgrade(
        address /* newImplementation */
    ) internal override onlyRole(DEFAULT_ADMIN_ROLE) {}

    /// @dev Required override for dual-inheritance of supportsInterface.
    function supportsInterface(
        bytes4 interfaceId
    )
        public
        view
        override(ERC1155Upgradeable, AccessControlUpgradeable)
        returns (bool)
    {
        return
            ERC1155Upgradeable.supportsInterface(interfaceId) ||
            AccessControlUpgradeable.supportsInterface(interfaceId);
    }
}

