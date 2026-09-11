'use client';

import React, { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { motion } from 'framer-motion';
import {
  ArrowLeft,
  ShoppingCart,
  Wallet,
  CheckCircle2,
  Copy,
  ExternalLink,
  AlertTriangle,
  Loader2,
  Bitcoin,
  Smartphone,
  Globe,
  XCircle,
} from 'lucide-react';
import { BrowserProvider, formatEther, parseEther } from 'ethers';
import { GlassCard } from '@/components/ui/GlassCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { Modal } from '@/components/ui/Modal';
import api, { ApiRequestError } from '@/lib/api';
import { getStoredReferral } from '@/lib/referral';
import { truncateAddress, copyToClipboard } from '@/lib/utils';

type Step = 'form' | 'payment' | 'confirming' | 'awaiting_confirmations' | 'success' | 'error';

interface ChainInfo {
  id: string;
  name: string;
  icon: string;
  tokens: string[];
}

const SUPPORTED_CHAINS: ChainInfo[] = [
  { id: 'base', name: 'Base', icon: '🔵', tokens: ['USDT', 'USDC'] },
  { id: 'arbitrum', name: 'Arbitrum', icon: '🔴', tokens: ['USDT', 'USDC'] },
  { id: 'ethereum', name: 'Ethereum', icon: '💎', tokens: ['ETH', 'USDT', 'USDC'] },
  { id: 'solana', name: 'Solana', icon: '🟣', tokens: ['USDC', 'SOL'] },
];

// ── EVM chain IDs for wallet switching ─────────────────────────────────────
interface ChainConfig {
  chainId: number;
  chainName: string;
  /** Primary RPC endpoint (operator-overridable via NEXT_PUBLIC_*_RPC_URL). */
  rpcUrl: string;
  /** Ordered RPC list (primary first) handed to the wallet + reachability probe. */
  rpcUrls: string[];
  explorer: string;
  nativeCurrency: { name: string; symbol: string; decimals: number };
}

/**
 * Resolve an operator-overridable RPC endpoint. Operators can pin a private /
 * higher-rate-limit provider via NEXT_PUBLIC_<KEY>_RPC_URL; the bundled public
 * endpoints stay as fallbacks so checkout keeps working out of the box.
 */
function resolveRpcUrls(envKey: string, defaults: string[]): string[] {
  const override = process.env[`NEXT_PUBLIC_${envKey}_RPC_URL`];
  const seen = new Set<string>();
  const urls: string[] = [];
  for (const url of [override, ...defaults]) {
    const trimmed = (url || '').trim();
    if (trimmed && !seen.has(trimmed)) {
      seen.add(trimmed);
      urls.push(trimmed);
    }
  }
  return urls;
}

function makeChainConfig(
  chainId: number,
  chainName: string,
  envKey: string,
  defaultRpcUrls: string[],
  explorer: string,
): ChainConfig {
  const rpcUrls = resolveRpcUrls(envKey, defaultRpcUrls);
  return {
    chainId,
    chainName,
    rpcUrl: rpcUrls[0],
    rpcUrls,
    explorer,
    nativeCurrency: { name: 'Ether', symbol: 'ETH', decimals: 18 },
  };
}

/**
 * Probe RPC endpoints with a cheap `eth_blockNumber` call and return them with
 * the reachable ones first. Used so the wallet is handed a working endpoint
 * when adding a chain; if every probe fails (offline, CORS) we keep the
 * original order so the wallet can still try them all.
 */
async function orderRpcUrlsByReachability(rpcUrls: string[]): Promise<string[]> {
  if (rpcUrls.length <= 1) return rpcUrls;

  const probe = async (url: string): Promise<boolean> => {
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'eth_blockNumber', params: [] }),
        signal: AbortSignal.timeout(2500),
      });
      if (!res.ok) return false;
      const data = await res.json().catch(() => null);
      return Boolean(data && typeof data.result === 'string');
    } catch {
      return false;
    }
  };

  const reachable = await Promise.all(rpcUrls.map(probe));
  const ok = rpcUrls.filter((_, i) => reachable[i]);
  const failed = rpcUrls.filter((_, i) => !reachable[i]);
  const ordered = [...ok, ...failed];
  return ordered.length > 0 ? ordered : rpcUrls;
}

const CHAIN_CONFIG_MAINNET: Record<string, ChainConfig> = {
  base: makeChainConfig(
    8453,
    'Base',
    'BASE',
    ['https://mainnet.base.org', 'https://base.llamarpc.com'],
    'https://basescan.org/tx/',
  ),
  arbitrum: makeChainConfig(
    42161,
    'Arbitrum One',
    'ARBITRUM',
    ['https://arb1.arbitrum.io/rpc', 'https://arbitrum.llamarpc.com'],
    'https://arbiscan.io/tx/',
  ),
  ethereum: makeChainConfig(
    1,
    'Ethereum Mainnet',
    'ETHEREUM',
    ['https://cloudflare-eth.com', 'https://eth.llamarpc.com'],
    'https://etherscan.io/tx/',
  ),
};

const CHAIN_CONFIG_TESTNET: Record<string, ChainConfig> = {
  base: makeChainConfig(
    84532,
    'Base Sepolia',
    'BASE_TESTNET',
    ['https://sepolia.base.org'],
    'https://sepolia.basescan.org/tx/',
  ),
  arbitrum: makeChainConfig(
    421614,
    'Arbitrum Sepolia',
    'ARBITRUM_TESTNET',
    ['https://sepolia-rollup.arbitrum.io/rpc'],
    'https://sepolia.arbiscan.io/tx/',
  ),
  ethereum: makeChainConfig(
    11155111,
    'Sepolia',
    'ETHEREUM_TESTNET',
    ['https://rpc.sepolia.org', 'https://ethereum-sepolia-rpc.publicnode.com'],
    'https://sepolia.etherscan.io/tx/',
  ),
};

export default function CheckoutPage() {
  const [selectedChain, setSelectedChain] = useState('base');
  const [selectedToken, setSelectedToken] = useState('USDT');
  const [amount, setAmount] = useState('10');
  const [productId, setProductId] = useState('');
  const [step, setStep] = useState<Step>('form');
  const [isConfirming, setIsConfirming] = useState(false);
  const [paymentInfo, setPaymentInfo] = useState<any>(null);
  const [txHash, setTxHash] = useState('');
  const [copied, setCopied] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [customerEmail, setCustomerEmail] = useState<string | null>(null);
  const [paymentTestnet, setPaymentTestnet] = useState(false);
  const [verifyStub, setVerifyStub] = useState(false);
  const [minConfirmations, setMinConfirmations] = useState(2);
  const [pendingConfirmations, setPendingConfirmations] = useState(0);
  const [supportedChains, setSupportedChains] = useState<ChainInfo[]>(SUPPORTED_CHAINS);

  const chainConfig = paymentTestnet ? CHAIN_CONFIG_TESTNET : CHAIN_CONFIG_MAINNET;

  // Wallet state
  const [walletAddress, setWalletAddress] = useState<string | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [walletError, setWalletError] = useState('');

  // ── Wallet Connection ──────────────────────────────────────────────────

  const connectWallet = useCallback(async () => {
    if (typeof window === 'undefined' || !(window as any).ethereum) {
      setWalletError('No wallet detected. Install MetaMask or another Web3 wallet.');
      return;
    }

    setIsConnecting(true);
    setWalletError('');

    try {
      const provider = new BrowserProvider((window as any).ethereum);
      const accounts = await provider.send('eth_requestAccounts', []);
      if (accounts.length > 0) {
        setWalletAddress(accounts[0]);
      }
    } catch (err: any) {
      const msg = err?.code === 4001
        ? 'Connection rejected by user.'
        : `Failed to connect: ${err?.message || 'Unknown error'}`;
      setWalletError(msg);
    } finally {
      setIsConnecting(false);
    }
  }, []);

  const disconnectWallet = useCallback(() => {
    setWalletAddress(null);
  }, []);

  // Auto-connect if already authorized
  useEffect(() => {
    const initialProduct = new URLSearchParams(window.location.search).get('product');
    if (initialProduct) setProductId(initialProduct);
    const savedEmail = typeof window !== 'undefined' ? localStorage.getItem('customer_email') : null;
    if (savedEmail) setCustomerEmail(savedEmail);
    api.getSupportedChains().then((meta: any) => {
      if (Array.isArray(meta?.chains) && meta.chains.length > 0) {
        setSupportedChains(meta.chains);
      }
      setPaymentTestnet(Boolean(meta?.testnet));
      setVerifyStub(Boolean(meta?.verify_stub));
      if (typeof meta?.min_confirmations === 'number') {
        setMinConfirmations(meta.min_confirmations);
      }
    }).catch(() => {
      /* keep defaults */
    });
  }, []);

  useEffect(() => {
    const tryAutoConnect = async () => {
      if (typeof window !== 'undefined' && (window as any).ethereum) {
        try {
          const provider = new BrowserProvider((window as any).ethereum);
          const accounts = await provider.send('eth_accounts', []);
          if (accounts.length > 0) {
            setWalletAddress(accounts[0]);
          }
        } catch {
          // Silently fail
        }
      }
    };
    tryAutoConnect();
  }, []);

  const handleCustomerAuth = async () => {
    if (!authEmail || !authPassword) return;
    setAuthLoading(true);
    setErrorMessage('');
    try {
      const res = authMode === 'register'
        ? await api.registerCustomer(authEmail, authPassword)
        : await api.loginCustomer(authEmail, authPassword);
      localStorage.setItem('customer_token', res.access_token);
      localStorage.setItem('customer_email', res.customer.email);
      setCustomerEmail(res.customer.email);
    } catch (err: any) {
      setErrorMessage(err?.message || 'Customer authentication failed');
    } finally {
      setAuthLoading(false);
    }
  };

  // ── Switch chain in wallet ─────────────────────────────────────────────

  const switchChainInWallet = useCallback(async (chainId: string) => {
    if (typeof window === 'undefined' || !(window as any).ethereum) return;
    const config = chainConfig[chainId];
    if (!config) return; // Solana etc. not supported via EVM wallet

    try {
      await (window as any).ethereum.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: `0x${config.chainId.toString(16)}` }],
      });
    } catch (switchErr: any) {
      // Chain not added — add it. Order the RPC list so a reachable endpoint
      // is offered first; the wallet still keeps the rest as fallbacks.
      if (switchErr.code === 4902) {
        const rpcUrls = await orderRpcUrlsByReachability(config.rpcUrls);
        try {
          await (window as any).ethereum.request({
            method: 'wallet_addEthereumChain',
            params: [{
              chainId: `0x${config.chainId.toString(16)}`,
              chainName: config.chainName,
              nativeCurrency: config.nativeCurrency,
              rpcUrls,
              blockExplorerUrls: [config.explorer.replace('/tx/', '')],
            }],
          });
        } catch {
          // User rejected
        }
      }
    }
  }, [chainConfig]);

  // ── Payment handlers ───────────────────────────────────────────────────

  const handleCreatePayment = async () => {
    if (!productId || !amount) return;

    setStep('payment');
    setErrorMessage('');
    try {
      const referral_source = getStoredReferral() || undefined;
      const payment = await api.createPayment({
        product_id: productId,
        chain: selectedChain,
        token: selectedToken,
        referral_source,
      });
      setPaymentInfo(payment);
      setAmount(String(payment.amount));
    } catch (err) {
      setErrorMessage('Failed to create payment. Please try again.');
      setStep('form');
    }
  };

  const handleSendTransaction = async () => {
    if (!paymentInfo || !walletAddress) return;

    const chainId = paymentInfo.chain;
    const config = chainConfig[chainId];

    if (!config) {
      // Solana or other non-EVM — use manual tx hash
      if (!txHash) return;
      await handleConfirmPayment();
      return;
    }

    setIsConfirming(true);
    setErrorMessage('');

    try {
      // Switch to the correct chain
      await switchChainInWallet(chainId);

      const provider = new BrowserProvider((window as any).ethereum);
      const signer = await provider.getSigner();

      let tx;
      if (paymentInfo.currency === 'ETH') {
        // Native ETH transfer
        tx = await signer.sendTransaction({
          to: paymentInfo.wallet_address,
          value: parseEther(paymentInfo.amount.toString()),
        });
      } else {
        // ERC20 token transfer — use transfer() on the token contract
        // We need the token contract address; we'll send the raw tx via the wallet
        // For simplicity, prompt user to send via their wallet UI and enter tx hash
        setStep('confirming');
        setIsConfirming(false);
        return;
      }

      setTxHash(tx.hash);
      await handleConfirmPayment(tx.hash);
    } catch (err: any) {
      const msg = err?.code === 4001
        ? 'Transaction rejected by user.'
        : `Transaction failed: ${err?.shortMessage || err?.message || 'Unknown error'}`;
      setErrorMessage(msg);
      setIsConfirming(false);
    }
  };

  const handleConfirmPayment = async (
    hash?: string,
    opts?: { testConfirmations?: number; silentPending?: boolean },
  ) => {
    const finalHash = hash || txHash || (verifyStub ? `0x${'ab'.repeat(32)}` : '');
    if (!finalHash) return;

    setIsConfirming(true);
    if (!opts?.silentPending) setErrorMessage('');

    try {
      const result = await api.confirmPayment(paymentInfo.payment_id, finalHash, {
        testConfirmations: opts?.testConfirmations,
      });
      setPaymentInfo((prev: any) => ({ ...prev, ...result }));
      setStep('success');
    } catch (err: unknown) {
      if (err instanceof ApiRequestError && err.status === 409) {
        const payload = err.detailPayload;
        if (payload?.status === 'pending_confirmation') {
          const conf = Number(payload.confirmations ?? 0);
          const required = Number(payload.required_confirmations ?? minConfirmations);
          setPendingConfirmations(conf);
          setMinConfirmations(required);
          setTxHash(finalHash);
          setStep('awaiting_confirmations');
          return;
        }
      }
      const detail =
        err instanceof ApiRequestError
          ? err.message
          : (err as { message?: string })?.message || 'On-chain verification failed';
      setErrorMessage(detail);
      setStep('error');
    } finally {
      setIsConfirming(false);
    }
  };

  const handleCopyAddress = async () => {
    if (paymentInfo?.wallet_address) {
      const success = await copyToClipboard(paymentInfo.wallet_address);
      if (success) {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    }
  };

  const explorerUrl = (hash: string, chain: string) => {
    const config = chainConfig[chain];
    if (config) return `${config.explorer}${hash}`;
    if (chain === 'solana') return `https://solscan.io/tx/${hash}`;
    return '#';
  };

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="glass border-b border-white/10 sticky top-0 z-50">
        <div className="max-w-4xl mx-auto px-4 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors">
            <ArrowLeft className="w-4 h-4" />
            <span className="text-sm">Back to Store</span>
          </Link>
          <div className="flex items-center gap-2">
            <ShoppingCart className="w-5 h-5 text-indigo-400" />
            <span className="text-sm text-gray-400">Checkout</span>
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center mb-12"
        >
          <h1 className="text-4xl font-bold text-white mb-3">
            <span className="text-gradient">Crypto</span> Checkout
          </h1>
          <p className="text-gray-400">
            Pay with USDT, USDC, or ETH on your preferred blockchain
          </p>
          {paymentTestnet && (
            <p className="mt-3 text-sm text-amber-300">
              Testnet mode — use Sepolia / Base Sepolia funds only
              {verifyStub ? ' (stub confirmations enabled for drills)' : ''}
            </p>
          )}
        </motion.div>

        {/* Wallet Status */}
        <div className="max-w-lg mx-auto mb-6">
          {walletAddress ? (
            <div className="flex items-center justify-between glass p-3 rounded-xl">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-emerald-400" />
                <span className="text-sm text-gray-300 font-mono">
                  {truncateAddress(walletAddress)}
                </span>
              </div>
              <button
                onClick={disconnectWallet}
                className="text-xs text-gray-500 hover:text-red-400 transition-colors"
              >
                Disconnect
              </button>
            </div>
          ) : (
            <Button
              className="w-full"
              variant="secondary"
              onClick={connectWallet}
              loading={isConnecting}
              icon={<Wallet className="w-4 h-4" />}
            >
              {isConnecting ? 'Connecting...' : 'Connect Wallet'}
            </Button>
          )}
          {walletError && (
            <p className="text-xs text-red-400 mt-2">{walletError}</p>
          )}
        </div>

        {step === 'form' && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="max-w-lg mx-auto"
          >
            <GlassCard>
              <h2 className="text-xl font-semibold text-white mb-6">Payment Details</h2>

              <div className="space-y-6">
                {/* Product ID */}
                <Input
                  label="Product ID"
                  placeholder="Enter the product ID to purchase"
                  value={productId}
                  onChange={(e) => setProductId(e.target.value)}
                  icon={<ShoppingCart className="w-4 h-4" />}
                />
                {!customerEmail && (
                  <div className="glass rounded-xl p-4 space-y-3">
                    <p className="text-sm text-gray-300">Customer account is required for delivery</p>
                    <Input
                      label="Email"
                      placeholder="you@company.com"
                      value={authEmail}
                      onChange={(e) => setAuthEmail(e.target.value)}
                    />
                    <Input
                      label="Password"
                      type="password"
                      placeholder="Minimum 8 characters"
                      value={authPassword}
                      onChange={(e) => setAuthPassword(e.target.value)}
                    />
                    <div className="flex items-center gap-2">
                      <Button
                        variant="secondary"
                        onClick={() => setAuthMode(authMode === 'login' ? 'register' : 'login')}
                      >
                        Switch to {authMode === 'login' ? 'register' : 'login'}
                      </Button>
                      <Button onClick={handleCustomerAuth} loading={authLoading}>
                        {authMode === 'login' ? 'Login' : 'Register'}
                      </Button>
                    </div>
                  </div>
                )}
                {customerEmail && (
                  <div className="glass rounded-xl p-3 text-sm text-emerald-300">
                    Purchasing as {customerEmail}
                  </div>
                )}

                {/* Amount */}
                <Input
                  label={`Amount (${selectedToken})`}
                  type="number"
                  placeholder="10.00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  icon={<Wallet className="w-4 h-4" />}
                />

                {/* Chain Selection */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-3">
                    Blockchain Network
                  </label>
                  <div className="grid grid-cols-4 gap-2">
                    {supportedChains.map((chain) => (
                      <button
                        key={chain.id}
                        onClick={() => {
                          setSelectedChain(chain.id);
                          setSelectedToken(chain.tokens[0]);
                        }}
                        className={`p-3 rounded-xl text-center transition-all ${
                          selectedChain === chain.id
                            ? 'glass-strong border-indigo-500/50'
                            : 'glass hover:border-white/20'
                        }`}
                      >
                        <span className="text-2xl block mb-1">{chain.icon}</span>
                        <span className="text-xs text-gray-300">{chain.name}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Token Selection */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-3">
                    Token
                  </label>
                  <div className="flex gap-3">
                    {supportedChains.find((c) => c.id === selectedChain)?.tokens.map(
                      (token) => (
                        <button
                          key={token}
                          onClick={() => setSelectedToken(token)}
                          className={`flex-1 p-3 rounded-xl text-center transition-all ${
                            selectedToken === token
                              ? 'glass-strong border-indigo-500/50'
                              : 'glass hover:border-white/20'
                          }`}
                        >
                          <span className="text-sm font-medium text-gray-300">{token}</span>
                        </button>
                      )
                    )}
                  </div>
                </div>

                {errorMessage && (
                  <div className="flex items-start gap-3 p-3 rounded-xl bg-red-500/10 border border-red-500/20">
                    <AlertTriangle className="w-5 h-5 text-red-400 mt-0.5 shrink-0" />
                    <p className="text-sm text-red-300">{errorMessage}</p>
                  </div>
                )}

                <Button
                  className="w-full"
                  size="lg"
                  onClick={handleCreatePayment}
                  disabled={!productId || !amount || !customerEmail}
                  icon={<Wallet className="w-5 h-5" />}
                >
                  Pay {amount} {selectedToken}
                </Button>
              </div>
            </GlassCard>
          </motion.div>
        )}

        {step === 'payment' && paymentInfo && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="max-w-lg mx-auto"
          >
            <GlassCard>
              <div className="text-center mb-6">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-500 p-4 mx-auto mb-4">
                  <Wallet className="w-full h-full text-white" />
                </div>
                <h2 className="text-xl font-semibold text-white">Send Payment</h2>
                <p className="text-sm text-gray-400 mt-1">
                  Send exactly <strong>{paymentInfo.amount} {paymentInfo.currency}</strong> to the address below
                </p>
              </div>

              <div className="space-y-4">
                {/* Wallet Address */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Recipient Address ({paymentInfo.chain.toUpperCase()})
                  </label>
                  <div className="flex gap-2">
                    <div className="flex-1 glass p-3 rounded-xl">
                      <p className="text-xs font-mono text-gray-300 break-all">
                        {paymentInfo.wallet_address}
                      </p>
                    </div>
                    <button
                      onClick={handleCopyAddress}
                      className="p-3 rounded-xl glass hover:border-indigo-500/30 transition-all"
                    >
                      {copied ? (
                        <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                      ) : (
                        <Copy className="w-5 h-5 text-gray-400" />
                      )}
                    </button>
                  </div>
                </div>

                {/* Amount */}
                <div className="glass p-4 rounded-xl">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-400">Amount</span>
                    <span className="text-lg font-bold text-white">
                      {paymentInfo.amount} {paymentInfo.currency}
                    </span>
                  </div>
                </div>

                {/* Network fee notice */}
                <div className="flex items-start gap-3 p-3 rounded-xl bg-amber-500/10 border border-amber-500/20">
                  <AlertTriangle className="w-5 h-5 text-amber-400 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-sm text-amber-300">Network fees apply</p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      Make sure you have enough {paymentInfo.chain === 'solana' ? 'SOL' : 'ETH'} for gas fees.
                    </p>
                  </div>
                </div>

                {/* Send via Wallet (EVM chains) */}
                {walletAddress && chainConfig[paymentInfo.chain] && (
                  <Button
                    className="w-full"
                    size="lg"
                    onClick={handleSendTransaction}
                    loading={isConfirming}
                    icon={<Bitcoin className="w-5 h-5" />}
                  >
                    {isConfirming ? 'Sending...' : `Send ${paymentInfo.amount} ${paymentInfo.currency}`}
                  </Button>
                )}

                {/* Manual Transaction Hash Input (fallback / Solana) */}
                <div className="border-t border-white/10 pt-4">
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    {walletAddress && chainConfig[paymentInfo.chain]
                      ? 'Or enter transaction hash manually'
                      : 'Transaction Hash (after sending)'}
                  </label>
                  <Input
                    placeholder="0x... or Solana tx hash"
                    value={txHash}
                    onChange={(e) => setTxHash(e.target.value)}
                  />
                  <Button
                    className="w-full mt-3"
                    size="lg"
                    onClick={() => handleConfirmPayment()}
                    disabled={!txHash && !verifyStub}
                    loading={isConfirming}
                    icon={<CheckCircle2 className="w-5 h-5" />}
                  >
                    {isConfirming ? 'Verifying...' : 'Confirm Payment'}
                  </Button>
                  {verifyStub && paymentTestnet && (
                    <div className="mt-3 space-y-2">
                      <p className="text-xs text-amber-300/90">
                        Testnet drill: 1 confirmation → 409 pending; then finalize → license once.
                      </p>
                      <div className="flex gap-2">
                        <Button
                          variant="secondary"
                          className="flex-1"
                          onClick={() =>
                            handleConfirmPayment(txHash || `0x${'cd'.repeat(32)}`, {
                              testConfirmations: 1,
                            })
                          }
                        >
                          Stub: 1 conf
                        </Button>
                        <Button
                          variant="secondary"
                          className="flex-1"
                          onClick={() =>
                            handleConfirmPayment(txHash || `0x${'cd'.repeat(32)}`, {
                              testConfirmations: minConfirmations,
                            })
                          }
                        >
                          Stub: finalize
                        </Button>
                      </div>
                    </div>
                  )}
                </div>

                {errorMessage && (
                  <div className="flex items-start gap-3 p-3 rounded-xl bg-red-500/10 border border-red-500/20">
                    <AlertTriangle className="w-5 h-5 text-red-400 mt-0.5 shrink-0" />
                    <p className="text-sm text-red-300">{errorMessage}</p>
                  </div>
                )}
              </div>
            </GlassCard>
          </motion.div>
        )}

        {step === 'awaiting_confirmations' && paymentInfo && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="max-w-lg mx-auto"
          >
            <GlassCard>
              <motion.div className="text-center py-6">
                <Loader2 className="w-14 h-14 text-amber-400 mx-auto mb-4 animate-spin" />
                <h2 className="text-xl font-bold text-white mb-2">Awaiting confirmations</h2>
                <p className="text-gray-400 text-sm mb-4">
                  Payment seen on-chain ({pendingConfirmations}/{minConfirmations} confirmations).
                  We will issue your license once the chain finalizes.
                </p>
                <Button
                  className="w-full"
                  onClick={() => handleConfirmPayment(txHash, { silentPending: true })}
                  loading={isConfirming}
                >
                  Check again
                </Button>
                {verifyStub && (
                  <div className="mt-4 flex gap-2">
                    <Button
                      variant="secondary"
                      className="flex-1"
                      onClick={() =>
                        handleConfirmPayment(txHash || `0x${'ab'.repeat(32)}`, {
                          testConfirmations: minConfirmations,
                        })
                      }
                    >
                      Stub: finalize ({minConfirmations} conf)
                    </Button>
                  </div>
                )}
              </motion.div>
            </GlassCard>
          </motion.div>
        )}

        {step === 'confirming' && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="max-w-lg mx-auto text-center"
          >
            <GlassCard>
              <div className="py-8">
                <Loader2 className="w-16 h-16 text-indigo-400 mx-auto mb-6 animate-spin" />
                <h2 className="text-xl font-bold text-white mb-2">Confirming Payment</h2>
                <p className="text-gray-400">
                  Verifying your transaction on the blockchain...
                </p>
              </div>
            </GlassCard>
          </motion.div>
        )}

        {step === 'success' && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="max-w-lg mx-auto text-center"
          >
            <GlassCard>
              <div className="py-8">
                <div className="w-20 h-20 rounded-full bg-gradient-to-br from-emerald-500 to-green-500 p-5 mx-auto mb-6">
                  <CheckCircle2 className="w-full h-full text-white" />
                </div>
                <h2 className="text-2xl font-bold text-white mb-2">Payment Successful!</h2>
                <p className="text-gray-400 mb-2">
                  Your payment of {paymentInfo?.amount} {paymentInfo?.currency} has been confirmed on-chain.
                </p>
                {paymentInfo?.tx_hash && (
                  <p className="text-sm text-gray-500 mb-2">
                    Transaction: {truncateAddress(paymentInfo.tx_hash)}
                  </p>
                )}
                {paymentInfo?.confirmations !== undefined && (
                  <p className="text-xs text-gray-500 mb-6">
                    Confirmations: {paymentInfo.confirmations}
                  </p>
                )}
                {paymentInfo?.license_key && (
                  <p className="text-xs text-emerald-300 mb-2">License: {paymentInfo.license_key}</p>
                )}
                <div className="flex gap-3 justify-center">
                  <Button onClick={() => (window.location.href = '/')}>
                    Back to Store
                  </Button>
                  {paymentInfo?.order_id && (
                    <a href={`/account?order=${paymentInfo.order_id}`}>
                      <Button variant="secondary">Download Product</Button>
                    </a>
                  )}
                  {paymentInfo?.tx_hash && (
                    <a
                      href={explorerUrl(paymentInfo.tx_hash, paymentInfo.chain)}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <Button
                        variant="secondary"
                        icon={<ExternalLink className="w-4 h-4" />}
                      >
                        View on Explorer
                      </Button>
                    </a>
                  )}
                </div>
              </div>
            </GlassCard>
          </motion.div>
        )}

        {step === 'error' && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="max-w-lg mx-auto text-center"
          >
            <GlassCard>
              <div className="py-8">
                <div className="w-20 h-20 rounded-full bg-gradient-to-br from-red-500 to-orange-500 p-5 mx-auto mb-6">
                  <XCircle className="w-full h-full text-white" />
                </div>
                <h2 className="text-2xl font-bold text-white mb-2">Verification Failed</h2>
                <p className="text-gray-400 mb-4">{errorMessage || 'Could not verify the transaction on-chain.'}</p>
                <p className="text-sm text-gray-500 mb-6">
                  Make sure you sent the exact amount to the correct address and try again.
                </p>
                <div className="flex gap-3 justify-center">
                  <Button onClick={() => { setStep('payment'); setErrorMessage(''); }}>
                    Try Again
                  </Button>
                  <Button variant="secondary" onClick={() => (window.location.href = '/')}>
                    Back to Store
                  </Button>
                </div>
              </div>
            </GlassCard>
          </motion.div>
        )}
      </div>
    </div>
  );
}
