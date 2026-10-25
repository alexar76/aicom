// Original @x402/extensions 2.28.0 SIWx schema. Regenerate only its Zod 4 declarations.
import { z } from "zod";
export const SIWxPayloadSchema = z.object({
  domain: z.string(),
  address: z.string(),
  statement: z.string().optional(),
  uri: z.string(),
  version: z.string(),
  chainId: z.string(),
  type: z.enum(["eip191", "ed25519"]),
  nonce: z.string(),
  issuedAt: z.string(),
  expirationTime: z.string().optional(),
  notBefore: z.string().optional(),
  requestId: z.string().optional(),
  resources: z.array(z.string()).optional(),
  signatureScheme: z.enum(["eip191", "eip1271", "eip6492", "siws"]).optional(),
  signature: z.string(),
});
