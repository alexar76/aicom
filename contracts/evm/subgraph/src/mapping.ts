import { Address, BigInt, Bytes, ethereum } from "@graphprotocol/graph-ts";

import {
  ChannelDebited,
  ChannelExpiredAndSettled,
  ChannelOpened,
  ChannelRefunded,
  ChannelSettled,
  HubAuthorized,
  TokenWhitelisted,
} from "../generated/AIMarketEscrow/AIMarketEscrow";
import { Channel, Debit, Hub, Refund, Settlement, Token } from "../generated/schema";

const ZERO = BigInt.fromI32(0);

function eventId(event: ethereum.Event): string {
  return event.transaction.hash.toHexString() + "-" + event.logIndex.toString();
}

function closeChannel(channel: Channel, status: string, event: ethereum.Event): void {
  channel.status = status;
  channel.closedAt = event.block.timestamp;
  channel.closedTx = event.transaction.hash;
}

export function handleChannelOpened(event: ChannelOpened): void {
  const channel = new Channel(event.params.channelId.toHexString());
  channel.depositor = event.params.depositor;
  channel.token = event.params.token;
  channel.depositAmount = event.params.depositAmount;
  channel.balance = event.params.depositAmount;
  channel.usedAmount = ZERO;
  channel.expiresAt = event.params.expiresAt;
  channel.status = "Open";
  channel.debitCount = 0;
  channel.openedAt = event.block.timestamp;
  channel.openedTx = event.transaction.hash;
  channel.save();
}

export function handleChannelDebited(event: ChannelDebited): void {
  const id = event.params.channelId.toHexString();
  const channel = Channel.load(id);
  // A debit can only follow an open, so a miss means the manifest's startBlock
  // is after the channel's opening. Skip rather than invent a channel whose
  // deposit/depositor we would have to make up.
  if (channel == null) {
    return;
  }

  const debit = new Debit(eventId(event));
  debit.channel = id;
  debit.amount = event.params.amount;
  debit.receiptId = event.params.receiptId;
  debit.remainingBalance = event.params.remainingBalance;
  debit.timestamp = event.block.timestamp;
  debit.blockNumber = event.block.number;
  debit.tx = event.transaction.hash;
  debit.save();

  channel.balance = event.params.remainingBalance;
  channel.usedAmount = channel.usedAmount.plus(event.params.amount);
  channel.debitCount = channel.debitCount + 1;
  channel.save();
}

export function handleChannelSettled(event: ChannelSettled): void {
  const id = event.params.channelId.toHexString();
  const channel = Channel.load(id);
  if (channel == null) {
    return;
  }

  const settlement = new Settlement(eventId(event));
  settlement.channel = id;
  settlement.usedAmount = event.params.usedAmount;
  settlement.refundAmount = event.params.refundAmount;
  // The contract reports address(0) when nothing was used; keep that as "no
  // recipient" instead of indexing the zero address as if it were paid.
  settlement.usedRecipient = event.params.usedRecipient.equals(Address.zero())
    ? null
    : changetype<Bytes>(event.params.usedRecipient);
  settlement.refundRecipient = changetype<Bytes>(event.params.refundRecipient);
  settlement.viaExpiry = false;
  settlement.timestamp = event.block.timestamp;
  settlement.blockNumber = event.block.number;
  settlement.tx = event.transaction.hash;
  settlement.save();

  // This log is the only place the bound hub is ever named.
  if (!event.params.usedRecipient.equals(Address.zero())) {
    channel.hub = changetype<Bytes>(event.params.usedRecipient);
  }
  channel.balance = ZERO;
  closeChannel(channel, "Settled", event);
  channel.save();
}

export function handleChannelRefunded(event: ChannelRefunded): void {
  const id = event.params.channelId.toHexString();
  const channel = Channel.load(id);
  if (channel == null) {
    return;
  }

  const refund = new Refund(eventId(event));
  refund.channel = id;
  refund.amount = event.params.amount;
  refund.reason = event.params.reason;
  refund.timestamp = event.block.timestamp;
  refund.blockNumber = event.block.number;
  refund.tx = event.transaction.hash;
  refund.save();

  channel.balance = ZERO;
  closeChannel(channel, "Refunded", event);
  channel.save();
}

export function handleChannelExpiredAndSettled(event: ChannelExpiredAndSettled): void {
  const id = event.params.channelId.toHexString();
  const channel = Channel.load(id);
  if (channel == null) {
    return;
  }

  // Expiry has the same economics as settleChannel — the hub is paid its
  // accumulated usedAmount and only the remainder goes back — but the event
  // names neither party. The depositor is known from ChannelOpened; the hub is
  // only known if a settlement already revealed it, so it stays null otherwise
  // rather than being guessed from the transaction sender (expiry is
  // permissionless: anyone can send it).
  const settlement = new Settlement(eventId(event));
  settlement.channel = id;
  settlement.usedAmount = event.params.usedAmount;
  settlement.refundAmount = event.params.refundAmount;
  settlement.usedRecipient = event.params.usedAmount.equals(ZERO) ? null : channel.hub;
  settlement.refundRecipient = channel.depositor;
  settlement.viaExpiry = true;
  settlement.timestamp = event.block.timestamp;
  settlement.blockNumber = event.block.number;
  settlement.tx = event.transaction.hash;
  settlement.save();

  channel.balance = ZERO;
  closeChannel(channel, "Expired", event);
  channel.save();
}

export function handleHubAuthorized(event: HubAuthorized): void {
  const id = event.params.hub.toHexString();
  let hub = Hub.load(id);
  if (hub == null) {
    hub = new Hub(id);
  }
  hub.authorized = event.params.authorized;
  hub.updatedAt = event.block.timestamp;
  hub.save();
}

export function handleTokenWhitelisted(event: TokenWhitelisted): void {
  const id = event.params.token.toHexString();
  let token = Token.load(id);
  if (token == null) {
    token = new Token(id);
  }
  token.whitelisted = event.params.whitelisted;
  token.updatedAt = event.block.timestamp;
  token.save();
}
