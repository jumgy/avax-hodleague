// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/HodleagueCards.sol";
import "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

contract HodleagueCardsTest is Test {
    HodleagueCards public cards;

    address public admin;
    address public minter;
    address public burner;
    address public user;
    address public user2;
    uint256 public adminKey;
    uint256 public minterKey;
    uint256 public userKey;

    function setUp() public {
        adminKey = 1;
        minterKey = 2;
        userKey = 3;
        admin = address(this);
        minter = vm.addr(minterKey);
        burner = vm.addr(4);
        user = vm.addr(userKey);
        user2 = vm.addr(5);

        HodleagueCards implementation = new HodleagueCards();
        bytes memory initData = abi.encodeCall(
            HodleagueCards.initialize,
            (admin, minter, "https://api.hodleague.com/nft/cards/")
        );
        ERC1967Proxy proxy = new ERC1967Proxy(address(implementation), initData);
        cards = HodleagueCards(address(proxy));

        // Grant BURNER_ROLE for burn tests
        vm.prank(admin);
        cards.grantRole(cards.BURNER_ROLE(), burner);
    }

    // ---------------------------------------------------------------
    //  Minting
    // ---------------------------------------------------------------

    function test_MinterCanMint() public {
        vm.prank(minter);
        cards.mint(user, 1);

        assertEq(cards.ownerOf(1), user);
        assertEq(cards.balanceOf(user), 1);
    }

    function test_NonMinterCannotMint() public {
        vm.prank(user);
        vm.expectRevert();
        cards.mint(user, 1);
    }

    function test_MintMultipleTokens() public {
        vm.startPrank(minter);
        cards.mint(user, 1);
        cards.mint(user, 2);
        cards.mint(user, 3);
        cards.mint(user2, 4);
        vm.stopPrank();

        assertEq(cards.balanceOf(user), 3);
        assertEq(cards.balanceOf(user2), 1);
        assertEq(cards.ownerOf(1), user);
        assertEq(cards.ownerOf(4), user2);
    }

    function test_MintDuplicateTokenIdReverts() public {
        vm.startPrank(minter);
        cards.mint(user, 1);
        vm.expectRevert();
        cards.mint(user2, 1);
        vm.stopPrank();
    }

    // ---------------------------------------------------------------
    //  Burning
    // ---------------------------------------------------------------

    function test_OwnerCanBurn() public {
        vm.prank(minter);
        cards.mint(user, 1);

        vm.prank(user);
        cards.burn(1);

        vm.expectRevert();
        cards.ownerOf(1);
    }

    function test_BurnerRoleCanBurn() public {
        vm.prank(minter);
        cards.mint(user, 1);

        vm.prank(burner);
        cards.burn(1);

        vm.expectRevert();
        cards.ownerOf(1);
    }

    function test_NonOwnerNonBurnerCannotBurn() public {
        vm.prank(minter);
        cards.mint(user, 1);

        vm.prank(admin);
        vm.expectRevert("HodleagueCards: caller is not owner or burner");
        cards.burn(1);
    }

    function test_BurnNonExistentTokenReverts() public {
        vm.prank(user);
        vm.expectRevert();
        cards.burn(999);
    }

    // ---------------------------------------------------------------
    //  Metadata
    // ---------------------------------------------------------------

    function test_TokenURI() public {
        vm.prank(minter);
        cards.mint(user, 42);

        assertEq(cards.tokenURI(42), "https://api.hodleague.com/nft/cards/42");
    }

    function test_TokenURIZeroId() public {
        vm.prank(minter);
        cards.mint(user, 0);

        assertEq(cards.tokenURI(0), "https://api.hodleague.com/nft/cards/0");
    }

    function test_TokenURIRevertsForNonExistent() public {
        vm.expectRevert();
        cards.tokenURI(999);
    }

    function test_AdminCanSetBaseURI() public {
        vm.prank(admin);
        cards.setBaseURI("https://new.hodleague.com/cards/");

        vm.prank(minter);
        cards.mint(user, 1);

        assertEq(cards.tokenURI(1), "https://new.hodleague.com/cards/1");
    }

    function test_NonAdminCannotSetBaseURI() public {
        vm.prank(user);
        vm.expectRevert();
        cards.setBaseURI("https://evil.com/");
    }

    // ---------------------------------------------------------------
    //  Access Control
    // ---------------------------------------------------------------

    function test_AdminCanGrantMinterRole() public {
        vm.prank(admin);
        cards.grantRole(cards.MINTER_ROLE(), user2);

        vm.prank(user2);
        cards.mint(user, 100);
        assertEq(cards.ownerOf(100), user);
    }

    function test_AdminCanRevokeMinterRole() public {
        vm.prank(admin);
        cards.revokeRole(cards.MINTER_ROLE(), minter);

        vm.prank(minter);
        vm.expectRevert();
        cards.mint(user, 1);
    }

    function test_AdminCanGrantBurnerRole() public {
        address newBurner = vm.addr(10);

        vm.prank(admin);
        cards.grantRole(cards.BURNER_ROLE(), newBurner);

        vm.prank(minter);
        cards.mint(user, 1);

        vm.prank(newBurner);
        cards.burn(1);

        vm.expectRevert();
        cards.ownerOf(1);
    }

    // ---------------------------------------------------------------
    //  UUPS Upgrade
    // ---------------------------------------------------------------

    function test_AdminCanUpgrade() public {
        HodleagueCards newImpl = new HodleagueCards();

        vm.prank(admin);
        cards.upgradeToAndCall(address(newImpl), "");

        // Contract still works after upgrade
        vm.prank(minter);
        cards.mint(user, 1);
        assertEq(cards.ownerOf(1), user);
    }

    function test_NonAdminCannotUpgrade() public {
        HodleagueCards newImpl = new HodleagueCards();

        vm.prank(user);
        vm.expectRevert();
        cards.upgradeToAndCall(address(newImpl), "");
    }

    // ---------------------------------------------------------------
    //  ERC-721 Standard Behavior
    // ---------------------------------------------------------------

    function test_Transfer() public {
        vm.prank(minter);
        cards.mint(user, 1);

        vm.prank(user);
        cards.transferFrom(user, user2, 1);

        assertEq(cards.ownerOf(1), user2);
        assertEq(cards.balanceOf(user), 0);
        assertEq(cards.balanceOf(user2), 1);
    }

    function test_SupportsERC721Interface() public view {
        // ERC-721 interface ID
        assertTrue(cards.supportsInterface(0x80ac58cd));
    }

    function test_SupportsAccessControlInterface() public view {
        // IAccessControl interface ID
        assertTrue(cards.supportsInterface(0x7965db0b));
    }
}