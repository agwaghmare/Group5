import { Link, useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { FinpilotHeader } from "@/components/finpilot-header";
import { Button } from "@/components/ui/button";
import { rememberFifth } from "@/lib/fifth-page";
import { shouldOpenFifthPage } from "@/lib/wheel-navigation";

const SECTIONS: {
  name: string;
  title: string;
  body: string;
  to?: "/finance" | "/learn" | "/wallet";
  cta?: string;
}[] = [
  {
    name: "Home",
    title: "Your money, piloted.",
    body: "Understand what you have, what you owe and what could happen next. Explore your financial picture, ask for plain-word explanations and choose a next step with more confidence.",
  },
  {
    name: "Wallet",
    title: "Level up your finances.",
    body: "Build habits with milestones and rewards, practice test payments, or create a test currency of your own.",
    to: "/wallet",
    cta: "Open Wallet",
  },
  {
    name: "Finance",
    title: "See the whole runway.",
    body: "See cash, bills, savings, debt and investments together. Explore health indicators and what-if sliders, then ask Amelia for a plain-word review of your synthetic tracker.",
    to: "/finance",
    cta: "Open Finance",
  },
  {
    name: "Learn",
    title: "Learn it in plain words.",
    body: "Short lessons, a knowledge map, and explanations of your own numbers — APR, residual value, equity and more.",
    to: "/learn",
    cta: "Open Learn",
  },
];
const N = SECTIONS.length;
const STEP = 360 / N;

function Wheel({
  progress,
  onSelect,
  onCenter,
}: {
  progress: number;
  onSelect: (i: number) => void;
  onCenter: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const drag = useRef<{
    x: number;
    y: number;
    centerX: number;
    centerY: number;
    moved: boolean;
  } | null>(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [opening, setOpening] = useState<{ x: number; y: number } | null>(null);
  const suppressClick = useRef(false);
  const active = Math.round(progress);
  const size = 168,
    c = size / 2,
    rOut = 80,
    rIn = 44;

  const arc = (i: number) => {
    const a0 = ((i * STEP - STEP / 2 - 90 + 2) * Math.PI) / 180;
    const a1 = ((i * STEP + STEP / 2 - 90 - 2) * Math.PI) / 180;
    const p = (r: number, a: number) =>
      `${c + r * Math.cos(a)} ${c + r * Math.sin(a)}`;
    return `M ${p(rOut, a0)} A ${rOut} ${rOut} 0 0 1 ${p(rOut, a1)} L ${p(rIn, a1)} A ${rIn} ${rIn} 0 0 0 ${p(rIn, a0)} Z`;
  };

  return (
    <>
      <div
        ref={ref}
        aria-label="Draggable navigation wheel"
        className={`relative cursor-grab touch-none select-none rounded-full bg-background p-3 shadow-glow active:cursor-grabbing ${opening ? "pointer-events-none" : ""}`}
        style={{
          width: size + 24,
          height: size + 24,
          transform: `translate(${offset.x}px, ${offset.y}px)`,
        }}
        onPointerDown={(e) => {
          if (e.button !== 0 || opening) return;
          const rect = e.currentTarget.getBoundingClientRect();
          suppressClick.current = false;
          drag.current = {
            x: e.clientX,
            y: e.clientY,
            centerX: rect.left + rect.width / 2,
            centerY: rect.top + rect.height / 2,
            moved: false,
          };
        }}
        onPointerMove={(e) => {
          if (!drag.current) return;
          const x = e.clientX - drag.current.x;
          const y = e.clientY - drag.current.y;
          if (Math.hypot(x, y) > 6) {
            drag.current.moved = true;
            suppressClick.current = true;
            e.currentTarget.setPointerCapture(e.pointerId);
          }
          if (!drag.current.moved) return;
          setOffset({ x, y });
        }}
        onPointerUp={(e) => {
          const current = drag.current;
          drag.current = null;
          if (!current) return;
          const x = current.centerX + e.clientX - current.x;
          const y = current.centerY + e.clientY - current.y;
          if (
            shouldOpenFifthPage(
              "drop",
              current.moved,
              x,
              y,
              window.innerWidth,
              window.innerHeight,
            )
          ) {
            setOpening({ x, y });
            return;
          }
          setOffset({ x: 0, y: 0 });
        }}
        onPointerCancel={() => {
          drag.current = null;
          setOffset({ x: 0, y: 0 });
        }}
      >
        <svg
          className={opening ? "wheel-implode" : ""}
          width={size}
          height={size}
          style={{ transform: `rotate(${-progress * STEP}deg)` }}
        >
          {SECTIONS.map((s, i) => {
            const mid = ((i * STEP - 90) * Math.PI) / 180;
            const tr = (rOut + rIn) / 2;
            const isActive = i === active;
            return (
              <g
                key={s.name}
                role="button"
                aria-label={`Go to ${s.name}`}
                tabIndex={0}
                className="cursor-pointer outline-none focus:outline-none"
                style={{ outline: "none" }}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  if (!suppressClick.current) onSelect(i);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelect(i);
                  }
                }}
              >
                <path
                  d={arc(i)}
                  className={
                    isActive
                      ? "fill-primary stroke-primary"
                      : "fill-card stroke-border hover:fill-accent"
                  }
                  strokeWidth={1.5}
                />
                <text
                  x={c + tr * Math.cos(mid)}
                  y={c + tr * Math.sin(mid)}
                  textAnchor="middle"
                  dominantBaseline="central"
                  transform={`rotate(${i * STEP} ${c + tr * Math.cos(mid)} ${c + tr * Math.sin(mid)})`}
                  className={`font-display text-[10px] font-bold uppercase ${isActive ? "fill-primary-foreground" : "fill-muted-foreground"}`}
                >
                  {s.name}
                </text>
              </g>
            );
          })}
        </svg>
        <div className="pointer-events-none absolute inset-0 m-auto flex h-[76px] w-[76px] items-center justify-center rounded-full border border-border bg-background">
          <span className="px-1 text-center font-display text-[11px] font-bold uppercase leading-tight text-primary">
            {SECTIONS[active]?.name ?? SECTIONS[0]!.name}
          </span>
        </div>
      </div>
      {opening && (
        <div
          aria-hidden="true"
          className="wheel-page-reveal"
          style={{ left: opening.x, top: opening.y }}
          onAnimationEnd={(e) => {
            if (e.target === e.currentTarget) onCenter();
          }}
        />
      )}
    </>
  );
}

export function LandingPage() {
  const panel = useRef<HTMLDivElement>(null);
  const [progress, setProgress] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    const el = panel.current;
    if (!el) return;
    const onScroll = () => setProgress(el.scrollTop / el.clientHeight);
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  const goTo = useCallback((i: number) => {
    const el = panel.current;
    if (!el) return;
    el.scrollTo({ top: i * el.clientHeight, behavior: "smooth" });
  }, []);

  const active = Math.round(progress);

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background p-4 md:p-6">
      <FinpilotHeader onHome={() => goTo(0)} />

      <div className="relative min-h-0 flex-1 rounded-[2rem] border border-border">
        <div
          ref={panel}
          className="no-scrollbar h-full overflow-y-auto rounded-[2rem] snap-y snap-mandatory"
        >
          {SECTIONS.map((s, i) => (
            <section
              key={s.name}
              className="flex h-full snap-start flex-col justify-center px-8 pb-36 md:px-20 md:pl-64 md:pb-0"
            >
              <p className="mb-4 font-display text-sm font-bold uppercase tracking-[0.3em] text-primary">
                0{i + 1} — {s.name}
              </p>
              <h1
                className="max-w-3xl font-display text-5xl font-extrabold leading-[0.95] transition-all duration-500 md:text-7xl"
                style={{
                  opacity: i === active ? 1 : 0.2,
                  transform: `translateY(${(i - progress) * 40}px)`,
                }}
              >
                {s.title}
              </h1>
              <p className="mt-6 max-w-md text-lg text-muted-foreground">
                {s.body}
              </p>
              {s.to && (
                <Button asChild className="mt-8 w-fit" size="lg">
                  <Link to={s.to}>{s.cta ?? "Open"}</Link>
                </Button>
              )}
            </section>
          ))}
        </div>

        <div className="absolute -bottom-2 -left-2 z-10">
          <Wheel
            progress={progress}
            onSelect={goTo}
            onCenter={() => {
              rememberFifth("customer");
              void navigate({ to: "/page-five" });
            }}
          />
        </div>
      </div>
    </div>
  );
}
