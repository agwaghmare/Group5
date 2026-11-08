/**
 * CoinForge: create custom SPL tokens on Devnet, mint, transfer, view history.
 * All operations require wallet approval. No real value is created.
 */
import { Connection, Keypair, PublicKey, Transaction, SystemProgram } from "@solana/web3.js";
import {
  createInitializeMintInstruction,
  createAssociatedTokenAccountInstruction,
  createMintToInstruction,
  createTransferInstruction,
  getAssociatedTokenAddress,
  getMint,
  getAccount,
  MINT_SIZE,
  TOKEN_PROGRAM_ID,
} from "@solana/spl-token";

export interface ForgedToken {
  mintAddress: string;
  name: string;
  symbol: string;
  decimals: number;
  supply: number;
  createdAt: number;
  creator: string;
}

export interface TokenTransfer {
  id: string;
  mint: string;
  from: string;
  to: string;
  amount: number;
  signature: string;
  timestamp: number;
  status: "confirmed" | "failed";
}

const TOKENS_KEY = "finpilot.coinforge.tokens";
const TRANSFERS_KEY = "finpilot.coinforge.transfers";

export function getForgedTokens(): ForgedToken[] {
  try { return JSON.parse(sessionStorage.getItem(TOKENS_KEY) ?? "[]"); } catch { return []; }
}
function saveTokens(t: ForgedToken[]) { sessionStorage.setItem(TOKENS_KEY, JSON.stringify(t)); }

export function getTokenTransfers(): TokenTransfer[] {
  try { return JSON.parse(sessionStorage.getItem(TRANSFERS_KEY) ?? "[]"); } catch { return []; }
}
function saveTransfers(t: TokenTransfer[]) { sessionStorage.setItem(TRANSFERS_KEY, JSON.stringify(t)); }

export async function createToken(
  connection: Connection,
  provider: any,
  creator: PublicKey,
  opts: { name: string; symbol: string; decimals: number; initialSupply: number },
): Promise<ForgedToken> {
  const mintKeypair = Keypair.generate();

  const lamports = await connection.getMinimumBalanceForRentExemption(MINT_SIZE);
  const { blockhash } = await connection.getLatestBlockhash();

  const tx = new Transaction();
  tx.add(
    SystemProgram.createAccount({
      fromPubkey: creator,
      newAccountPubkey: mintKeypair.publicKey,
      space: MINT_SIZE,
      lamports,
      programId: TOKEN_PROGRAM_ID,
    }),
    createInitializeMintInstruction(mintKeypair.publicKey, opts.decimals, creator, creator),
  );

  // Create ATA and mint initial supply
  const ata = await getAssociatedTokenAddress(mintKeypair.publicKey, creator);
  tx.add(createAssociatedTokenAccountInstruction(creator, ata, creator, mintKeypair.publicKey));

  const supplyRaw = BigInt(Math.round(opts.initialSupply * 10 ** opts.decimals));
  tx.add(createMintToInstruction(mintKeypair.publicKey, ata, creator, supplyRaw));

  tx.feePayer = creator;
  tx.recentBlockhash = blockhash;
  tx.partialSign(mintKeypair);

  const signed = await provider.signTransaction(tx);
  const sig = await connection.sendRawTransaction(signed.serialize());
  await connection.confirmTransaction(sig, "confirmed");

  const token: ForgedToken = {
    mintAddress: mintKeypair.publicKey.toBase58(),
    name: opts.name,
    symbol: opts.symbol,
    decimals: opts.decimals,
    supply: opts.initialSupply,
    createdAt: Date.now(),
    creator: creator.toBase58(),
  };

  const all = getForgedTokens();
  all.unshift(token);
  saveTokens(all);

  return token;
}

export async function transferToken(
  connection: Connection,
  provider: any,
  sender: PublicKey,
  recipientAddr: string,
  mintAddr: string,
  amount: number,
  decimals: number,
): Promise<TokenTransfer> {
  const mint = new PublicKey(mintAddr);
  const recipient = new PublicKey(recipientAddr);

  const senderAta = await getAssociatedTokenAddress(mint, sender);
  const recipientAta = await getAssociatedTokenAddress(mint, recipient);

  const tx = new Transaction();

  // Ensure recipient ATA exists
  try {
    await getAccount(connection, recipientAta);
  } catch {
    tx.add(createAssociatedTokenAccountInstruction(sender, recipientAta, recipient, mint));
  }

  const raw = BigInt(Math.round(amount * 10 ** decimals));
  tx.add(createTransferInstruction(senderAta, recipientAta, sender, raw));

  tx.feePayer = sender;
  const { blockhash } = await connection.getLatestBlockhash();
  tx.recentBlockhash = blockhash;

  const signed = await provider.signTransaction(tx);
  const sig = await connection.sendRawTransaction(signed.serialize());
  await connection.confirmTransaction(sig, "confirmed");

  const transfer: TokenTransfer = {
    id: sig,
    mint: mintAddr,
    from: sender.toBase58(),
    to: recipientAddr,
    amount,
    signature: sig,
    timestamp: Date.now(),
    status: "confirmed",
  };

  const all = getTokenTransfers();
  all.unshift(transfer);
  saveTransfers(all);

  return transfer;
}
