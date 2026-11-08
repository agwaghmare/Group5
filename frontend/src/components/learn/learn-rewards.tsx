import { useQuery } from "@tanstack/react-query";
import { useCustomerSession } from "@/lib/customer-session";
import { learnApi } from "@/lib/learn-api";

export function LearnRewards() {
  const session = useCustomerSession();
  const rewards = useQuery({
    queryKey: ["learn", "rewards", session?.email, session?.token],
    queryFn: learnApi.rewards,
    enabled: Boolean(session?.token),
    retry: false,
  });
  return (
    <section aria-label="Learn to earn" className="mb-5 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-primary/30 bg-primary/5 p-4">
      <div>
        <h2 className="font-display font-bold">Learn to earn</h2>
        <p className="text-sm text-muted-foreground">Pass a lesson quiz with at least 80% to earn 0.1 FIN coins, once per lesson.</p>
        <p className="mt-1 text-xs text-muted-foreground">In-app learning points. No cash value or SOL transfer.</p>
      </div>
      <div className="text-right">
        {!session?.token ? <p className="text-sm">Sign in to earn coins.</p>
          : rewards.error ? <p role="alert" className="text-sm text-destructive">Could not load rewards. <button className="underline" onClick={() => void rewards.refetch()}>Retry</button></p>
          : <>
            <p className="font-display text-2xl font-bold">{rewards.data ? rewards.data.balance.toFixed(1) : "..."} FIN coins</p>
            <p className="text-xs text-muted-foreground">{rewards.data?.earned_lessons.length ?? 0} lessons rewarded</p>
          </>}
      </div>
    </section>
  );
}
