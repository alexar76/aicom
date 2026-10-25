const {test}=require('node:test');
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
const {Keypair,PublicKey,SystemProgram,Transaction,TransactionMessage,VersionedTransaction}=require('@solana/web3.js');
const {BorshInstructionCoder,BN}=require('@anchor-lang/core');
const {u64,u128,u256}=require('@solana/buffer-layout-utils');

test('legacy and versioned SOL transfer signatures match independent Ed25519 and message vectors',()=>{
  const seed=Buffer.alloc(32,7);
  const kp=Keypair.fromSeed(seed);
  const privateKey=crypto.createPrivateKey({key:Buffer.concat([Buffer.from('302e020100300506032b657004220420','hex'),seed]),format:'der',type:'pkcs8'});
  const publicKey=crypto.createPublicKey(privateKey);
  assert.deepEqual(kp.publicKey.toBuffer(),publicKey.export({format:'der',type:'spki'}).subarray(-32));
  const recipient=new PublicKey(Buffer.alloc(32,8));
  const amount=123_456_789;
  const transfer=SystemProgram.transfer({fromPubkey:kp.publicKey,toPubkey:recipient,lamports:amount});
  const paymentBytes=Buffer.from('0200000015cd5b0700000000','hex');
  assert.deepEqual(transfer.data,paymentBytes);
  const message=Buffer.concat([Buffer.from([1,0,1,3]),kp.publicKey.toBuffer(),recipient.toBuffer(),Buffer.alloc(32),Buffer.alloc(32),Buffer.from([1,2,2,0,1,12]),paymentBytes]);
  const tx=new Transaction({feePayer:kp.publicKey,recentBlockhash:SystemProgram.programId.toBase58()}).add(transfer);
  assert.deepEqual(tx.serializeMessage(),message);
  tx.sign(kp);
  const independentSignature=crypto.sign(null,message,privateKey);
  assert.deepEqual(tx.signature,independentSignature);
  assert.equal(crypto.verify(null,message,publicKey,tx.signature),true);
  assert.deepEqual(tx.serialize(),Buffer.concat([Buffer.from([1]),independentSignature,message]));
  const tampered=Buffer.from(message);tampered[tampered.length-1]^=1;
  assert.equal(crypto.verify(null,tampered,publicKey,tx.signature),false);
  const v0=new TransactionMessage({payerKey:kp.publicKey,recentBlockhash:SystemProgram.programId.toBase58(),instructions:[transfer]}).compileToV0Message();
  const versioned=new VersionedTransaction(v0);versioned.sign([kp]);
  const v0Message=Buffer.concat([Buffer.from([128]),message,Buffer.from([0])]);
  assert.deepEqual(Buffer.from(versioned.message.serialize()),v0Message);
  assert.deepEqual(Buffer.from(versioned.signatures[0]),crypto.sign(null,v0Message,privateKey));
});

test('Anchor instruction coder and PDA derivation retain deployed lottery wire format',()=>{
  const idl={address:'DT6QVF7HhCQTFRCcP7V6AJpQF6ZQzEc9LQSrq85MHpFD',metadata:{name:'aimarket_lottery',version:'0.1.0',spec:'0.1.0'},instructions:[{name:'fund',discriminator:[218,188,111,221,152,113,174,7],accounts:[],args:[{name:'amount',type:'u64'}]}]};
  const coder=new BorshInstructionCoder(idl);
  assert.equal(coder.encode('fund',{amount:new BN('0807060504030201',16)}).toString('hex'),'dabc6fdd9871ae070102030405060708');
  const rid=Buffer.alloc(8);rid.writeBigUInt64LE(42n);
  const [key,bump]=PublicKey.findProgramAddressSync([Buffer.from('vault'),rid],new PublicKey(idl.address));
  assert.equal(key.toBase58(),'BPP5ipDhG8DcvKeyNxuux3JGYvm19Eat31zeHz4Ey3ij');assert.equal(bump,254);
});

test('real SPL layouts use the safe replacement without changing unsigned amount bytes',()=>{
  for(const [layout,width] of [[u64(),8],[u128(),16],[u256(),32]]) {
    const bytes=Buffer.alloc(width);const amount=(1n<<BigInt(width*8))-2n;
    assert.equal(layout.encode(amount,bytes,0),width);
    assert.equal(bytes.toString('hex'),'fe'+'ff'.repeat(width-1));
    assert.equal(layout.decode(bytes,0),amount);
  }
});
