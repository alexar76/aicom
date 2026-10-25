// Executes only against an explicitly supplied loopback validator. Wallets exist
// only in memory. No existing wallet, cluster config, deploy key or live RPC is read.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { Connection, Keypair, PublicKey, SystemProgram, Transaction, TransactionInstruction, sendAndConfirmTransaction, SYSVAR_SLOT_HASHES_PUBKEY } = require('@solana/web3.js');
const rpc = process.env.LOTTERY_LOCAL_RPC || 'http://127.0.0.1:18999';
const url = new URL(rpc);
if (url.protocol !== 'http:' || !['127.0.0.1','localhost','[::1]'].includes(url.hostname)) throw new Error('This test only allows a local validator');
const connection = new Connection(rpc, 'confirmed');
const program = new PublicKey('DT6QVF7HhCQTFRCcP7V6AJpQF6ZQzEc9LQSrq85MHpFD');
// Published throwaway seed: ONLY for this loopback genesis upgrade authority.
const authority=Keypair.fromSeed(Buffer.alloc(32,42)), oracle=Keypair.generate(), treasury=Keypair.generate(), buyer=Keypair.generate(), benefactor=Keypair.generate();
const u64 = n => { const b=Buffer.alloc(8); b.writeBigUInt64LE(BigInt(n)); return b; };
const disc = name => crypto.createHash('sha256').update(`global:${name}`).digest().subarray(0,8);
const pda = (...seeds) => PublicKey.findProgramAddressSync(seeds,program)[0];
const config=pda(Buffer.from('lottery_config'));
const loader=new PublicKey('BPFLoaderUpgradeab1e11111111111111111111111');
const programData=PublicKey.findProgramAddressSync([program.toBuffer()],loader)[0];
const rw=(pubkey,isSigner=false)=>({pubkey,isWritable:true,isSigner});
const ro=(pubkey,isSigner=false)=>({pubkey,isWritable:false,isSigner});
const system=ro(SystemProgram.programId);
function ix(name,keys,args=Buffer.alloc(0)) { return new TransactionInstruction({programId:program,keys,data:Buffer.concat([disc(name),args])}); }
async function send(instruction,signers=[]) {
 return sendAndConfirmTransaction(connection,new Transaction().add(instruction),[authority,...signers.filter(k=>k!==authority)],{commitment:'confirmed'});
}
async function reject(instruction,signers=[]) { await assert.rejects(()=>send(instruction,signers)); }
async function read(pubkey) { const account=await connection.getAccountInfo(pubkey); assert(account); return account.data; }
function roundKeys(id) { const rid=u64(id); return {round:pda(Buffer.from('round'),rid),vault:pda(Buffer.from('vault'),rid),ticket:pda(Buffer.from('ticket'),rid,buyer.publicKey.toBuffer())}; }
async function open(id) {
 const k=roundKeys(id); await send(ix('open_round',[rw(authority.publicKey,true),rw(config),rw(k.round),rw(k.vault),system],u64(id))); return k;
}
async function buy(k) {
 const count=Buffer.alloc(4);count.writeUInt32LE(10);
 await send(ix('buy_tickets',[rw(buyer.publicKey,true),ro(config),rw(k.round),rw(k.ticket),rw(k.vault),system],count),[buyer]);
}
async function fund(k) { await send(ix('fund',[rw(benefactor.publicKey,true),rw(config),rw(k.round),rw(k.vault),system],u64(10_000)),[benefactor]); }
async function close(k,extraSystem) {
 await send(ix('close_vault',[rw(authority.publicKey,true),ro(config),ro(k.round),rw(k.vault),...(extraSystem?[system]:[])]));
}
(async()=>{
 console.log('Local validator:',await connection.getVersion());
 for (const payer of [authority,oracle,treasury,buyer,benefactor]) { const signature=await connection.requestAirdrop(payer.publicKey,2_000_000_000); await connection.confirmTransaction(signature,'confirmed'); }
 const args=Buffer.alloc(14);args.writeBigUInt64LE(1000n);args.writeUInt16LE(7000,8);args.writeUInt16LE(2000,10);args.writeUInt16LE(1000,12);
 await reject(ix('initialize',[rw(buyer.publicKey,true),ro(oracle.publicKey),ro(treasury.publicKey),rw(config),system,ro(programData)],args),[buyer]);
 await send(ix('initialize',[rw(authority.publicKey,true),ro(oracle.publicKey),ro(treasury.publicKey),rw(config),system,ro(programData)],args));
 console.log('Only the loader upgrade authority may initialize; front-running rejected');
 console.log('Initialize and open, tickets and benefactor funding');
 const first=await open(1); await buy(first); await fund(first);
 assert.equal((await read(first.round)).readBigUInt64LE(39),10_000n);
 assert.equal((await read(first.round)).readBigUInt64LE(47),10_000n);
 const seed=Buffer.alloc(32,7),commitment=crypto.createHash('sha256').update(seed).digest();
 await send(ix('close_round',[ro(authority.publicKey,true),ro(config),rw(first.round)],commitment));
 const drawSlot=Number((await read(first.round)).readBigUInt64LE(153));
 const deadline=Date.now()+45_000;
 while(await connection.getSlot('confirmed')<=drawSlot) { if(Date.now()>deadline)throw new Error('Local validator did not reach pinned slot');await new Promise(r=>setTimeout(r,250)); }
 const drawKeys=[ro(oracle.publicKey,true),rw(config),rw(first.round),ro(first.ticket),ro(SYSVAR_SLOT_HASHES_PUBKEY)];
 await reject(ix('fulfill_draw',drawKeys,Buffer.alloc(32,6)),[oracle]);
 await reject(ix('fulfill_draw',[ro(authority.publicKey,true),...drawKeys.slice(1)],seed));
 await send(ix('fulfill_draw',drawKeys,seed),[oracle]);
 let data=await read(first.round);assert.equal(data[16],3);assert.equal(data.readBigUInt64LE(63),14_000n);assert.equal(data.readBigUInt64LE(169),4000n);assert.equal(data.readBigUInt64LE(177),2000n);
 console.log('Pinned draw accepted; invalid oracle and commitment rejected');
 const claim=ix('claim_prize',[rw(buyer.publicKey,true),rw(first.round),rw(first.vault),system]);
 const winnerBefore=await connection.getBalance(buyer.publicKey);
 await reject(ix('claim_prize',[rw(authority.publicKey,true),rw(first.round),rw(first.vault),system]));
 await send(claim,[buyer]);assert.equal(await connection.getBalance(buyer.publicKey)-winnerBefore,14_000);
 await reject(claim,[buyer]);
 const treasuryBefore=await connection.getBalance(treasury.publicKey);
 const withdraw=ix('withdraw_residual',[ro(authority.publicKey,true),ro(config),rw(first.round),rw(treasury.publicKey),rw(first.vault),system]);
 await send(withdraw);assert.equal(await connection.getBalance(treasury.publicKey)-treasuryBefore,6000);await reject(withdraw);
 const reserve=Number((await read(first.round)).readBigUInt64LE(161));assert.equal(await connection.getBalance(first.vault),reserve);
 if(process.argv.includes('--expect-close-failure')) {
   await assert.rejects(()=>close(first,false),error=>{ console.log('Confirmed legacy close_vault runtime failure:',error.message);return /instruction spent from the balance of an account it does not own/i.test(error.message); });
   console.log('Verified legacy close_vault failure after successful real SBF payouts');return;
 }
 await close(first,true);assert.equal(await connection.getAccountInfo(first.vault),null);
 console.log('Settlement payouts, replay guards and vault reserve closure passed');
 const second=await open(2);await buy(second);await fund(second);
 await send(ix('cancel_round',[ro(authority.publicKey,true),ro(config),rw(second.round)]));
 const ticketRent=(await connection.getAccountInfo(second.ticket)).lamports;
 const beforeRefund=await connection.getBalance(buyer.publicKey);
 const refund=ix('refund_ticket',[rw(second.round),rw(buyer.publicKey),rw(second.ticket),rw(second.vault),system]);
 await send(refund);assert.equal(await connection.getBalance(buyer.publicKey)-beforeRefund,10_000+ticketRent);assert.equal(await connection.getAccountInfo(second.ticket),null);await reject(refund);
 const beforeReclaim=await connection.getBalance(treasury.publicKey);
 const reclaim=ix('reclaim_funding',[ro(authority.publicKey,true),ro(config),rw(second.round),rw(treasury.publicKey),rw(second.vault),system]);
 await send(reclaim);assert.equal(await connection.getBalance(treasury.publicKey)-beforeReclaim,10_000);await reject(reclaim);await close(second,true);assert.equal(await connection.getAccountInfo(second.vault),null);
 console.log('Cancellation, permissionless buyer refund, funding reclaim and vault closure passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
