import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CoinForgeTab } from "@/components/wallet/coinforge-tab";

const mocks = vi.hoisted(() => ({ forgeToken: vi.fn(), sendToken: vi.fn(), getHistory: vi.fn() }));
vi.mock("@/lib/solana/wallet-context", () => ({ useWallet: () => ({
  connected: true, publicKey: "local-wallet", provider: null, mode: "server", network: "localnet", ...mocks,
}) }));
vi.mock("@/components/wallet/wallet-connect", () => ({ WalletConnect: () => null }));
vi.mock("@/lib/solana/coinforge", () => ({ getForgedTokens: () => [], getTokenTransfers: () => [] }));

const coin = { mintAddress: "test-mint", name: "My Coin", symbol: "MYC", decimals: 6, supply: 100, createdAt: 1, creator: "local-wallet" };
afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  mocks.getHistory.mockResolvedValue({ tokens: [], transfers: [], payments: [] });
  mocks.forgeToken.mockResolvedValue(coin);
  mocks.sendToken.mockResolvedValue({ id: "tx1", signature: "tx1", mint: "test-mint", from: "local-wallet", to: "recipient", amount: 2, timestamp: 1, status: "confirmed" });
});

describe("CoinForge local wallet", () => {
  it("creates and sends custom currency without a Phantom provider", async () => {
    const { container } = render(<CoinForgeTab />);
    await waitFor(() => expect(mocks.getHistory).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText("FinPilot Coin"), { target: { value: "My Coin" } });
    fireEvent.change(screen.getByPlaceholderText("FPC"), { target: { value: "MYC" } });
    fireEvent.click(screen.getByRole("button", { name: /Forge Token/ }));
    await screen.findByText(/Created MYC/);
    expect(mocks.forgeToken).toHaveBeenCalledWith({ name: "My Coin", symbol: "MYC", decimals: 9, initialSupply: 1000000 });
    fireEvent.change(screen.getByPlaceholderText("Recipient Solana public key"), { target: { value: "recipient" } });
    fireEvent.change(container.querySelector('input[step="1"]')!, { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Send Token" }));
    await waitFor(() => expect(mocks.sendToken).toHaveBeenCalledWith("test-mint", "recipient", 2, 6));
    await screen.findByText(/Sent!/);
    expect(container.querySelector('a[href*="explorer.solana.com"]')).toBeNull();
  });

  it("restores coins from backend history when the tab opens", async () => {
    mocks.getHistory.mockResolvedValue({ tokens: [coin], transfers: [], payments: [] });
    render(<CoinForgeTab />);
    await screen.findByText("My Coin (MYC)");
    expect(screen.getByRole("option", { name: "MYC — My Coin" })).toBeTruthy();
  });

  it("shows the backend error when creating a coin fails", async () => {
    mocks.forgeToken.mockRejectedValue(new Error("Validator unavailable"));
    render(<CoinForgeTab />);
    await waitFor(() => expect(mocks.getHistory).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText("FinPilot Coin"), { target: { value: "My Coin" } });
    fireEvent.change(screen.getByPlaceholderText("FPC"), { target: { value: "MYC" } });
    fireEvent.click(screen.getByRole("button", { name: /Forge Token/ }));
    await screen.findByText(/Validator unavailable/);
  });
});
