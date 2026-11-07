export function reachesCenter(x: number, y: number, width: number, height: number) {
  return Math.hypot(x - width / 2, y - height / 2) <= Math.min(width, height) * 0.16;
}

export function shouldOpenFifthPage(phase: "move" | "drop" | "cancel", moved: boolean, x: number, y: number, width: number, height: number) {
  return phase === "drop" && moved && reachesCenter(x, y, width, height);
}