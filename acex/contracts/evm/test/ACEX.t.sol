// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

import {AgentShareToken} from "../src/AgentShareToken.sol";
import {AgentCollateralVault} from "../src/AgentCollateralVault.sol";
import {AgentListingRegistry} from "../src/AgentListingRegistry.sol";
import {AgentLendingPool} from "../src/AgentLendingPool.sol";
import {PulseAMM} from "../src/PulseAMM.sol";
import {IAgentListingRegistry} from "../src/interfaces/IAgentListingRegistry.sol";

contract MockUSDC is ERC20 {
    constructor() ERC20("USDC", "USDC") {}

    function decimals() public pure override returns (uint8) {
        return 6;
    }

    function mint(address to, uint256 amt) external {
        _mint(to, amt);
    }
}

contract ACEXTest is Test {
    MockUSDC usdc;
    AgentCollateralVault vault;
    AgentListingRegistry registry;
    AgentLendingPool lending;
    PulseAMM amm;

    address agent = address(0xA1);
    address auditor = address(0xA2);
    address lender = address(0xA3);

    bytes32 listingId = keccak256("agent-alpha");

    function setUp() public {
        usdc = new MockUSDC();
        vault = new AgentCollateralVault(address(usdc));
        registry = new AgentListingRegistry(address(vault), address(usdc));
        vault.setRegistry(address(registry));
        lending = new AgentLendingPool(address(usdc), address(vault), address(registry));
        vault.setLendingPool(address(lending));
        amm = new PulseAMM();

        registry.setAuditor(auditor, true);
        usdc.mint(agent, 1_000_000e6);
        usdc.mint(lender, 1_000_000e6);
        usdc.mint(address(this), 1_000_000e6);
    }

    function test_ALP_listing_flow() public {
        vm.startPrank(agent);
        registry.applyForListing(listingId, keccak256("meta"));
        vm.stopPrank();

        vm.prank(auditor);
        registry.recordAudit(listingId, 8500);

        address share = registry.approveListing(listingId, "Agent Alpha", "AAIX", 1_000_000e18);
        assertTrue(share != address(0));

        IAgentListingRegistry.Listing memory L = registry.getListing(listingId);
        assertEq(uint8(L.status), uint8(IAgentListingRegistry.ListingStatus.Approved));
    }

    function test_notes_collateral_and_redeem() public {
        _approveListing();

        vm.startPrank(agent);
        usdc.approve(address(registry), 100_000e6);
        address note = registry.issueAgentNotes(
            listingId,
            "Agent Alpha Note",
            "AAN",
            100e18,
            uint64(block.timestamp + 30 days),
            1e6,
            50_000e6
        );
        vm.stopPrank();

        assertTrue(note != address(0));
        // 50_000 USDC deposited; 100 USDC locked for 100 notes @ $1 face
        assertEq(vault.availableCollateral(listingId), 50_000e6 - 100e6);

        vm.warp(block.timestamp + 31 days);
        uint256 before = usdc.balanceOf(agent);
        vm.prank(agent);
        vault.redeemNote(note, 100e18);
        assertGt(usdc.balanceOf(agent), before);
    }

    function test_lending_borrow_repay() public {
        _approveListing();

        vm.startPrank(agent);
        usdc.approve(address(vault), 200_000e6);
        usdc.approve(address(registry), 200_000e6);
        registry.issueAgentNotes(
            listingId, "N", "N", 1e18, uint64(block.timestamp + 1 days), 1e6, 100_000e6
        );
        vm.stopPrank();

        vm.startPrank(lender);
        usdc.approve(address(lending), 500_000e6);
        lending.deposit(500_000e6);
        vm.stopPrank();

        vm.startPrank(agent);
        lending.borrow(listingId, 10_000e6);
        usdc.approve(address(lending), 10_000e6);
        lending.repay(listingId, 10_000e6);
        vm.stopPrank();
    }

    function test_pulse_amm_swap() public {
        _approveListing();
        address shareAddr = registry.getListing(listingId).shareToken;
        AgentShareToken share = AgentShareToken(shareAddr);

        vm.startPrank(agent);
        share.approve(address(this), type(uint256).max);
        share.transfer(address(this), 200_000e18);
        vm.stopPrank();

        share.approve(address(amm), type(uint256).max);
        usdc.approve(address(amm), type(uint256).max);
        amm.createPool(shareAddr, address(usdc), 100_000e18, 50_000e6);

        share.approve(address(amm), 10_000e18);
        uint256 before = usdc.balanceOf(address(this));
        amm.swapShareForUsdc(shareAddr, 10_000e18, 1);
        assertGt(usdc.balanceOf(address(this)), before);
    }

    function _approveListing() internal {
        vm.prank(agent);
        registry.applyForListing(listingId, keccak256("meta"));
        vm.prank(auditor);
        registry.recordAudit(listingId, 9000);
        registry.approveListing(listingId, "Agent", "AGT", 1e24);
    }
}
