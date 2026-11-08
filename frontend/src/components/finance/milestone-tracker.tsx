import { useMemo, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { num, money, type Snapshot } from "@/lib/finance-api";

/* ─── Types ─── */
type MilestoneState = "locked" | "in_progress" | "completed";

interface Milestone {
  id: string;
  title: string;
  description: string;
  icon: string;
  xp: number;
  credits: number;
  badge: string;
  target: number;
  current: number;
  state: MilestoneState;
  completedDate?: string | undefined;
  celebrationText?: string | undefined;
  progressLabel?: string | undefined;
  eligibilityNote?: string | undefined;
}

interface RewardItem {
  id: string;
  title: string;
  description: string;
  icon: string;
  cost: number;
  type: "badge" | "theme" | "title" | "cashback";
}

/* ─── Persistence ─── */
const CLAIMED_KEY = "finpilot.milestones.claimed";
const REDEEMED_KEY = "finpilot.rewards.redeemed";
function loadSet(key: string): Set<string> {
  try { return new Set(JSON.parse(sessionStorage.getItem(key) ?? "[]")); } catch { return new Set(); }
}
function saveSet(key: string, s: Set<string>) {
  sessionStorage.setItem(key, JSON.stringify([...s]));
}

/* ─── XP → Level ─── */
const LEVELS = [
  { min: 0, label: "Beginner", tier: 1 },
  { min: 500, label: "Saver", tier: 2 },
  { min: 1200, label: "Builder", tier: 3 },
  { min: 2200, label: "Money Hero", tier: 4 },
  { min: 3500, label: "Finance Master", tier: 5 },
];
function getLevel(xp: number) {
  let lvl = LEVELS[0]!;
  for (const l of LEVELS) if (xp >= l.min) lvl = l;
  const next = LEVELS[LEVELS.indexOf(lvl) + 1];
  return { ...lvl, xpToNext: next ? next.min - xp : 0, nextMin: next?.min ?? lvl.min };
}

/* ─── Rewards catalog ─── */
const REWARDS: RewardItem[] = [
  { id: "badge-first-saver", title: "First Saver Badge", description: "Profile badge for your first savings milestone", icon: "🏅", cost: 50, type: "badge" },
  { id: "cashback-dine", title: "3% dine-in cashback", description: "Earn 3% back on all dine-in purchases", icon: "🍽️", cost: 75, type: "cashback" },
  { id: "theme-midnight", title: "Midnight Theme", description: "Unlock the midnight blue color theme", icon: "🌙", cost: 150, type: "theme" },
  { id: "title-money-wizard", title: "Money Wizard Title", description: "Special achievement title on your profile", icon: "🧙", cost: 200, type: "title" },
  { id: "cashback-5", title: "$5 Demo Cashback", description: "A demo cashback voucher for your account", icon: "💵", cost: 100, type: "cashback" },
  { id: "badge-debt-crusher", title: "Debt Crusher Badge", description: "Badge for paying off a credit card", icon: "💪", cost: 75, type: "badge" },
  { id: "title-budget-boss", title: "Budget Boss Title", description: "Title for staying under budget consistently", icon: "👑", cost: 250, type: "title" },
  { id: "theme-emerald", title: "Emerald Glow Theme", description: "Unlock the emerald accent theme", icon: "💎", cost: 300, type: "theme" },
];

/* ─── Milestone definitions ─── */
function buildMilestones(latest: Snapshot, history: Snapshot[], claimed: Set<string>): Milestone[] {
  const savings = num(latest.savings_balance);
  const creditUse = num(latest.credit_utilization);
  const emergencyMonths = num(latest.emergency_fund_months);
  const totalDebt = num(latest.total_debt_balance);
  const monthlyIncome = num(latest.monthly_income);
  const budgetUnderCount = history.filter((s) => num(s.budget_variance_pct) <= 0).length;
  const positiveCashFlowCount = history.filter((s) => num(s.projected_balance_30d) > 0).length;

  function ms(id: string, title: string, desc: string, icon: string, xp: number, credits: number, badge: string, current: number, target: number, eligible: boolean, opts?: { celebration?: string; progressLabel?: string; note?: string }): Milestone {
    const done = eligible && current >= target;
    return {
      id, title, description: desc, icon, xp, credits, badge, target,
      current: Math.min(current, target),
      state: done && claimed.has(id) ? "completed" : done ? "in_progress" : current > 0 ? "in_progress" : "locked",
      completedDate: done && claimed.has(id) ? latest.date : undefined,
      celebrationText: done && claimed.has(id) ? opts?.celebration : undefined,
      progressLabel: opts?.progressLabel,
      eligibilityNote: opts?.note,
    };
  }

  const emergencyTarget = monthlyIncome * 3;

  return [
    ms("save-1000", "Save your first $1,000", "Reach $1,000 in savings balance", "💰", 250, 100, "$1,000\nSaved", savings, 1000, true,
      { celebration: "YAAYYY!! Earned 100 FinPilot Credits", progressLabel: `${money(savings)} / ${money(1000)}` }),
    ms("credit-700", "Reach a 700+ credit score", "Keep credit utilization under 30%", "📊", 300, 75, "700+\nCredit Score", creditUse <= 0.3 ? 700 : Math.round(700 * (1 - creditUse)), 700, true,
      { celebration: "Unlocked 3% dine-in cashback 🎉", note: "Estimated from utilization. A verified bureau score is required for production." }),
    ms("emergency-3mo", "Build a 3-month emergency fund", "Save ~3 months of your essential expenses.", "🛡️", 350, 100, "3-Month\nEmergency Fund",
      emergencyMonths, 3, true,
      { progressLabel: `${money(savings)} / ${money(emergencyTarget)}` }),
    ms("payoff-card", "Pay off one credit card", "Clear the balance on any one of your credit cards.", "💳", 400, 100, "Pay Off\nCredit Card",
      totalDebt <= 0 ? 1 : 0, 1, true,
      { progressLabel: totalDebt > 0 ? `${money(Math.max(0, 3000 - totalDebt))} / ${money(3000)}` : "Paid off!" }),
    ms("budget-3mo", "Keep spending under budget for 3 months", "Stay within your monthly budget for 3 consecutive months.", "📉", 300, 75, "3 Months\nUnder Budget",
      budgetUnderCount, 3, history.length >= 3,
      { progressLabel: `${budgetUnderCount * 30} / 90 days` }),
    ms("cashflow-3mo", "Maintain a positive cash flow for 3 months", "Projected balance stays positive for 3+ months.", "📈", 300, 75, "Positive\nCash Flow",
      positiveCashFlowCount, 3, history.length >= 3,
      { progressLabel: `${positiveCashFlowCount} / 3 months` }),
  ];
}

/* ─── Confetti ─── */
function Confetti({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <div className="pointer-events-none fixed inset-0 z-50 overflow-hidden">
      {Array.from({ length: 50 }).map((_, i) => (
        <div key={i} className="absolute animate-bounce"
          style={{ left: `${Math.random() * 100}%`, top: `-${Math.random() * 20}%`,
            animationDelay: `${Math.random() * 0.6}s`, animationDuration: `${1.5 + Math.random()}s`,
            fontSize: `${14 + Math.random() * 14}px`, opacity: 0.9 }}>
          {["🎉", "⭐", "🏆", "✨", "💎", "🎊"][i % 6]}
        </div>
      ))}
    </div>
  );
}

/* ═══════════════════════════════════════════ MAIN ═══════════════════════════════════════════ */
export function MilestoneTracker({ latest, history }: { latest: Snapshot; history: Snapshot[] }) {
  const [claimed, setClaimed] = useState(() => loadSet(CLAIMED_KEY));
  const [redeemed, setRedeemed] = useState(() => loadSet(REDEEMED_KEY));
  const [celebrating, setCelebrating] = useState(false);

  const milestones = useMemo(() => buildMilestones(latest, history, claimed), [latest, history, claimed]);
  const totalXp = milestones.filter((m) => m.state === "completed").reduce((s, m) => s + m.xp, 0);
  const totalCredits = milestones.filter((m) => m.state === "completed").reduce((s, m) => s + m.credits, 0);
  const spentCredits = REWARDS.filter((r) => redeemed.has(r.id)).reduce((s, r) => s + r.cost, 0);
  const availableCredits = totalCredits - spentCredits;
  const level = getLevel(totalXp);
  const completedCount = milestones.filter((m) => m.state === "completed").length;
  const streakDays = Math.round(num(latest.savings_streak_months) * 30);
  const nextRewardCredits = 250;
  const milestonesLeft = milestones.filter((m) => m.state !== "completed").length;

  const claimMilestone = useCallback((id: string) => {
    if (claimed.has(id)) return;
    const next = new Set(claimed); next.add(id);
    setClaimed(next); saveSet(CLAIMED_KEY, next);
    setCelebrating(true);
    setTimeout(() => setCelebrating(false), 2200);
  }, [claimed]);

  const redeemReward = useCallback((id: string) => {
    const reward = REWARDS.find((r) => r.id === id);
    if (!reward || redeemed.has(id) || availableCredits < reward.cost) return;
    const next = new Set(redeemed); next.add(id);
    setRedeemed(next); saveSet(REDEEMED_KEY, next);
  }, [redeemed, availableCredits]);

  const unlockedPerks = REWARDS.filter((r) => redeemed.has(r.id));

  return (
    <div className="flex flex-col gap-6">
      <Confetti show={celebrating} />

      {/* ═══ HERO HEADER ═══ */}
      <div className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-[#0a2a1a] to-[#0d1f15] p-6">
        {/* Mountain deco */}
        <div className="pointer-events-none absolute -right-4 -top-4 text-[80px] opacity-20 select-none">🏔️</div>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="font-display text-2xl font-extrabold md:text-3xl">
              Milestone Tracker <span className="inline-block animate-bounce text-2xl">🌿</span>
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">Level up your financial life</p>
          </div>
          <div className="flex items-center gap-3">
            {/* XP pill */}
            <div className="flex items-center gap-2 rounded-full border border-primary/40 bg-primary/15 px-4 py-2">
              <span className="text-base">⭐</span>
              <div>
                <p className="font-display text-base font-extrabold text-primary leading-none">{totalXp.toLocaleString()} XP</p>
                <p className="text-[9px] text-muted-foreground">{level.xpToNext > 0 ? `${level.xpToNext} XP to Level ${level.tier + 1}` : "Max level!"}</p>
              </div>
            </div>
            {/* Level pill */}
            <div className="flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-4 py-2">
              <span className="text-base">🏆</span>
              <div>
                <p className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Level {level.tier}</p>
                <p className="font-display text-sm font-extrabold leading-none">{level.label}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ═══ QUEST ROADMAP ═══ */}
      <div className="rounded-2xl border border-border bg-card p-5">
        {/* Roadmap icons */}
        <div className="flex items-start">
          {milestones.map((m, i) => (
            <div key={m.id} className="flex flex-1 flex-col items-center">
              <div className={`relative flex size-10 items-center justify-center rounded-full border-2 text-lg transition-all
                ${m.state === "completed" ? "border-primary bg-primary/20 shadow-[0_0_12px_rgba(134,239,172,0.3)]" : m.state === "in_progress" ? "border-primary/60 bg-card" : "border-muted/40 bg-muted/20"}`}>
                {m.state === "completed" ? "✅" : m.icon}
              </div>
              <p className={`mt-2 text-center text-[9px] font-bold leading-tight ${m.state === "completed" ? "text-primary" : "text-muted-foreground"}`}>
                {m.badge.split("\n").map((line, j) => <span key={j}>{line}<br /></span>)}
              </p>
            </div>
          ))}
          {/* Next reward node */}
          <div className="flex flex-1 flex-col items-center">
            <div className="flex size-10 items-center justify-center rounded-full border-2 border-yellow-500/40 bg-yellow-500/10 text-lg">🎁</div>
            <p className="mt-2 text-center text-[9px] font-bold leading-tight text-yellow-500">Next Reward<br />+{nextRewardCredits} Credits</p>
          </div>
        </div>
        {/* Progress line */}
        <div className="mx-5 mt-3">
          <div className="h-1.5 overflow-hidden rounded-full bg-muted/30">
            <div className="h-full rounded-full bg-gradient-to-r from-primary to-primary/60 transition-all duration-700"
              style={{ width: `${Math.min(100, (completedCount / milestones.length) * 100)}%` }} />
          </div>
        </div>
      </div>

      {/* ═══ TWO-COLUMN: MILESTONES + REWARDS ═══ */}
      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        {/* ─── Left: Milestone list ─── */}
        <div className="space-y-3">
          {milestones.map((m) => {
            const pctDone = m.target > 0 ? Math.round((m.current / m.target) * 100) : 0;
            const claimable = pctDone >= 100 && m.state !== "completed";
            return (
              <div key={m.id} className={`group rounded-2xl border p-4 transition-all
                ${m.state === "completed" ? "border-primary/40 bg-gradient-to-r from-primary/8 to-transparent" : "border-border bg-card hover:border-border/80"}`}>
                <div className="flex items-start gap-3">
                  {/* Icon */}
                  <div className={`flex size-10 shrink-0 items-center justify-center rounded-xl text-xl
                    ${m.state === "completed" ? "bg-primary/20" : "bg-secondary"}`}>
                    {m.state === "completed" ? "✅" : m.icon}
                  </div>
                  {/* Content */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <h4 className="font-display text-sm font-bold">{m.title}</h4>
                      {m.state === "completed" && (
                        <span className="shrink-0 rounded-md bg-primary/20 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-primary">
                          ✅ Completed
                        </span>
                      )}
                      {claimable && (
                        <Button size="sm" className="h-7 shrink-0 animate-pulse rounded-lg px-3 text-xs" onClick={() => claimMilestone(m.id)}>
                          🎉 Claim
                        </Button>
                      )}
                    </div>
                    {m.state === "completed" && m.celebrationText && (
                      <p className="mt-1 rounded-md bg-primary/10 px-2 py-1 text-[10px] font-bold text-primary">
                        🎉 {m.celebrationText}
                      </p>
                    )}
                    {m.state !== "completed" && (
                      <>
                        <p className="mt-0.5 text-xs text-muted-foreground">{m.description}</p>
                        <div className="mt-2 flex items-center gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="h-2 overflow-hidden rounded-full bg-muted/30">
                              <div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${pctDone}%` }} />
                            </div>
                          </div>
                          <span className="shrink-0 text-xs font-bold tabular-nums text-muted-foreground">{pctDone}%</span>
                        </div>
                        {m.progressLabel && (
                          <p className="mt-1 text-right text-[10px] text-muted-foreground">{m.progressLabel}</p>
                        )}
                      </>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* ─── Right: Rewards Wallet ─── */}
        <div className="space-y-4">
          {/* Wallet header card */}
          <div className="rounded-2xl border border-border bg-card p-5">
            <div className="mb-4 flex items-center gap-2">
              <span className="text-xl">🏆</span>
              <div>
                <h3 className="font-display text-sm font-bold">Rewards Wallet</h3>
                <p className="text-[10px] text-muted-foreground">Your earned perks &amp; progress</p>
              </div>
            </div>

            {/* Level section */}
            <div className="mb-4 rounded-xl border border-primary/20 bg-primary/5 p-4">
              <div className="flex items-center gap-3">
                <div className="flex size-12 items-center justify-center rounded-xl bg-primary/20 text-2xl">🏆</div>
                <div className="flex-1">
                  <p className="font-display text-lg font-extrabold">Level {level.tier}</p>
                  <p className="text-xs font-bold text-primary">{level.label}</p>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted/30">
                    <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${level.nextMin > 0 ? Math.min(100, (totalXp / level.nextMin) * 100) : 100}%` }} />
                  </div>
                  <p className="mt-1 text-[9px] text-muted-foreground">{totalXp.toLocaleString()} / {level.nextMin.toLocaleString()} XP</p>
                </div>
              </div>
            </div>

            {/* Credits + Cashback row */}
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-border bg-secondary/30 p-3 text-center">
                <p className="font-display text-2xl font-extrabold text-primary">{availableCredits}</p>
                <p className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">FinPilot Credits</p>
              </div>
              <div className="rounded-xl border border-border bg-secondary/30 p-3 text-center">
                <p className="font-display text-2xl font-extrabold">{redeemed.has("cashback-dine") ? "3%" : "—"}</p>
                <p className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">
                  {redeemed.has("cashback-dine") ? "Dine-in Cashback\n(Unlocked)" : "Dine-in Cashback"}
                </p>
              </div>
            </div>
          </div>

          {/* Perks Unlocked */}
          <div className="rounded-2xl border border-border bg-card p-5">
            <h4 className="mb-3 font-display text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground">Perks Unlocked</h4>
            {unlockedPerks.length === 0 ? (
              <p className="text-xs text-muted-foreground/60">Redeem credits below to unlock perks.</p>
            ) : (
              <div className="space-y-2">
                {unlockedPerks.map((r) => (
                  <div key={r.id} className="flex items-center justify-between rounded-lg border border-primary/20 bg-primary/5 px-3 py-2">
                    <span className="flex items-center gap-2 text-xs font-bold">
                      {r.icon} {r.title}
                    </span>
                    <span className="rounded-full bg-primary/20 px-2 py-0.5 text-[8px] font-bold uppercase text-primary">
                      {r.type === "cashback" ? "Active" : "Earned"}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Redeem shop */}
          <div className="rounded-2xl border border-border bg-card p-5">
            <h4 className="mb-3 font-display text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground">Redeem Credits</h4>
            <div className="grid grid-cols-2 gap-2">
              {REWARDS.map((r) => {
                const owned = redeemed.has(r.id);
                const canAfford = availableCredits >= r.cost;
                return (
                  <div key={r.id} className={`flex flex-col rounded-xl border p-3 transition-all ${owned ? "border-primary/30 bg-primary/5" : "border-border"}`}>
                    <div className="mb-1 text-xl">{r.icon}</div>
                    <p className="text-[11px] font-bold">{r.title}</p>
                    <p className="mt-0.5 flex-1 text-[9px] text-muted-foreground">{r.description}</p>
                    <div className="mt-2 flex items-center justify-between">
                      <span className="text-[10px] font-bold text-primary">🪙 {r.cost}</span>
                      {owned ? (
                        <span className="text-[8px] font-bold text-primary">Owned</span>
                      ) : (
                        <Button size="sm" variant={canAfford ? "default" : "outline"} disabled={!canAfford}
                          className="h-6 rounded-md px-2 text-[10px]" onClick={() => redeemReward(r.id)}>
                          {canAfford ? "Redeem" : "🔒"}
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* ═══ BOTTOM BAR: NEXT REWARD ═══ */}
      <div className="sticky bottom-0 z-10 rounded-2xl border border-border bg-gradient-to-r from-[#0a2a1a] to-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="flex size-10 items-center justify-center rounded-xl bg-primary/20 text-xl">🎁</div>
            <div>
              <p className="font-display text-sm font-bold">Next Reward</p>
              <p className="text-[10px] text-muted-foreground">Complete {milestonesLeft} more milestone{milestonesLeft !== 1 ? "s" : ""} to unlock</p>
            </div>
            <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-3 py-1.5">
              <p className="text-xs font-bold text-yellow-400">+{nextRewardCredits} FinPilot Credits</p>
              <p className="text-[9px] text-yellow-500/70">+ a special Level {level.tier + 1} badge 🌟</p>
            </div>
          </div>
          <Button className="rounded-xl px-6 font-display font-bold" size="lg">
            Start Next Milestone →
          </Button>
        </div>
      </div>

      {/* Streak badge (floating) */}
      {streakDays > 0 && (
        <div className="pointer-events-none fixed right-6 top-20 z-20 flex items-center gap-2 rounded-full border border-yellow-500/30 bg-yellow-500/10 px-3 py-1.5 backdrop-blur-sm">
          <span>🔥</span>
          <p className="text-xs font-bold text-yellow-400">{streakDays}-day streak</p>
        </div>
      )}
    </div>
  );
}
