import { FinpilotHeader } from "@/components/finpilot-header";

const PLANS = [
  {
    name: "Free",
    price: "$0",
    cadence: "Included now",
    status: "Yours now",
    featured: false,
    items: [
      "Home, Wallet, Finance, and Learn on the wheel",
      "My Money, Bills, Savings, Loans & Health, and What If",
      "Amelia explains the numbers already on your tracker",
      "Milestones, XP, and the rewards wallet",
      "Test payments and CoinForge on this machine",
      "Lessons and plain-word explanations of your own figures",
    ],
  },
  {
    name: "Plus",
    price: "$8",
    cadence: "per month, when it ships",
    status: "Next",
    featured: true,
    items: [
      "A reminder before a bill is due",
      "A household view you can share without opening the whole file",
      "A payday rule that sets savings aside",
      "A weekly spoken brief of what changed",
      "A date on each savings goal",
      "Receipts that land in the bill list you already have",
    ],
  },
  {
    name: "Pro",
    price: "$18",
    cadence: "per month, when it ships",
    status: "The full cockpit",
    featured: false,
    items: [
      "A real account in place of the sample tracker",
      "A move between your own accounts, only after you approve it",
      "A refinance watch on the loan in What If",
      "Credit changes explained from your own utilization",
      "Recurring charges found and ready to review",
      "A person at PNC when the picture looks wrong",
      "Tax money set aside from each paycheck",
      "Family accounts with allowances",
    ],
  },
] as const;

export function CustomerPlans({ onReturn }: { onReturn: () => void }) {
  return (
    <div className="relative flex h-dvh flex-col overflow-hidden bg-background p-4 md:p-6">
      <FinpilotHeader miniWheel onWheelReturn={onReturn} badge="Customer" />
      <main className="fifth-page-enter flex min-h-0 flex-1 flex-col overflow-y-auto rounded-[2rem] border border-border px-6 py-8 md:px-10">
        <p className="font-display text-sm font-bold uppercase tracking-[0.3em] text-primary">
          05 — Plans
        </p>
        <h1 className="mt-3 max-w-3xl font-display text-4xl font-extrabold leading-[0.95] md:text-6xl">
          Start free. Grow the cockpit.
        </h1>
        <p className="mt-4 max-w-xl text-base text-muted-foreground">
          Free is everything on your wheel today. Plus and Pro are the next
          reasons to stay. Nothing is charged in this demo.
        </p>
        <div className="mt-8 grid gap-4 lg:grid-cols-3">
          {PLANS.map((plan) => (
            <article
              key={plan.name}
              className={`flex flex-col rounded-2xl border p-5 ${
                plan.name === "Pro"
                  ? "border-primary/80 bg-zinc-950 text-zinc-50 shadow-[0_0_36px_-10px] shadow-primary/80 ring-1 ring-primary/40"
                  : plan.featured
                    ? "border-primary bg-primary/5"
                    : "border-border"
              }`}
            >
              <p
                className="font-display text-xs font-bold uppercase tracking-[0.2em] text-primary"
              >
                {plan.status}
              </p>
              <h2 className="mt-3 font-display text-3xl font-extrabold">
                {plan.name}
              </h2>
              <p className="mt-2 font-display text-4xl font-extrabold leading-none">
                {plan.price}
                {plan.price !== "$0" && (
                  <span className="ml-1 text-base font-bold opacity-70">
                    /mo
                  </span>
                )}
              </p>
              <p
                className={`mt-2 text-sm ${plan.name === "Pro" ? "text-zinc-400" : "text-muted-foreground"}`}
              >
                {plan.cadence}
              </p>
              <ul className="mt-6 space-y-3 text-sm">
                {plan.items.map((item) => (
                  <li key={item} className="flex gap-2">
                    <span aria-hidden="true">{plan.name === "Free" ? "✓" : "＋"}</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </main>
    </div>
  );
}
