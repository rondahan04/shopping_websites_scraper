"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Obstacle = { x: number; w: number; h: number; kind: "bug" | "semi" | "brace" };

const GRAVITY = 0.38;
const JUMP = -11.8;

/** Frames until max difficulty (~30s at 60fps) — stays chill for a while. */
const RAMP_FRAMES = 1800;
const GRACE_FRAMES = 150;
const SPEED_MIN = 2;
const SPEED_MAX = 5.5;
const GAP_MIN_EARLY = 320;
const GAP_MIN_LATE = 150;
const GAP_SPREAD_EARLY = 160;
const GAP_SPREAD_LATE = 70;
/** Shrink collision boxes so near-misses count as clears. */
const HIT_INSET = 8;

type Difficulty = {
  speed: number;
  gapMin: number;
  gapSpread: number;
  clusterChance: number;
};

function getDifficulty(score: number): Difficulty {
  const t = Math.min(1, score / RAMP_FRAMES);
  const ease = Math.sqrt(t);
  const speed = SPEED_MIN + (SPEED_MAX - SPEED_MIN) * ease;
  const gapMin = GAP_MIN_EARLY - (GAP_MIN_EARLY - GAP_MIN_LATE) * ease;
  const gapSpread =
    GAP_SPREAD_EARLY - (GAP_SPREAD_EARLY - GAP_SPREAD_LATE) * ease;
  const clusterChance = ease < 0.7 ? 0 : (ease - 0.7) * 0.12;
  return { speed, gapMin, gapSpread, clusterChance };
}

function maybeSpawnObstacles(
  obstacles: Obstacle[],
  canvasWidth: number,
  diff: Difficulty,
  score: number,
): Obstacle[] {
  if (score < GRACE_FRAMES) {
    return obstacles;
  }

  const next = [...obstacles];
  const last = next[next.length - 1];
  const spawnLine = canvasWidth - diff.gapMin;

  if (last && last.x > spawnLine) {
    return next;
  }

  const anchorX = last ? last.x : canvasWidth;
  const gap = diff.gapMin + Math.random() * diff.gapSpread;
  next.push(randomObstacle(anchorX + gap));

  if (Math.random() < diff.clusterChance) {
    const clusterGap = 48 + Math.random() * 36;
    next.push(randomObstacle(anchorX + gap + clusterGap));
  }

  return next;
}

function randomObstacle(x: number): Obstacle {
  const roll = Math.random();
  const kind: Obstacle["kind"] =
    roll < 0.55 ? "semi" : roll < 0.85 ? "brace" : "bug";
  const h = kind === "brace" ? 24 : 20;
  const w = kind === "semi" ? 12 : kind === "brace" ? 18 : 22;
  return { x, w, h, kind };
}

function hitsObstacle(
  playerX: number,
  playerW: number,
  playerTop: number,
  playerH: number,
  groundY: number,
  o: Obstacle,
): boolean {
  const oy = groundY - o.h;
  const inset = HIT_INSET;
  return (
    playerX + playerW - inset > o.x + inset &&
    playerX + inset < o.x + o.w - inset &&
    playerTop + playerH - inset > oy + inset &&
    playerTop + inset < groundY
  );
}

function drawObstacle(
  ctx: CanvasRenderingContext2D,
  o: Obstacle,
  groundY: number,
) {
  ctx.fillStyle = "#ff6b4a";
  if (o.kind === "bug") {
    ctx.font = "18px ui-monospace, monospace";
    ctx.fillText("bug", o.x, groundY - 4);
  } else if (o.kind === "semi") {
    ctx.font = "bold 22px ui-monospace, monospace";
    ctx.fillText(";", o.x, groundY - 2);
  } else {
    ctx.font = "20px ui-monospace, monospace";
    ctx.fillText("}", o.x, groundY - 4);
  }
}

export function WaitGame() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [score, setScore] = useState(0);
  const [best, setBest] = useState(0);
  const [over, setOver] = useState(false);
  const stateRef = useRef({
    running: true,
    playerY: 0,
    vy: 0,
    grounded: true,
    obstacles: [] as Obstacle[],
    frame: 0,
    score: 0,
  });

  const reset = useCallback(() => {
    const s = stateRef.current;
    s.playerY = 0;
    s.vy = 0;
    s.grounded = true;
    s.obstacles = [];
    s.frame = 0;
    s.score = 0;
    s.running = true;
    setScore(0);
    setOver(false);
  }, []);

  const jump = useCallback(() => {
    const s = stateRef.current;
    if (!s.running) {
      reset();
      return;
    }
    if (s.grounded) {
      s.vy = JUMP;
      s.grounded = false;
    }
  }, [reset]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = 520;
    const h = 140;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    ctx.scale(dpr, dpr);

    const groundY = h - 18;
    const playerX = 48;
    const playerW = 36;
    const playerH = 28;

    let raf = 0;
    const loop = () => {
      const s = stateRef.current;
      ctx.clearRect(0, 0, w, h);

      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, "#0a2e2f");
      grad.addColorStop(1, "#0f3d3e");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);

      ctx.strokeStyle = "#7ee0d0";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(0, groundY);
      ctx.lineTo(w, groundY);
      ctx.stroke();

      if (s.running) {
        s.frame += 1;
        const diff = getDifficulty(s.score);

        s.vy += GRAVITY;
        s.playerY += s.vy;
        if (s.playerY >= 0) {
          s.playerY = 0;
          s.vy = 0;
          s.grounded = true;
        }

        s.obstacles = maybeSpawnObstacles(s.obstacles, w, diff, s.score);

        for (const o of s.obstacles) o.x -= diff.speed;
        s.obstacles = s.obstacles.filter((o) => o.x > -40);

        const py = groundY - playerH + s.playerY;
        for (const o of s.obstacles) {
          if (hitsObstacle(playerX, playerW, py, playerH, groundY, o)) {
            s.running = false;
            setOver(true);
            setBest((b) => Math.max(b, s.score));
            break;
          }
        }

        if (s.running) {
          s.score += 1;
          if (s.score % 10 === 0) setScore(s.score);
        }
      }

      const py = groundY - playerH + s.playerY;
      ctx.fillStyle = "#f5f0e6";
      ctx.fillRect(playerX, py + 8, playerW, playerH - 10);
      ctx.fillStyle = "#7ee0d0";
      ctx.fillRect(playerX + 4, py + 2, playerW - 8, 10);
      ctx.fillStyle = "#0f3d3e";
      ctx.font = "10px ui-monospace, monospace";
      ctx.fillText(">_ run", playerX + 6, py + 10);

      for (const o of s.obstacles) {
        drawObstacle(ctx, o, groundY);
      }

      raf = requestAnimationFrame(loop);
    };

    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code === "Space" || e.code === "ArrowUp") {
        e.preventDefault();
        jump();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [jump]);

  return (
    <div className="wait-game">
      <div className="wait-game-header">
        <span className="wait-game-title">While you wait: dodge the bugs</span>
        <span className="wait-game-score">
          Score: {score}
          {best > 0 && ` · Best: ${best}`}
        </span>
      </div>
      <canvas
        ref={canvasRef}
        className="wait-game-canvas"
        onClick={jump}
        role="img"
        aria-label="Mini game: press space or tap to jump over bugs and symbols"
      />
      <p className="wait-game-hint">
        {over
          ? "Ouch! Tap or press Space to try again."
          : "Space or tap to jump. Easy mode — wide gaps, floaty jumps, gentle ramp-up."}
      </p>
    </div>
  );
}
