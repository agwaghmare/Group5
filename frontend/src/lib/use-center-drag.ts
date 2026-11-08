import {
  useRef,
  useState,
  type AnimationEvent,
  type PointerEvent,
} from "react";
import { shouldOpenFifthPage } from "@/lib/wheel-navigation";

export function useCenterDrag(onOpen: () => void) {
  const drag = useRef<{
    x: number;
    y: number;
    centerX: number;
    centerY: number;
    moved: boolean;
  } | null>(null);
  const suppressClick = useRef(false);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [opening, setOpening] = useState<{ x: number; y: number } | null>(null);

  return {
    offset,
    opening,
    suppressClick,
    handlers: {
      onPointerDown: (event: PointerEvent<HTMLElement>) => {
        if (event.button !== 0 || opening) return;
        const rect = event.currentTarget.getBoundingClientRect();
        suppressClick.current = false;
        drag.current = {
          x: event.clientX,
          y: event.clientY,
          centerX: rect.left + rect.width / 2,
          centerY: rect.top + rect.height / 2,
          moved: false,
        };
      },
      onPointerMove: (event: PointerEvent<HTMLElement>) => {
        if (!drag.current) return;
        const x = event.clientX - drag.current.x;
        const y = event.clientY - drag.current.y;
        if (Math.hypot(x, y) > 6) {
          drag.current.moved = true;
          suppressClick.current = true;
          event.currentTarget.setPointerCapture(event.pointerId);
        }
        if (!drag.current.moved) return;
        setOffset({ x, y });
      },
      onPointerUp: (event: PointerEvent<HTMLElement>) => {
        const current = drag.current;
        drag.current = null;
        if (!current) return;
        const x = current.centerX + event.clientX - current.x;
        const y = current.centerY + event.clientY - current.y;
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
      },
      onPointerCancel: () => {
        drag.current = null;
        setOffset({ x: 0, y: 0 });
      },
    },
    revealProps: opening
      ? {
          style: { left: opening.x, top: opening.y },
          onAnimationEnd: (event: AnimationEvent<HTMLDivElement>) => {
            if (event.target === event.currentTarget) onOpen();
          },
        }
      : null,
  };
}
