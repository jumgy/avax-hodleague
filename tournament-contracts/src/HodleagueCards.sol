// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts-upgradeable/token/ERC721/ERC721Upgradeable.sol";
import "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts/utils/Strings.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";

/**
 * @title HodleagueCards
 * @notice ERC-721 NFT contract for Hodleague player cards.
 *
 * On-chain storage is minimal: each token stores only its ID and current owner.
 * All visual metadata (image, name, stats, rarity) is served by the Hodleague
 * backend API via the tokenURI mechanism.
 *
 * Access control:
     *   - MINTER_ROLE       → server hot-wallet or other system contracts.
     *   - BURNER_ROLE       → future upgrade / crafting contracts that need to burn cards.
     *   - SIGNER_ROLE       → backend signing key for mintWithSignature().
     *   - DEFAULT_ADMIN_ROLE → multisig; manages roles, SIGNER and contract upgrades.
 *
 * Upgradeability: UUPS proxy pattern (OpenZeppelin).
 */
contract HodleagueCards is
    Initializable,
    ERC721Upgradeable,
    AccessControlUpgradeable,
    UUPSUpgradeable
{
    using Strings for uint256;
    using MessageHashUtils for bytes32;
    using ECDSA for bytes32;

    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 public constant BURNER_ROLE = keccak256("BURNER_ROLE");
    bytes32 public constant SIGNER_ROLE = keccak256("SIGNER_ROLE");

    /// @notice Base URL for off-chain metadata. tokenURI returns baseURI + tokenId.
    string private _baseTokenURI;

    /// @notice Tracks which off-chain openings have already been used to mint cards.
    mapping(uint256 openingId => bool used) public used;

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /**
     * @notice Initializes the proxy. Called once at deployment.
     * @param defaultAdmin  Receives DEFAULT_ADMIN_ROLE (use multisig in production).
     * @param minter        Receives MINTER_ROLE (server hot-wallet or system contract).
     * @param baseURI       Base URL for metadata, e.g. "https://back.avax.hodleague.com/nft/cards/".
     */
    function initialize(
        address defaultAdmin,
        address minter,
        string calldata baseURI
    ) public initializer {
        __ERC721_init("Hodleague Cards", "HLCARD");
        __AccessControl_init();

        _baseTokenURI = baseURI;

        _grantRole(DEFAULT_ADMIN_ROLE, defaultAdmin);
        _grantRole(MINTER_ROLE, minter);
    }

    // ---------------------------------------------------------------
    //  Events
    // ---------------------------------------------------------------

    /**
     * @notice Emitted when cards are minted via mintWithSignature for a specific opening.
     * @param user       Recipient address.
     * @param openingId  Off-chain PackOpening.id used for this mint.
     * @param cardIds    Logical card identifiers used by backend.
     */
    event PackOpened(
        address indexed user,
        uint256 indexed openingId,
        uint256[] cardIds
    );

    // ---------------------------------------------------------------
    //  Minting & Burning
    // ---------------------------------------------------------------

    /**
     * @notice Mints a new card.
     * @param to       Recipient address.
     * @param tokenId  Unique token ID (assigned by off-chain logic).
     */
    function mint(address to, uint256 tokenId) external onlyRole(MINTER_ROLE) {
        _safeMint(to, tokenId);
    }

    /**
     * @notice Mints a batch of cards for a given pack opening using a backend signature.
     *
     * Security model:
     * - Off-chain backend generates cardIds and serverSeed for a specific openingId,
     *   signs keccak256(abi.encodePacked(user, openingId, cardIds, serverSeed, block.chainid, address(this))).
     * - User calls this function providing the same tuple and signature.
     * - Contract recovers signer and checks it has SIGNER_ROLE.
     * - Each openingId can be used only once (used[openingId] == false).
     *
     * Token IDs are derived deterministically from (openingId, index) so that backend
     * can recompute them when syncing on-chain state to the database.
     *
     * @param user        Recipient address (must equal msg.sender).
     * @param openingId   Off-chain PackOpening.id representing this pack opening.
     * @param cardIds     Logical card identifiers selected by backend.
     * @param serverSeed  Backend server seed committed before reveal.
     * @param signature   Backend signature proving authorisation.
     */
    function mintWithSignature(
        address user,
        uint256 openingId,
        uint256[] calldata cardIds,
        bytes32 serverSeed,
        bytes calldata signature
    ) external {
        require(msg.sender == user, "HodleagueCards: caller must be user");
        require(!used[openingId], "HodleagueCards: opening already used");
        require(cardIds.length > 0, "HodleagueCards: empty cardIds");

        bytes32 messageHash = keccak256(
            abi.encodePacked(
                user,
                openingId,
                cardIds,
                serverSeed,
                block.chainid,
                address(this)
            )
        );
        bytes32 ethSigned = messageHash.toEthSignedMessageHash();
        address recovered = ethSigned.recover(signature);
        require(
            hasRole(SIGNER_ROLE, recovered),
            "HodleagueCards: invalid signature"
        );

        used[openingId] = true;

        uint256 count = cardIds.length;
        for (uint256 i = 0; i < count; ) {
            // Deterministic tokenId derived from (openingId, index).
            uint256 tokenId = uint256(
                keccak256(abi.encodePacked(openingId, i))
            );
            _safeMint(user, tokenId);

            unchecked {
                ++i;
            }
        }

        emit PackOpened(user, openingId, cardIds);
    }

    /**
     * @notice Burns a card.
     *         Callable by the token owner OR any address with BURNER_ROLE
     *         (e.g. a future crafting / upgrade contract).
     * @param tokenId  Token to burn.
     */
    function burn(uint256 tokenId) external {
        require(
            ownerOf(tokenId) == msg.sender || hasRole(BURNER_ROLE, msg.sender),
            "HodleagueCards: caller is not owner or burner"
        );
        _burn(tokenId);
    }

    // ---------------------------------------------------------------
    //  Metadata
    // ---------------------------------------------------------------

    /**
     * @notice Returns the full metadata URI for a token.
     * @dev Reverts if tokenId does not exist (ownerOf check).
     */
    function tokenURI(
        uint256 tokenId
    ) public view override returns (string memory) {
        ownerOf(tokenId); // reverts for non-existent tokens
        return string.concat(_baseTokenURI, tokenId.toString());
    }

    /**
     * @notice Updates the base URI for all tokens. Admin only.
     * @param baseURI  New base URL.
     */
    function setBaseURI(
        string calldata baseURI
    ) external onlyRole(DEFAULT_ADMIN_ROLE) {
        _baseTokenURI = baseURI;
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
        override(ERC721Upgradeable, AccessControlUpgradeable)
        returns (bool)
    {
        return
            ERC721Upgradeable.supportsInterface(interfaceId) ||
            AccessControlUpgradeable.supportsInterface(interfaceId);
    }
}