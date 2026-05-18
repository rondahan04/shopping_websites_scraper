"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Obstacle = { x: number; w: number; h: number; kind: "bug" | "semi" | "brace" };
type Particle = { x: number; y: number; vx: number; vy: number; life: number; maxLife: number };
type Star     = { x: number; y: number; speed: number; size: number; bright: number };

const GRAVITY = 0.38;
const JUMP = -11.8;
const RAMP_FRAMES = 1800;
const GRACE_FRAMES = 150;
const SPEED_MIN = 2;
const SPEED_MAX = 5.5;
const GAP_MIN_EARLY = 320;
const GAP_MIN_LATE = 150;
const GAP_SPREAD_EARLY = 160;
const GAP_SPREAD_LATE = 70;
const HIT_INSET = 8;
const STAR_COUNT = 50;

type Difficulty = { speed: number; gapMin: number; gapSpread: number; clusterChance: number };

function getDifficulty(score: number): Difficulty {
  const t    = Math.min(1, score / RAMP_FRAMES);
  const ease = Math.sqrt(t);
  return {
    speed:        SPEED_MIN + (SPEED_MAX - SPEED_MIN) * ease,
    gapMin:       GAP_MIN_EARLY - (GAP_MIN_EARLY - GAP_MIN_LATE) * ease,
    gapSpread:    GAP_SPREAD_EARLY - (GAP_SPREAD_EARLY - GAP_SPREAD_LATE) * ease,
    clusterChance: ease < 0.7 ? 0 : (ease - 0.7) * 0.12,
  };
}

function maybeSpawnObstacles(obstacles: Obstacle[], cw: number, diff: Difficulty, score: number): Obstacle[] {
  if (score < GRACE_FRAMES) return obstacles;
  const next = [...obstacles];
  const last = next[next.length - 1];
  if (last && last.x > cw - diff.gapMin) return next;
  const anchorX = last ? last.x : cw;
  const gap = diff.gapMin + Math.random() * diff.gapSpread;
  next.push(randomObstacle(anchorX + gap));
  if (Math.random() < diff.clusterChance) next.push(randomObstacle(anchorX + gap + 48 + Math.random() * 36));
  return next;
}

function randomObstacle(x: number): Obstacle {
  const roll = Math.random();
  const kind: Obstacle["kind"] = roll < 0.55 ? "semi" : roll < 0.85 ? "brace" : "bug";
  return { x, h: kind === "brace" ? 24 : 20, w: kind === "semi" ? 12 : kind === "brace" ? 18 : 22, kind };
}

function hitsObstacle(px: number, pw: number, pt: number, ph: number, groundY: number, o: Obstacle): boolean {
  const oy = groundY - o.h;
  const i  = HIT_INSET;
  return px + pw - i > o.x + i && px + i < o.x + o.w - i && pt + ph - i > oy + i && pt + i < groundY;
}

function initStars(count: number, w: number, h: number, groundY: number): Star[] {
  return Array.from({ length: count }, () => ({
    x:      Math.random() * w,
    y:      Math.random() * (groundY - 20),
    speed:  0.3 + Math.random() * 1.2,
    size:   Math.random() < 0.2 ? 1.5 : 0.8,
    bright: 0.3 + Math.random() * 0.7,
  }));
}

export function WaitGame() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [score, setScore]   = useState(0);
  const [best, setBest]     = useState(0);
  const [over, setOver]     = useState(false);
  const stateRef = useRef({
    running:   true,
    playerY:   0,
    vy:        0,
    grounded:  true,
    obstacles: [] as Obstacle[],
    particles: [] as Particle[],
    stars:     [] as Star[],
    frame:     0,
    score:     0,
  });

  const reset = useCallback(() => {
    const s      = stateRef.current;
    s.playerY    = 0;
    s.vy         = 0;
    s.grounded   = true;
    s.obstacles  = [];
    s.particles  = [];
    s.frame      = 0;
    s.score      = 0;
    s.running    = true;
    setScore(0);
    setOver(false);
  }, []);

  const jump = useCallback(() => {
    const s = stateRef.current;
    if (!s.running) { reset(); return; }
    if (s.grounded) { s.vy = JUMP; s.grounded = false; }
  }, [reset]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const W   = 700;
    const H   = 210;
    canvas.width  = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width  = `${W}px`;
    canvas.style.height = `${H}px`;
    ctx.scale(dpr, dpr);

    const groundY  = H - 22;
    const playerX  = 52;
    const playerW  = 38;
    const playerH  = 30;

    stateRef.current.stars = initStars(STAR_COUNT, W, H, groundY);

    let raf = 0;

    const loop = () => {
      const s = stateRef.current;
      ctx.clearRect(0, 0, W, H);

      /* ── Background ─────────────────────────────────── */
      const bgGrad = ctx.createLinearGradient(0, 0, 0, H);
      bgGrad.addColorStop(0,   "#020c10");
      bgGrad.addColorStop(0.6, "#04161c");
      bgGrad.addColorStop(1,   "#091e24");
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, W, H);

      /* ── Vertical grid columns ──────────────────────── */
      const colW = 40;
      for (let c = 0; c < Math.ceil(W / colW) + 1; c++) {
        const cx = (c * colW - (s.frame * 0.6) % colW);
        const colAlpha = 0.035 + 0.015 * Math.sin(c * 1.3 + s.frame * 0.02);
        ctx.fillStyle = `rgba(126,224,208,${colAlpha})`;
        ctx.fillRect(cx, 0, 1, groundY);
      }

      /* ── Scanline overlay ───────────────────────────── */
      for (let y = 0; y < groundY; y += 4) {
        ctx.fillStyle = "rgba(0,0,0,0.12)";
        ctx.fillRect(0, y, W, 2);
      }

      /* ── Parallax stars ─────────────────────────────── */
      for (const star of s.stars) {
        if (s.running) star.x -= star.speed;
        if (star.x < -2) star.x = W + 2;
        const flicker = 0.6 + 0.4 * Math.sin(s.frame * 0.07 + star.x);
        ctx.fillStyle = `rgba(126,224,208,${star.bright * flicker})`;
        ctx.fillRect(star.x, star.y, star.size, star.size);
      }

      /* ── Physics ────────────────────────────────────── */
      if (s.running) {
        s.frame += 1;
        const diff = getDifficulty(s.score);

        s.vy += GRAVITY;
        s.playerY += s.vy;
        if (s.playerY >= 0) { s.playerY = 0; s.vy = 0; s.grounded = true; }

        s.obstacles = maybeSpawnObstacles(s.obstacles, W, diff, s.score);
        for (const o of s.obstacles) o.x -= diff.speed;
        s.obstacles = s.obstacles.filter((o) => o.x > -50);

        /* Spawn particles when jumping */
        if (!s.grounded) {
          const py = groundY - playerH + s.playerY;
          s.particles.push({
            x: playerX + playerW - 2,
            y: py + playerH * 0.6,
            vx: -(1.5 + Math.random() * 2),
            vy: (Math.random() - 0.5) * 1.2,
            life: 18,
            maxLife: 18,
          });
        }

        s.particles = s.particles
          .map((p) => ({ ...p, x: p.x + p.vx, y: p.y + p.vy, life: p.life - 1 }))
          .filter((p) => p.life > 0);

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

      /* ── Particle trail ─────────────────────────────── */
      for (const p of s.particles) {
        const alpha = (p.life / p.maxLife) * 0.7;
        const size  = 3 * (p.life / p.maxLife);
        ctx.shadowColor = "#7ee0d0";
        ctx.shadowBlur  = 6;
        ctx.globalAlpha = alpha;
        ctx.fillStyle   = "#7ee0d0";
        ctx.fillRect(p.x - size / 2, p.y - size / 2, size, size);
      }
      ctx.globalAlpha = 1;
      ctx.shadowBlur  = 0;

      /* ── Ground ─────────────────────────────────────── */
      const groundGrad = ctx.createLinearGradient(0, groundY, 0, H);
      groundGrad.addColorStop(0, "rgba(126,224,208,0.18)");
      groundGrad.addColorStop(1, "rgba(126,224,208,0)");
      ctx.fillStyle = groundGrad;
      ctx.fillRect(0, groundY, W, H - groundY);

      ctx.shadowColor = "#7ee0d0";
      ctx.shadowBlur  = 10;
      ctx.strokeStyle = "#7ee0d0";
      ctx.lineWidth   = 2;
      ctx.beginPath();
      ctx.moveTo(0, groundY);
      ctx.lineTo(W, groundY);
      ctx.stroke();
      ctx.shadowBlur = 0;

      /* ── Player ─────────────────────────────────────── */
      const py    = groundY - playerH + stateRef.current.playerY;
      const pulse = 8 + 5 * Math.abs(Math.sin(s.frame * 0.08));

      ctx.shadowColor = "#7ee0d0";
      ctx.shadowBlur  = pulse;
      ctx.strokeStyle = "#7ee0d0";
      ctx.lineWidth   = 1.5;
      ctx.strokeRect(playerX, py + 8, playerW, playerH - 10);

      ctx.fillStyle = "rgba(11,45,53,0.9)";
      ctx.fillRect(playerX, py + 8, playerW, playerH - 10);

      ctx.fillStyle = "#7ee0d0";
      ctx.shadowBlur = pulse * 1.5;
      ctx.fillRect(playerX + 4, py + 2, playerW - 8, 10);

      ctx.shadowBlur  = 0;
      ctx.fillStyle   = "#020c10";
      ctx.font        = "bold 7px ui-monospace, monospace";
      ctx.fillText(">_", playerX + 6, py + 10);

      /* Blinking cursor */
      if (Math.floor(s.frame / 25) % 2 === 0) {
        ctx.fillStyle  = "#7ee0d0";
        ctx.shadowColor = "#7ee0d0";
        ctx.shadowBlur  = 5;
        ctx.fillRect(playerX + playerW - 9, py + 3, 3, 7);
        ctx.shadowBlur = 0;
      }

      /* ── Obstacles ──────────────────────────────────── */
      for (const o of s.obstacles) {
        const shimmer = 0.85 + 0.15 * Math.sin(s.frame * 0.1 + o.x * 0.05);
        ctx.shadowColor = `rgba(255,107,74,${shimmer})`;
        ctx.shadowBlur  = 14;
        ctx.fillStyle   = `rgba(255,${80 + Math.floor(shimmer * 27)},74,1)`;

        if (o.kind === "bug") {
          ctx.font = "bold 16px ui-monospace, monospace";
          ctx.fillText("bug", o.x, groundY - 5);
        } else if (o.kind === "semi") {
          ctx.font = "bold 26px ui-monospace, monospace";
          ctx.fillText(";", o.x, groundY - 2);
        } else {
          ctx.font = "bold 22px ui-monospace, monospace";
          ctx.fillText("}", o.x, groundY - 5);
        }
        ctx.shadowBlur = 0;
      }

      /* ── HUD score ──────────────────────────────────── */
      ctx.shadowColor = "rgba(126,224,208,0.6)";
      ctx.shadowBlur  = 8;
      ctx.fillStyle   = "rgba(126,224,208,0.55)";
      ctx.font        = "bold 11px ui-monospace, monospace";
      ctx.textAlign   = "right";
      ctx.fillText(`${s.score}`, W - 14, 20);
      ctx.textAlign   = "left";
      ctx.shadowBlur  = 0;

      /* ── Game over overlay ──────────────────────────── */
      if (!s.running) {
        ctx.fillStyle = "rgba(2,12,16,0.72)";
        ctx.fillRect(0, 0, W, H);

        ctx.shadowColor = "#ff6b4a";
        ctx.shadowBlur  = 25;
        ctx.fillStyle   = "#ff6b4a";
        ctx.font        = "bold 32px ui-monospace, monospace";
        ctx.textAlign   = "center";
        ctx.fillText("GAME OVER", W / 2, H / 2 - 12);

        ctx.shadowBlur  = 0;
        ctx.fillStyle   = "rgba(126,224,208,0.75)";
        ctx.font        = "12px ui-monospace, monospace";
        ctx.fillText("tap or press Space to restart", W / 2, H / 2 + 14);
        ctx.textAlign   = "left";
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
        <span className="wait-game-title">Dodge the bugs while we scrape</span>
        <span className="wait-game-score">
          {score > 0 && `score: ${score}`}
          {best > 0 && ` · best: ${best}`}
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
          ? "// process crashed — tap or Space to respawn"
          : "// space or tap → jump  ·  avoid the bugs and stray semicolons"}
      </p>
    </div>
  );
}
