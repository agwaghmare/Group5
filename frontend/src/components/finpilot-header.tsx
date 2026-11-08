import { Link, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { CircleDot, Settings, UserCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  useCustomerSession,
  writeCustomerSession,
} from "@/lib/customer-session";
import { writeStaffToken } from "@/lib/staff-api";

export function FinpilotHeader({
  miniWheel = false,
  onHome,
  onWheelReturn,
  onProfile,
  role,
  badge,
}: {
  miniWheel?: boolean;
  onHome?: () => void;
  onWheelReturn?: () => void;
  onProfile?: () => void;
  role?: string;
  badge?: string;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const customer = useCustomerSession();
  return (
    <header className="flex items-center justify-between gap-2 px-2 pb-4 md:px-4">
      <Button
        asChild
        variant="ghost"
        className="h-auto p-0 font-display text-2xl font-extrabold hover:bg-transparent md:text-3xl"
      >
        <Link to="/" onClick={onHome}>
          FIN<span className="text-primary">PILOT</span>
        </Link>
      </Button>
      <nav className="flex items-center gap-1 text-muted-foreground sm:gap-4">
        {role && (
          <span className="hidden text-xs font-bold uppercase tracking-wide text-primary sm:inline">
            {role}
          </span>
        )}
        {badge && (
          <span className="hidden text-xs uppercase tracking-wide sm:inline">
            {badge}
          </span>
        )}
        {miniWheel &&
          (onWheelReturn ? (
            <Button
              variant="ghost"
              size="icon"
              className="text-primary"
              title="Return to wheel navigation"
              aria-label="Return to wheel navigation"
              onClick={onWheelReturn}
            >
              <CircleDot />
            </Button>
          ) : (
            <Button
              asChild
              variant="ghost"
              size="icon"
              className="text-primary"
              title="Return to wheel navigation"
              aria-label="Return to wheel navigation"
            >
              <Link to="/">
                <CircleDot />
              </Link>
            </Button>
          ))}
        <Button variant="ghost" aria-label="Settings">
          <Settings />
          <span className="hidden sm:inline">Settings</span>
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              aria-label="Profile"
              className="outline-none"
            >
              <UserCircle />
              <span className="hidden sm:inline">Profile</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>
              <span className="block">
                {customer?.displayName ??
                  customer?.email ??
                  role ??
                  "Not signed in"}
              </span>
              {customer?.roleLabel && (
                <span className="block text-xs font-normal text-muted-foreground">
                  {customer.roleLabel}
                </span>
              )}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {onProfile && (
              <DropdownMenuItem onSelect={onProfile}>
                Account details
              </DropdownMenuItem>
            )}
            {customer ? (
              <DropdownMenuItem
                onSelect={() => {
                  if (customer.token)
                    void fetch("/api/v1/auth/session", {
                      method: "DELETE",
                      headers: { Authorization: `Bearer ${customer.token}` },
                    }).catch(() => undefined);
                  queryClient.clear();
                  writeCustomerSession(null);
                  writeStaffToken(null);
                  void navigate({ to: "/login" });
                }}
              >
                Sign out
              </DropdownMenuItem>
            ) : (
              <DropdownMenuItem
                onSelect={() => void navigate({ to: "/login" })}
              >
                Sign in
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </nav>
    </header>
  );
}
