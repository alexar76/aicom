import { SIWxPayloadSchema, type SIWxPayload } from "@x402/extensions/sign-in-with-x";
import type { SIWxPayload as CjsPayload } from "@x402/extensions/sign-in-with-x" with { "resolution-mode": "require" };
import { PaymentRequiredSchema, PaymentPayloadSchema } from "@x402/core/schemas";

const payload: SIWxPayload = {
  domain: "seller.example", address: "0x1234", uri: "https://seller.example/",
  version: "1", chainId: "eip155:8453", type: "eip191", nonce: "test",
  issuedAt: new Date().toISOString(), signature: "0x1234", resources: ["https://seller.example/order"],
};
const cjs: CjsPayload = payload;
const signature: string = SIWxPayloadSchema.parse(cjs).signature;
const parsed = PaymentPayloadSchema.parse({});
PaymentRequiredSchema.safeParse({});
void signature;
void parsed;
