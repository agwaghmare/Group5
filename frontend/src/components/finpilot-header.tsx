import { Link } from "@tanstack/react-router";
import { CircleDot, Settings, UserCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

export function FinpilotHeader({ miniWheel = false, onHome, onWheelReturn }: { miniWheel?: boolean; onHome?: () => void; onWheelReturn?: () => void }) {
  return (
    <header className="flex items-center justify-between gap-2 px-2 pb-4 md:px-4">
      <Button asChild variant="ghost" className="h-auto p-0 font-display text-2xl font-extrabold hover:bg-transparent md:text-3xl">
        <Link to="/" onClick={onHome}>FIN<span className="text-primary">PILOT</span></Link>
      </Button>
      <nav className="flex items-center gap-1 text-muted-foreground sm:gap-4">
        {miniWheel && (onWheelReturn ? (
          <Button variant="ghost" size="icon" className="text-primary" title="Return to wheel navigation" aria-label="Return to wheel navigation" onClick={onWheelReturn}>
            <CircleDot />
          </Button>
        ) : (
          <Button asChild variant="ghost" size="icon" className="text-primary" title="Return to wheel navigation" aria-label="Return to wheel navigation">
            <Link to="/"><CircleDot /></Link>
          </Button>
        ))}
        <Button variant="ghost" aria-label="Settings"><Settings /><span className="hidden sm:inline">Settings</span></Button>
        <Button variant="ghost" aria-label="Profile"><UserCircle /><span className="hidden sm:inline">Profile</span></Button>
      </nav>
    </header>
  );
}