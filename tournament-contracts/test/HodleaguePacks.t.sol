// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/HodleagueCards.sol";
import "../src/HodleaguePacks.sol";
import "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";

contract HodleaguePacksTest is Test {
    using MessageHashUtils for bytes32;

    HodleagueCards public cards;
    HodleaguePacks public packs;

    address public admin;
    address public minter;
    address public signer;
    address public user;
    address public user2;
    uint256 public signerKey;

    // Mirror events from contracts for expectEmit
    event PackCommitted(address indexed user, uint256 indexed packTypeId, uint256 indexed commitId);
    event PackRevealed(
        address indexed user,
        uint256 indexed commitId,
        uint256[] nftTokenIds,
        uint256[] cardIds,
        bytes32 serverSeed
    );
    event CardMinted(address indexed to, uint256 indexed nftTokenId, uint256 cardId);
    event PackPurchased(address indexed buyer, uint256 indexed packTypeId, uint256 amount, uint256 totalPaid);
    event PackClaimed(address indexed user, bytes32 indexed claimId, uint256 packTypeId, uint256 amount);

    function setUp() public {
        admin = address(this);
        minter = vm.addr(2);
        signerKey = 3;
        signer = vm.addr(signerKey);
        user = vm.addr(4);
        user2 = vm.addr(5);

        // Deploy HodleagueCards behind proxy
        HodleagueCards cardsImpl = new HodleagueCards();
        bytes memory cardsInit = abi.encodeCall(
            HodleagueCards.initialize,
            (admin, address(0), "https://api.hodleague.com/nft/cards/")
        );
        ERC1967Proxy cardsProxy = new ERC1967Proxy(address(cardsImpl), cardsInit);
        cards = HodleagueCards(address(cardsProxy));

        // Deploy HodleaguePacks behind proxy
        HodleaguePacks packsImpl = new HodleaguePacks();
        bytes memory packsInit = abi.encodeCall(
            HodleaguePacks.initialize,
            (admin, minter, signer, address(cards))
        );
        ERC1967Proxy packsProxy = new ERC1967Proxy(address(packsImpl), packsInit);
        packs = HodleaguePacks(address(packsProxy));

        // Grant Packs contract MINTER_ROLE on Cards
        cards.grantRole(cards.MINTER_ROLE(), address(packs));
    }

    // ---------------------------------------------------------------
    //  Helpers
    // ---------------------------------------------------------------

    /// @dev Sign for revealOpen (two-step: user, commitId, cardIds, serverSeed).
    function _signRevealOpen(
        address _user,
        uint256 commitId,
        uint256[] memory cardIds,
        bytes32 serverSeed
    ) internal view returns (bytes memory) {
        bytes32 messageHash = keccak256(abi.encode(_user, commitId, cardIds, serverSeed));
        bytes32 digest = messageHash.toEthSignedMessageHash();
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(signerKey, digest);
        return abi.encodePacked(r, s, v);
    }

    function _signClaim(
        address _user,
        bytes32 claimId,
        uint256 packTypeId,
        uint256 amount
    ) internal view returns (bytes memory) {
        bytes32 messageHash = keccak256(abi.encode(_user, claimId, packTypeId, amount));
        bytes32 digest = messageHash.toEthSignedMessageHash();
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(signerKey, digest);
        return abi.encodePacked(r, s, v);
    }

    function _signRevealWithKey(
        uint256 key,
        address _user,
        uint256 commitId,
        uint256[] memory cardIds,
        bytes32 serverSeed
    ) internal view returns (bytes memory) {
        bytes32 messageHash = keccak256(abi.encode(_user, commitId, cardIds, serverSeed));
        bytes32 digest = messageHash.toEthSignedMessageHash();
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, digest);
        return abi.encodePacked(r, s, v);
    }

    // ---------------------------------------------------------------
    //  Minting Packs (server grant)
    // ---------------------------------------------------------------

    function test_MinterCanMintPacks() public {
        vm.prank(minter);
        packs.mint(user, 1, 3);

        assertEq(packs.balanceOf(user, 1), 3);
    }

    function test_NonMinterCannotMintPacks() public {
        vm.prank(user);
        vm.expectRevert();
        packs.mint(user, 1, 1);
    }

    function test_MintMultiplePackTypes() public {
        vm.startPrank(minter);
        packs.mint(user, 1, 2);
        packs.mint(user, 2, 5);
        packs.mint(user, 3, 1);
        vm.stopPrank();

        assertEq(packs.balanceOf(user, 1), 2);
        assertEq(packs.balanceOf(user, 2), 5);
        assertEq(packs.balanceOf(user, 3), 1);
    }

    // ---------------------------------------------------------------
    //  Soulbound
    // ---------------------------------------------------------------

    function test_TransferReverts() public {
        vm.prank(minter);
        packs.mint(user, 1, 1);

        vm.prank(user);
        vm.expectRevert("HodleaguePacks: packs are soulbound");
        packs.safeTransferFrom(user, user2, 1, 1, "");
    }

    function test_BatchTransferReverts() public {
        vm.prank(minter);
        packs.mint(user, 1, 1);

        uint256[] memory ids = new uint256[](1);
        ids[0] = 1;
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = 1;

        vm.prank(user);
        vm.expectRevert("HodleaguePacks: packs are soulbound");
        packs.safeBatchTransferFrom(user, user2, ids, amounts, "");
    }

    // ---------------------------------------------------------------
    //  Opening Packs (two-step commit-reveal)
    // ---------------------------------------------------------------

    function test_CommitOpenBurnsPackAndRevealMintsCards() public {
        vm.prank(minter);
        packs.mint(user, 1, 1);

        uint256 commitId;
        vm.prank(user);
        commitId = packs.commitOpen(1);

        assertEq(commitId, 1);
        assertEq(packs.balanceOf(user, 1), 0);

        uint256[] memory cardIds = new uint256[](3);
        cardIds[0] = 101;
        cardIds[1] = 202;
        cardIds[2] = 303;
        bytes32 serverSeed = keccak256("test-seed-1");
        bytes memory sig = _signRevealOpen(user, commitId, cardIds, serverSeed);

        vm.prank(user);
        packs.revealOpen(commitId, cardIds, serverSeed, sig);

        assertEq(cards.balanceOf(user), 3);
        assertEq(cards.ownerOf(0), user);
        assertEq(cards.ownerOf(1), user);
        assertEq(cards.ownerOf(2), user);
        assertEq(packs.nextCardTokenId(), 3);
    }

    function test_RevealOpenEmitsEvents() public {
        vm.prank(minter);
        packs.mint(user, 1, 1);

        vm.prank(user);
        uint256 commitId = packs.commitOpen(1);

        uint256[] memory cardIds = new uint256[](2);
        cardIds[0] = 50;
        cardIds[1] = 75;
        bytes32 serverSeed = keccak256("event-seed");
        bytes memory sig = _signRevealOpen(user, commitId, cardIds, serverSeed);

        vm.expectEmit(true, true, false, true, address(packs));
        emit CardMinted(user, 0, 50);

        vm.expectEmit(true, true, false, true, address(packs));
        emit CardMinted(user, 1, 75);

        uint256[] memory expectedNftIds = new uint256[](2);
        expectedNftIds[0] = 0;
        expectedNftIds[1] = 1;

        vm.expectEmit(true, true, false, true, address(packs));
        emit PackRevealed(user, commitId, expectedNftIds, cardIds, serverSeed);

        vm.prank(user);
        packs.revealOpen(commitId, cardIds, serverSeed, sig);
    }

    function test_RevealOpenInvalidSignatureReverts() public {
        vm.prank(minter);
        packs.mint(user, 1, 1);

        vm.prank(user);
        uint256 commitId = packs.commitOpen(1);

        uint256[] memory cardIds = new uint256[](1);
        cardIds[0] = 5;
        bytes32 serverSeed = keccak256("seed");
        bytes memory sig = _signRevealWithKey(999, user, commitId, cardIds, serverSeed);

        vm.prank(user);
        vm.expectRevert("HodleaguePacks: invalid signature");
        packs.revealOpen(commitId, cardIds, serverSeed, sig);
    }

    function test_RevealOpenWrongUserReverts() public {
        vm.prank(minter);
        packs.mint(user, 1, 1);

        vm.prank(user);
        uint256 commitId = packs.commitOpen(1);

        uint256[] memory cardIds = new uint256[](1);
        cardIds[0] = 5;
        bytes32 serverSeed = keccak256("seed");
        bytes memory sig = _signRevealOpen(user, commitId, cardIds, serverSeed);

        vm.prank(user2);
        vm.expectRevert("HodleaguePacks: not your commit");
        packs.revealOpen(commitId, cardIds, serverSeed, sig);
    }

    function test_CommitOpenWithoutPackReverts() public {
        vm.prank(user);
        vm.expectRevert("HodleaguePacks: insufficient pack balance");
        packs.commitOpen(1);
    }

    function test_RevealOpenDoubleRevealReverts() public {
        vm.prank(minter);
        packs.mint(user, 1, 1);

        vm.prank(user);
        uint256 commitId = packs.commitOpen(1);

        uint256[] memory cardIds = new uint256[](1);
        cardIds[0] = 5;
        bytes32 serverSeed = keccak256("seed");
        bytes memory sig = _signRevealOpen(user, commitId, cardIds, serverSeed);

        vm.prank(user);
        packs.revealOpen(commitId, cardIds, serverSeed, sig);

        vm.prank(user);
        vm.expectRevert("HodleaguePacks: commit not found");
        packs.revealOpen(commitId, cardIds, serverSeed, sig);
    }

    function test_OpenMultiplePacksSequentially() public {
        vm.prank(minter);
        packs.mint(user, 1, 2);

        vm.prank(user);
        uint256 commitId1 = packs.commitOpen(1);

        uint256[] memory cardIds1 = new uint256[](2);
        cardIds1[0] = 10;
        cardIds1[1] = 20;
        bytes32 seed1 = keccak256("seed-1");
        bytes memory sig1 = _signRevealOpen(user, commitId1, cardIds1, seed1);

        vm.prank(user);
        packs.revealOpen(commitId1, cardIds1, seed1, sig1);

        vm.prank(user);
        uint256 commitId2 = packs.commitOpen(1);

        uint256[] memory cardIds2 = new uint256[](3);
        cardIds2[0] = 30;
        cardIds2[1] = 40;
        cardIds2[2] = 50;
        bytes32 seed2 = keccak256("seed-2");
        bytes memory sig2 = _signRevealOpen(user, commitId2, cardIds2, seed2);

        vm.prank(user);
        packs.revealOpen(commitId2, cardIds2, seed2, sig2);

        assertEq(packs.balanceOf(user, 1), 0);
        assertEq(cards.balanceOf(user), 5);
        assertEq(cards.ownerOf(0), user);
        assertEq(cards.ownerOf(4), user);
        assertEq(packs.nextCardTokenId(), 5);
    }

    function test_GetCommitReturnsData() public {
        vm.prank(minter);
        packs.mint(user, 1, 1);

        vm.prank(user);
        uint256 commitId = packs.commitOpen(1);

        (address cUser, uint256 packTypeId, uint256 ts) = packs.getCommit(commitId);
        assertEq(cUser, user);
        assertEq(packTypeId, 1);
        assertEq(ts, block.timestamp);
    }

    function test_RelayerRevealOpenMintsToCommitUser() public {
        vm.prank(minter);
        packs.mint(user, 1, 1);

        vm.prank(user);
        uint256 commitId = packs.commitOpen(1);

        uint256[] memory cardIds = new uint256[](2);
        cardIds[0] = 10;
        cardIds[1] = 20;
        bytes32 serverSeed = keccak256("relayer-seed");
        bytes memory sig = _signRevealOpen(user, commitId, cardIds, serverSeed);

        vm.prank(signer);
        packs.relayerRevealOpen(commitId, cardIds, serverSeed, sig);

        assertEq(cards.balanceOf(user), 2);
        assertEq(cards.ownerOf(0), user);
        assertEq(cards.ownerOf(1), user);
    }

    function test_TwoUsersOpenPacksTokenIdsDoNotCollide() public {
        vm.startPrank(minter);
        packs.mint(user, 1, 1);
        packs.mint(user2, 1, 1);
        vm.stopPrank();

        vm.prank(user);
        uint256 commitId1 = packs.commitOpen(1);

        uint256[] memory cardIds1 = new uint256[](2);
        cardIds1[0] = 10;
        cardIds1[1] = 20;
        bytes32 seed1 = keccak256("user1-seed");
        bytes memory sig1 = _signRevealOpen(user, commitId1, cardIds1, seed1);

        vm.prank(user);
        packs.revealOpen(commitId1, cardIds1, seed1, sig1);

        vm.prank(user2);
        uint256 commitId2 = packs.commitOpen(1);

        uint256[] memory cardIds2 = new uint256[](2);
        cardIds2[0] = 30;
        cardIds2[1] = 40;
        bytes32 seed2 = keccak256("user2-seed");
        bytes memory sig2 = _signRevealOpen(user2, commitId2, cardIds2, seed2);

        vm.prank(user2);
        packs.revealOpen(commitId2, cardIds2, seed2, sig2);

        assertEq(cards.ownerOf(0), user);
        assertEq(cards.ownerOf(1), user);
        assertEq(cards.ownerOf(2), user2);
        assertEq(cards.ownerOf(3), user2);
    }

    // ---------------------------------------------------------------
    //  Buying Packs
    // ---------------------------------------------------------------

    function test_BuyPack() public {
        packs.setPackPrice(1, 1 ether);

        vm.deal(user, 10 ether);
        vm.prank(user);
        packs.buyPack{value: 2 ether}(1, 2);

        assertEq(packs.balanceOf(user, 1), 2);
        assertEq(address(packs).balance, 2 ether);
        assertEq(user.balance, 8 ether);
    }

    function test_BuyPackEmitsEvent() public {
        packs.setPackPrice(1, 0.5 ether);

        vm.deal(user, 5 ether);

        vm.expectEmit(true, true, false, true, address(packs));
        emit PackPurchased(user, 1, 3, 1.5 ether);

        vm.prank(user);
        packs.buyPack{value: 1.5 ether}(1, 3);
    }

    function test_BuyPackOverpayRefunds() public {
        packs.setPackPrice(1, 1 ether);

        vm.deal(user, 5 ether);
        vm.prank(user);
        packs.buyPack{value: 3 ether}(1, 1);

        assertEq(packs.balanceOf(user, 1), 1);
        assertEq(address(packs).balance, 1 ether);
        assertEq(user.balance, 4 ether);
    }

    function test_BuyPackInsufficientPaymentReverts() public {
        packs.setPackPrice(1, 1 ether);

        vm.deal(user, 5 ether);
        vm.prank(user);
        vm.expectRevert("HodleaguePacks: insufficient payment");
        packs.buyPack{value: 0.5 ether}(1, 1);
    }

    function test_BuyPackNotForSaleReverts() public {
        vm.deal(user, 5 ether);
        vm.prank(user);
        vm.expectRevert("HodleaguePacks: pack not for sale");
        packs.buyPack{value: 1 ether}(1, 1);
    }

    function test_BuyPackZeroAmountReverts() public {
        packs.setPackPrice(1, 1 ether);

        vm.deal(user, 5 ether);
        vm.prank(user);
        vm.expectRevert("HodleaguePacks: invalid amount");
        packs.buyPack{value: 0}(1, 0);
    }

    function test_BuyPackExceedsMaxAmountReverts() public {
        packs.setPackPrice(1, 0.01 ether);

        vm.deal(user, 100 ether);
        vm.prank(user);
        vm.expectRevert("HodleaguePacks: invalid amount");
        packs.buyPack{value: 1 ether}(1, 51);
    }

    // ---------------------------------------------------------------
    //  Claiming Packs
    // ---------------------------------------------------------------

    function test_ClaimPack() public {
        bytes32 claimId = keccak256("claim-001");
        bytes memory sig = _signClaim(user, claimId, 1, 2);

        vm.prank(user);
        packs.claimPack(claimId, 1, 2, sig);

        assertEq(packs.balanceOf(user, 1), 2);
        assertTrue(packs.usedClaimIds(claimId));
    }

    function test_ClaimPackEmitsEvent() public {
        bytes32 claimId = keccak256("claim-event");
        bytes memory sig = _signClaim(user, claimId, 2, 3);

        vm.expectEmit(true, true, false, true, address(packs));
        emit PackClaimed(user, claimId, 2, 3);

        vm.prank(user);
        packs.claimPack(claimId, 2, 3, sig);
    }

    function test_ClaimPackReplayReverts() public {
        bytes32 claimId = keccak256("claim-replay");
        bytes memory sig = _signClaim(user, claimId, 1, 1);

        vm.prank(user);
        packs.claimPack(claimId, 1, 1, sig);

        vm.prank(user);
        vm.expectRevert("HodleaguePacks: claim already used");
        packs.claimPack(claimId, 1, 1, sig);
    }

    function test_ClaimPackInvalidSignatureReverts() public {
        bytes32 claimId = keccak256("claim-invalid");
        // Sign with wrong key
        bytes32 messageHash = keccak256(abi.encode(user, claimId, uint256(1), uint256(1)));
        bytes32 digest = messageHash.toEthSignedMessageHash();
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(999, digest);
        bytes memory sig = abi.encodePacked(r, s, v);

        vm.prank(user);
        vm.expectRevert("HodleaguePacks: invalid signature");
        packs.claimPack(claimId, 1, 1, sig);
    }

    function test_ClaimPackWrongUserCannotUseSignature() public {
        bytes32 claimId = keccak256("claim-wrong-user");
        // Signature made for user, but user2 tries to use it
        bytes memory sig = _signClaim(user, claimId, 1, 1);

        vm.prank(user2);
        vm.expectRevert("HodleaguePacks: invalid signature");
        packs.claimPack(claimId, 1, 1, sig);
    }

    // ---------------------------------------------------------------
    //  Withdraw
    // ---------------------------------------------------------------

    function test_AdminCanWithdraw() public {
        packs.setPackPrice(1, 1 ether);

        vm.deal(user, 5 ether);
        vm.prank(user);
        packs.buyPack{value: 2 ether}(1, 2);

        address payable treasury = payable(vm.addr(99));
        uint256 before = treasury.balance;

        packs.withdraw(treasury);

        assertEq(treasury.balance, before + 2 ether);
        assertEq(address(packs).balance, 0);
    }

    function test_NonAdminCannotWithdraw() public {
        vm.prank(user);
        vm.expectRevert();
        packs.withdraw(payable(user));
    }

    // ---------------------------------------------------------------
    //  Admin: Pack Prices
    // ---------------------------------------------------------------

    function test_AdminCanSetPackPrice() public {
        packs.setPackPrice(1, 2 ether);
        assertEq(packs.packPrices(1), 2 ether);
    }

    function test_AdminCanDisablePackSale() public {
        packs.setPackPrice(1, 1 ether);
        packs.setPackPrice(1, 0);

        vm.deal(user, 5 ether);
        vm.prank(user);
        vm.expectRevert("HodleaguePacks: pack not for sale");
        packs.buyPack{value: 1 ether}(1, 1);
    }

    function test_NonAdminCannotSetPackPrice() public {
        vm.prank(user);
        vm.expectRevert();
        packs.setPackPrice(1, 1 ether);
    }

    // ---------------------------------------------------------------
    //  UUPS Upgrade
    // ---------------------------------------------------------------

    function test_AdminCanUpgrade() public {
        HodleaguePacks newImpl = new HodleaguePacks();
        packs.upgradeToAndCall(address(newImpl), "");

        // Still works after upgrade
        vm.prank(minter);
        packs.mint(user, 1, 1);
        assertEq(packs.balanceOf(user, 1), 1);
    }

    function test_NonAdminCannotUpgrade() public {
        HodleaguePacks newImpl = new HodleaguePacks();

        vm.prank(user);
        vm.expectRevert();
        packs.upgradeToAndCall(address(newImpl), "");
    }

    // ---------------------------------------------------------------
    //  Interface Support
    // ---------------------------------------------------------------

    function test_SupportsERC1155Interface() public view {
        assertTrue(packs.supportsInterface(0xd9b67a26)); // ERC-1155
    }

    function test_SupportsAccessControlInterface() public view {
        assertTrue(packs.supportsInterface(0x7965db0b)); // IAccessControl
    }
}