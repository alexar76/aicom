// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @notice The UNI realm's dollar. A sealed-bubble stand-in for USDC that is
///         indistinguishable from it to anything inside the bubble.
///
/// @dev Three deliberate choices, each one there because a difference would have been
///      detectable from inside — and the whole premise of UNI is that it is not.
///
///      1. **It calls itself what USDC calls itself.** `name()` is "USD Coin", `symbol()`
///         is "USDC", `version()` is "2", and 6 decimals. Those are not cosmetics: they are
///         the EIP-712 domain fields a payer signs over, so a client that hard-codes
///         `extra: {name: "USD Coin", version: "2"}` (every x402 client does, because that
///         is what Base mainnet USDC reports) produces a signature this contract accepts.
///         Change the name and every payment inside the bubble fails with a signature error
///         that looks like a client bug.
///
///      2. **EIP-3009 is implemented, not stubbed.** `transferWithAuthorization` is the
///         mechanism the x402 "exact" scheme settles with. Without it the hub could verify a
///         payment inside UNI and never settle it, which is precisely the half-rail the
///         real deployment already suffers from — the bubble would be *less* capable than
///         what it simulates, and an inside agent could tell.
///
///      3. **`mint` is open to anyone.** Money in UNI comes from nowhere and is unlimited;
///         that is the point, not a shortcut. It is only safe because of where this contract
///         can exist: chain 31337 behind a private RPC, with the hub's realm seal refusing
///         to name a real chain, a real endpoint or a real asset. An open mint on a public
///         chain would be worthless; here it is the funding model.
///
///      The chain id lives in the domain separator, recomputed if it ever changes, so a
///      signature made here is invalid on Base and a signature made on Base is invalid
///      here. That is the arithmetic the seal rests on.
contract UniUSD is ERC20 {
    uint8 private constant _DECIMALS = 6;

    /// @dev keccak256("TransferWithAuthorization(address from,address to,uint256 value,uint256 validAfter,uint256 validBefore,bytes32 nonce)")
    bytes32 public constant TRANSFER_WITH_AUTHORIZATION_TYPEHASH =
        0x7c7c6cdb67a18743f49ec6fa9b35f50d52ed05cbed4cc592e13b44501c1a2267;

    bytes32 private constant _EIP712_DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");

    string public constant version = "2";

    /// @notice Which authorizations a payer has already used, exactly as EIP-3009 specifies.
    mapping(address => mapping(bytes32 => bool)) public authorizationState;

    uint256 private immutable _deployChainId;
    bytes32 private immutable _cachedDomainSeparator;

    error AuthorizationUsed();
    error AuthorizationNotYetValid();
    error AuthorizationExpired();
    error InvalidSignature();

    event AuthorizationUsedEvent(address indexed authorizer, bytes32 indexed nonce);

    constructor() ERC20("USD Coin", "USDC") {
        _deployChainId = block.chainid;
        _cachedDomainSeparator = _buildDomainSeparator();
    }

    function decimals() public pure override returns (uint8) {
        return _DECIMALS;
    }

    /// @notice Funding from nowhere — the UNI premise. See the contract docs for why this
    ///         is deliberate and why it is only safe inside a sealed bubble.
    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    function domainSeparator() public view returns (bytes32) {
        // Recomputed on a fork so a signature can never be valid on a chain it was not
        // signed for. Mirrors AIMarketEscrow._buildDomainSeparator.
        return block.chainid == _deployChainId ? _cachedDomainSeparator : _buildDomainSeparator();
    }

    function _buildDomainSeparator() private view returns (bytes32) {
        return keccak256(
            abi.encode(
                _EIP712_DOMAIN_TYPEHASH,
                keccak256(bytes(name())),
                keccak256(bytes(version)),
                block.chainid,
                address(this)
            )
        );
    }

    /// @notice EIP-3009: move `value` from `from` to `to` on the payer's signed authorization.
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
    ) external {
        if (block.timestamp <= validAfter) revert AuthorizationNotYetValid();
        if (block.timestamp >= validBefore) revert AuthorizationExpired();
        if (authorizationState[from][nonce]) revert AuthorizationUsed();

        bytes32 structHash = keccak256(
            abi.encode(
                TRANSFER_WITH_AUTHORIZATION_TYPEHASH, from, to, value, validAfter, validBefore, nonce
            )
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator(), structHash));
        address signer = ecrecover(digest, v, r, s);
        if (signer == address(0) || signer != from) revert InvalidSignature();

        authorizationState[from][nonce] = true;
        emit AuthorizationUsedEvent(from, nonce);
        _transfer(from, to, value);
    }
}
