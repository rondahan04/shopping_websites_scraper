"use client";

import { useEffect, useRef } from "react";

const CELL = 14;

// Shell / scraping / coding themed character pool
const CHAR_POOL =
  "0123456789abcdefghijklmnopqrstuvwxyz$>_{}[];/|@#<%&?!";

// Longer "word" tokens that occasionally appear as sequential chars in a column
const WORDS = [
  "GET", "200", "curl", "html", "json", "grep",
  "wget", "POST", "null", "true", "http", "fetch",
  "pipe", "exec", "fork", "kill", "exit", "sudo",
];

function rchar(): string {
  // 8% chance to start a word token sequence — caller handles sequencing
  return CHAR_POOL[Math.floor(Math.random() * CHAR_POOL.length)];
}

function buildColChars(len: number): string[] {
  const out: string[] = [];
  while (out.length < len) {
    if (Math.random() < 0.12) {
      const word = WORDS[Math.floor(Math.random() * WORDS.length)];
      for (const ch of word) out.push(ch);
    } else {
      out.push(rchar());
    }
  }
  return out.slice(0, len);
}

type Col = {
  x: number;
  y: number;
  speed: number;
  length: number;
  chars: string[];
  muteTick: number;
};

export function MatrixBackground() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let w = 0;
    let h = 0;
    let cols: Col[] = [];

    const rebuild = () => {
      w = canvas.width  = window.innerWidth;
      h = canvas.height = window.innerHeight;
      const n = Math.ceil(w / CELL);
      cols = Array.from({ length: n }, (_, i) => ({
        x:        i * CELL,
        y:        Math.random() * -h,
        speed:    0.35 + Math.random() * 0.75,
        length:   Math.floor(10 + Math.random() * 28),
        chars:    buildColChars(40),
        muteTick: 0,
      }));
    };

    rebuild();
    window.addEventListener("resize", rebuild);

    let raf  = 0;
    let last = 0;
    const TARGET_MS = 1000 / 30; // throttle to ~30 fps for perf

    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      if (now - last < TARGET_MS) return;
      last = now;

      // Fade previous frame with semi-transparent overlay
      ctx.fillStyle = "rgba(2, 10, 8, 0.13)";
      ctx.fillRect(0, 0, w, h);

      ctx.font = `${CELL - 2}px 'Fira Code', 'Courier New', monospace`;

      for (const col of cols) {
        col.y += col.speed;
        col.muteTick++;

        // Occasionally mutate a random character in the column
        if (col.muteTick % 6 === 0) {
          const idx = Math.floor(Math.random() * col.chars.length);
          col.chars[idx] = rchar();
        }

        // Draw trail from head downward into past (j=0 = head, j=length = tail)
        for (let j = 0; j <= col.length; j++) {
          const cy = col.y - j * CELL;
          if (cy < -CELL || cy > h + CELL) continue;

          const ratio = 1 - j / col.length; // 1 at head, 0 at tail

          let color: string;
          if (j === 0) {
            // Head: near-white with #00FF41 tint
            color = "rgba(210, 255, 220, 0.97)";
          } else if (j < 3) {
            // Near-head: #00FF41 = rgb(0,255,65)
            color = `rgba(0, 255, 65, ${0.85 * ratio})`;
          } else {
            // Tail: fades toward dark #00FF41 (rgb 0,180,45 → 0,60,15)
            const g = Math.floor(60 + 195 * ratio);
            const b = Math.floor(10 + 55 * ratio);
            color = `rgba(0, ${g}, ${b}, ${0.55 * ratio})`;
          }

          ctx.fillStyle = color;
          const ci = (Math.floor(col.y / CELL) + j) % col.chars.length;
          ctx.fillText(col.chars[ci], col.x, cy);
        }

        // Reset column when it scrolls fully off-screen
        if (col.y - col.length * CELL > h) {
          col.y      = -(CELL * 3) - Math.random() * h * 0.6;
          col.speed  = 0.35 + Math.random() * 0.75;
          col.length = Math.floor(10 + Math.random() * 28);
          col.chars  = buildColChars(40);
        }
      }
    };

    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", rebuild);
    };
  }, []);

  return (
    <canvas
      ref={ref}
      aria-hidden="true"
      style={{
        position: "fixed",
        inset: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
        zIndex: 0,
        opacity: 0.28,
      }}
    />
  );
}
