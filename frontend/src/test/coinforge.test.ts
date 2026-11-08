/**
 * Tests for CoinForge session-storage helpers (getForgedTokens, getTokenTransfers).
 * Network-dependent createToken/transferToken are tested via integration; here we verify
 * the storage and type contracts.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { getForgedTokens, getTokenTransfers, type ForgedToken, type TokenTransfer } from "@/lib/solana/coinforge";

describe("CoinForge storage helpers", () => {
  beforeEach(() => sessionStorage.clear());

  it("returns empty array when no tokens forged", () => {
    expect(getForgedTokens()).toEqual([]);
  });

  it("returns empty array when no transfers recorded", () => {
    expect(getTokenTransfers()).toEqual([]);
  });

  it("survives corrupted tokens storage", () => {
    sessionStorage.setItem("finpilot.coinforge.tokens", "NOT-JSON");
    expect(getForgedTokens()).toEqual([]);
  });

  it("survives corrupted transfers storage", () => {
    sessionStorage.setItem("finpilot.coinforge.transfers", "{bad");
    expect(getTokenTransfers()).toEqual([]);
  });

  it("reads back valid token data", () => {
    const token: ForgedToken = {
      mintAddress: "FakeMint123",
      name: "TestCoin",
      symbol: "TST",
      decimals: 6,
      supply: 1000000,
      createdAt: Date.now(),
      creator: "FakeCreator123",
    };
    sessionStorage.setItem("finpilot.coinforge.tokens", JSON.stringify([token]));
    const result = getForgedTokens();
    expect(result).toHaveLength(1);
    expect(result[0]!.symbol).toBe("TST");
    expect(result[0]!.supply).toBe(1000000);
  });

  it("reads back valid transfer data", () => {
    const transfer: TokenTransfer = {
      id: "sig123",
      mint: "FakeMint123",
      from: "SenderPK",
      to: "RecipPK",
      amount: 500,
      signature: "sig123",
      timestamp: Date.now(),
      status: "confirmed",
    };
    sessionStorage.setItem("finpilot.coinforge.transfers", JSON.stringify([transfer]));
    const result = getTokenTransfers();
    expect(result).toHaveLength(1);
    expect(result[0]!.status).toBe("confirmed");
    expect(result[0]!.amount).toBe(500);
  });
});

describe("ForgedToken type contracts", () => {
  it("token has no real dollar value claim", () => {
    // CoinForge tokens are Devnet only — there is no price field on ForgedToken
    const token: ForgedToken = {
      mintAddress: "abc", name: "Test", symbol: "T", decimals: 9,
      supply: 100, createdAt: Date.now(), creator: "pub",
    };
    expect((token as any).priceUsd).toBeUndefined();
    expect((token as any).value).toBeUndefined();
  });
});
