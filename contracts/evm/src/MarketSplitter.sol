// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.28;

/**
 * @title MarketSplitter
 * @notice One buyer payment, split on-chain between the seller and the hub operator.
 *
 * WHY THIS EXISTS. The catalogue rail pays the seller directly: the 402 names the
 * listing's `payout_address`, the buyer sends USDC there, and the Hub reads the chain
 * and serves the call. That kept the Hub out of custody — and also out of the money
 * entirely, which is a different thing that got bundled into the same invariant. The
 * Hub carries the index, the trust scoring, the 402 machinery and the RPC verification,
 * and earned nothing for it, while publishing both the payee and the invoke URL so a
 * buyer could route around it after one lookup.
 *
 * "The Hub does not hold the money" and "the Hub takes no cut" are separable. This
 * contract separates them: it is the payee named in the 402, it never keeps a balance
 * past the end of the call that created it, and the Hub holds no key over it.
 *
 * INVARIANTS, which hold regardless of what any operator intends:
 *
 *   - `operator` and `feeBps` are IMMUTABLE. There is no setter, no owner, no upgrade
 *     path. A seller reading this contract once knows what every future sale pays them.
 *   - `feeBps <= MAX_FEE_BPS` (10%), enforced in the constructor. A deployment that
 *     tries for more does not exist.
 *   - Every wei that arrives in a call leaves in the same call. `split` pays out of the
 *     measured delta, not out of the argument, so a fee-on-transfer token cannot leave
 *     a residue and a griefer cannot strand dust that later pays somebody else.
 *   - The OPERATOR's share is the one computed by division; the seller takes the
 *     remainder. Integer division truncates, so the computed side is the side that
 *     loses the dust — which means the operator's cut is never more than `feeBps` of
 *     what arrived, and every rounding remainder goes to the seller. Written the other
 *     way round it reads as the generous choice and is the opposite: at 250 bps a
 *     one-unit payment paid the seller nothing and the operator the whole unit.
 *   - `seller` may not be this contract, the zero address, or the operator: each of
 *     those turns a split into something that is not a split.
 *
 * TWO DOORS, because a buyer arrives one of two ways.
 *
 *   `pay` is for a buyer who has approved this contract — one `transferFrom`, then the
 *   split. `payWithAuthorization` is for EIP-3009: the buyer signs an authorization
 *   naming THIS contract and the nonce the Hub minted in its 402, and the token emits
 *   `AuthorizationUsed(from, nonce)` when it is consumed. That event is what binds a
 *   payment to one call, and the Hub already looks for exactly it — so routing through
 *   the splitter changes who the `Transfer` logs name and nothing else about the proof.
 *
 * WHAT THE HUB VERIFIES, and why it is not "trust the contract". The Hub does not check
 * that the payment went through this address. It checks the two `Transfer` legs it
 * requires: at least `net` to the seller and at least `fee` to the operator, in one
 * transaction. This contract is the convenience that lets a buyer produce both legs
 * with one signature; a buyer who prefers a multicall of two plain transfers settles
 * identically. Neither the Hub nor the seller has to trust this code to be paid — the
 * chain says whether they were.
 *
 * NOT DEPLOYED BY DEFAULT. The rail runs with `feeBps = 0` and no splitter address
 * until an operator deploys this and configures it. Nothing here moves money on its own.
 */

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @dev The EIP-3009 surface USDC exposes. Declared here rather than imported so this
///      file does not depend on a token package for two selectors.
interface IERC3009 {
    function transferWithAuthorization(
        address from,
        address to,
        uint256 value,
        uint256 validAfter,
        uint256 validBefore,
        bytes32 nonce,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external;

    function receiveWithAuthorization(
        address from,
        address to,
        uint256 value,
        uint256 validAfter,
        uint256 validBefore,
        bytes32 nonce,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external;
}

contract MarketSplitter is ReentrancyGuard {
    using SafeERC20 for IERC20;

    /// @notice Hard ceiling on the operator's share. Immutable and unconditional.
    uint16 public constant MAX_FEE_BPS = 1000; // 10%

    /// @notice Who receives the operator's share. Set once, at deployment.
    address public immutable operator;

    /// @notice The operator's share in basis points. Set once, at deployment.
    uint16 public immutable feeBps;

    /**
     * @notice One settled sale.
     * @dev `capabilityId` is the Hub's listing id, kept as a hash so the log is a fixed
     *      width and the string never has to be trusted. It is evidence for a reader
     *      reconciling a receipt, not an input to any check in this contract.
     */
    event Split(
        address indexed token,
        address indexed seller,
        address indexed payer,
        uint256 sellerAmount,
        uint256 operatorAmount,
        bytes32 capabilityId
    );

    error ZeroAddress();
    error FeeTooHigh(uint16 requested, uint16 maximum);
    error BadSeller(address seller);
    error NothingReceived();

    constructor(address operator_, uint16 feeBps_) {
        if (operator_ == address(0)) revert ZeroAddress();
        if (feeBps_ > MAX_FEE_BPS) revert FeeTooHigh(feeBps_, MAX_FEE_BPS);
        operator = operator_;
        feeBps = feeBps_;
    }

    /**
     * @notice Pay `gross` for a listing; the seller and the operator are paid in this call.
     * @dev Requires a prior `approve(address(this), gross)` by the buyer.
     */
    function pay(
        IERC20 token,
        address seller,
        uint256 gross,
        bytes32 capabilityId
    ) external nonReentrant {
        _checkSeller(seller);
        uint256 before = token.balanceOf(address(this));
        token.safeTransferFrom(msg.sender, address(this), gross);
        _settle(token, seller, msg.sender, token.balanceOf(address(this)) - before, capabilityId);
    }

    /**
     * @notice Pay with an EIP-3009 authorization the buyer signed over the Hub's nonce.
     * @dev `receiveWithAuthorization` is used rather than `transferWithAuthorization`
     *      because only the former pins `to == msg.sender`: with the transfer variant a
     *      signed authorization naming this contract is public the moment it is broadcast,
     *      and anyone could front-run it into a call that splits to a seller of THEIR
     *      choosing. The receive variant can only be consumed by the named recipient,
     *      which is this contract, so the (seller, capabilityId) it is settled against are
     *      the ones in the transaction that carried the signature.
     */
    function payWithAuthorization(
        IERC3009 token,
        address seller,
        uint256 gross,
        uint256 validAfter,
        uint256 validBefore,
        bytes32 nonce,
        uint8 v,
        bytes32 r,
        bytes32 s,
        bytes32 capabilityId
    ) external nonReentrant {
        _checkSeller(seller);
        IERC20 erc20 = IERC20(address(token));
        uint256 before = erc20.balanceOf(address(this));
        // `from` is recovered by the token from the signature, so the payer named in the
        // event below is the account that actually signed, never the caller's claim.
        token.receiveWithAuthorization(
            msg.sender, address(this), gross, validAfter, validBefore, nonce, v, r, s
        );
        _settle(erc20, seller, msg.sender, erc20.balanceOf(address(this)) - before, capabilityId);
    }

    function _checkSeller(address seller) private view {
        if (seller == address(0) || seller == address(this) || seller == operator) {
            revert BadSeller(seller);
        }
    }

    /**
     * @dev Pays out of `received` — the measured delta — so nothing can be left behind.
     *      The OPERATOR's share is the one computed by division, and the seller takes
     *      the remainder. That order is the invariant, not a detail: integer division
     *      truncates, so whichever share is computed keeps less than its exact value and
     *      the other absorbs the dust. Computing the seller's share first read as the
     *      generous choice and was the opposite — on a 1-unit payment at 250 bps the
     *      seller received 0 and the operator took the whole unit. This way the
     *      operator's cut is never MORE than `feeBps` of what arrived, and every
     *      remainder goes to the seller.
     */
    function _settle(
        IERC20 token,
        address seller,
        address payer,
        uint256 received,
        bytes32 capabilityId
    ) private {
        if (received == 0) revert NothingReceived();
        uint256 operatorAmount = (received * feeBps) / 10_000;
        uint256 sellerAmount = received - operatorAmount;
        token.safeTransfer(seller, sellerAmount);
        if (operatorAmount != 0) {
            token.safeTransfer(operator, operatorAmount);
        }
        emit Split(address(token), seller, payer, sellerAmount, operatorAmount, capabilityId);
    }
}
