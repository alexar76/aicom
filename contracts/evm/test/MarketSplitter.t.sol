// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {MarketSplitter, IERC3009} from "../src/MarketSplitter.sol";

contract MockUSDC is ERC20 {
    constructor() ERC20("USD Coin", "USDC") {}
    function decimals() public pure override returns (uint8) { return 6; }
    function mint(address to, uint256 amt) external { _mint(to, amt); }
}

/// @notice 6-decimal token that skims 1% on every transfer. The splitter must pay out of
///         what ARRIVED, not out of what the caller asked for, or it strands dust that a
///         later sale would quietly pay to the wrong party.
contract MockFeeUSDC is ERC20 {
    uint256 public constant FEE_BPS = 100;
    address public constant SINK = address(0xFEE);

    constructor() ERC20("Fee USD Coin", "fUSDC") {}
    function decimals() public pure override returns (uint8) { return 6; }
    function mint(address to, uint256 amt) external { _mint(to, amt); }

    function _update(address from, address to, uint256 value) internal override {
        if (from != address(0) && to != address(0)) {
            uint256 fee = value * FEE_BPS / 10_000;
            super._update(from, SINK, fee);
            super._update(from, to, value - fee);
        } else {
            super._update(from, to, value);
        }
    }
}

/// @notice The EIP-3009 half of USDC, enough to prove the splitter consumes an
///         authorization the buyer signed and splits what it receives.
contract MockAuthUSDC is ERC20, IERC3009 {
    mapping(address => mapping(bytes32 => bool)) public authorizationState;

    event AuthorizationUsed(address indexed authorizer, bytes32 indexed nonce);

    constructor() ERC20("Auth USD Coin", "aUSDC") {}
    function decimals() public pure override returns (uint8) { return 6; }
    function mint(address to, uint256 amt) external { _mint(to, amt); }

    function transferWithAuthorization(
        address from, address to, uint256 value, uint256, uint256,
        bytes32 nonce, uint8, bytes32, bytes32
    ) external {
        _consume(from, to, value, nonce);
    }

    /// @dev The real token pins `to == msg.sender`; so does this, because that pin is
    ///      the reason the splitter uses this door rather than the transfer one.
    function receiveWithAuthorization(
        address from, address to, uint256 value, uint256, uint256,
        bytes32 nonce, uint8, bytes32, bytes32
    ) external {
        require(to == msg.sender, "caller must be the payee");
        _consume(from, to, value, nonce);
    }

    function _consume(address from, address to, uint256 value, bytes32 nonce) private {
        require(!authorizationState[from][nonce], "authorization is used");
        authorizationState[from][nonce] = true;
        _transfer(from, to, value);
        emit AuthorizationUsed(from, nonce);
    }
}

contract MarketSplitterTest is Test {
    MockUSDC usdc;
    MarketSplitter splitter;

    address constant OPERATOR = address(0x0FF1CE);
    address constant SELLER = address(0x5E11E7);
    address constant BUYER = address(0xB0B);
    bytes32 constant CAP = keccak256("rules.decide@v1");

    uint16 constant FEE_BPS = 250; // 2.5%
    uint256 constant PRICE = 20_000; // $0.02 at 6 decimals

    function setUp() public {
        usdc = new MockUSDC();
        splitter = new MarketSplitter(OPERATOR, FEE_BPS);
        usdc.mint(BUYER, 1_000_000);
        vm.prank(BUYER);
        usdc.approve(address(splitter), type(uint256).max);
    }

    // ---- what the deployment promises, before any money moves -------------------

    function test_the_fee_ceiling_is_not_a_suggestion() public {
        vm.expectRevert(
            abi.encodeWithSelector(MarketSplitter.FeeTooHigh.selector, uint16(1001), uint16(1000))
        );
        new MarketSplitter(OPERATOR, 1001);
    }

    function test_there_is_no_setter_for_the_fee_or_the_operator() public view {
        // Both are `immutable`; this asserts the deployed values are the constructor's
        // and stands as the executable form of "a seller reading this once knows".
        assertEq(splitter.operator(), OPERATOR);
        assertEq(splitter.feeBps(), FEE_BPS);
        assertEq(splitter.MAX_FEE_BPS(), 1000);
    }

    function test_an_operator_payee_of_zero_is_refused() public {
        vm.expectRevert(MarketSplitter.ZeroAddress.selector);
        new MarketSplitter(address(0), FEE_BPS);
    }

    // ---- the split itself --------------------------------------------------------

    function test_one_payment_pays_both_and_keeps_nothing() public {
        vm.prank(BUYER);
        splitter.pay(IERC20(address(usdc)), SELLER, PRICE, CAP);

        uint256 fee = PRICE * FEE_BPS / 10_000;
        assertEq(usdc.balanceOf(SELLER), PRICE - fee, "seller gets the net");
        assertEq(usdc.balanceOf(OPERATOR), fee, "operator gets the fee");
        assertEq(usdc.balanceOf(address(splitter)), 0, "the splitter keeps nothing");
    }

    function test_rounding_goes_to_the_seller() public {
        // 1 base unit cannot be split 2.5/97.5 evenly; the remainder must not drift to
        // the operator, because an operator choosing the rounding rule is the whole
        // thing this contract exists to make impossible. The first cut of this contract
        // computed the SELLER's share by division and failed exactly here: the seller
        // got 0 and the operator took the unit.
        vm.prank(BUYER);
        splitter.pay(IERC20(address(usdc)), SELLER, 1, CAP);
        assertEq(usdc.balanceOf(SELLER), 1);
        assertEq(usdc.balanceOf(OPERATOR), 0);
    }

    function test_a_zero_fee_deployment_pays_the_seller_everything() public {
        MarketSplitter free = new MarketSplitter(OPERATOR, 0);
        vm.startPrank(BUYER);
        usdc.approve(address(free), PRICE);
        free.pay(IERC20(address(usdc)), SELLER, PRICE, CAP);
        vm.stopPrank();
        assertEq(usdc.balanceOf(SELLER), PRICE);
        assertEq(usdc.balanceOf(OPERATOR), 0);
    }

    function test_it_pays_out_of_what_arrived_not_what_was_asked() public {
        MockFeeUSDC skimming = new MockFeeUSDC();
        skimming.mint(BUYER, 1_000_000);
        vm.startPrank(BUYER);
        skimming.approve(address(splitter), PRICE);
        splitter.pay(IERC20(address(skimming)), SELLER, PRICE, CAP);
        vm.stopPrank();

        uint256 arrived = PRICE - (PRICE * skimming.FEE_BPS() / 10_000);
        uint256 fee = arrived * FEE_BPS / 10_000;
        // Transfers OUT are skimmed too, so assert the invariant that is this contract's
        // own: it kept nothing, and it never paid out more than reached it.
        assertEq(skimming.balanceOf(address(splitter)), 0, "no residue to strand");
        assertLe(skimming.balanceOf(SELLER), arrived - fee);
        assertGt(skimming.balanceOf(SELLER), 0);
    }

    // ---- who may be the seller ---------------------------------------------------

    function test_the_seller_may_not_be_the_operator() public {
        vm.prank(BUYER);
        vm.expectRevert(abi.encodeWithSelector(MarketSplitter.BadSeller.selector, OPERATOR));
        splitter.pay(IERC20(address(usdc)), OPERATOR, PRICE, CAP);
    }

    function test_the_seller_may_not_be_the_splitter_itself() public {
        vm.prank(BUYER);
        vm.expectRevert(
            abi.encodeWithSelector(MarketSplitter.BadSeller.selector, address(splitter))
        );
        splitter.pay(IERC20(address(usdc)), address(splitter), PRICE, CAP);
    }

    function test_the_seller_may_not_be_nobody() public {
        vm.prank(BUYER);
        vm.expectRevert(abi.encodeWithSelector(MarketSplitter.BadSeller.selector, address(0)));
        splitter.pay(IERC20(address(usdc)), address(0), PRICE, CAP);
    }

    // ---- the EIP-3009 door, which is what binds a payment to one call -------------

    function test_an_authorization_pays_both_legs_and_burns_its_nonce() public {
        MockAuthUSDC auth = new MockAuthUSDC();
        auth.mint(BUYER, 1_000_000);
        bytes32 nonce = keccak256("hub-minted-nonce");

        vm.prank(BUYER);
        splitter.payWithAuthorization(
            IERC3009(address(auth)), SELLER, PRICE, 0, type(uint256).max,
            nonce, 27, bytes32(0), bytes32(0), CAP
        );

        uint256 fee = PRICE * FEE_BPS / 10_000;
        assertEq(auth.balanceOf(SELLER), PRICE - fee);
        assertEq(auth.balanceOf(OPERATOR), fee);
        assertEq(auth.balanceOf(address(splitter)), 0);
        assertTrue(auth.authorizationState(BUYER, nonce), "the nonce is spent");

        // And it cannot be spent twice — which is what one-payment-one-call rests on.
        vm.prank(BUYER);
        vm.expectRevert(bytes("authorization is used"));
        splitter.payWithAuthorization(
            IERC3009(address(auth)), SELLER, PRICE, 0, type(uint256).max,
            nonce, 27, bytes32(0), bytes32(0), CAP
        );
    }

    function test_the_split_is_announced_with_the_listing_it_paid_for() public {
        uint256 fee = PRICE * FEE_BPS / 10_000;
        vm.expectEmit(true, true, true, true, address(splitter));
        emit MarketSplitter.Split(address(usdc), SELLER, BUYER, PRICE - fee, fee, CAP);
        vm.prank(BUYER);
        splitter.pay(IERC20(address(usdc)), SELLER, PRICE, CAP);
    }
}
