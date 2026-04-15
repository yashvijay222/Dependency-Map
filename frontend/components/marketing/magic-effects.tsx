"use client";

import { motion } from "framer-motion";

import { cn } from "@/lib/utils";

export function AnimatedGridPattern({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cn(
        "hero-grid absolute inset-0 opacity-70 [mask-image:radial-gradient(circle_at_center,black,transparent_78%)]",
        className,
      )}
    />
  );
}

export function GlowOrbs() {
  return (
    <div aria-hidden className="absolute inset-0 overflow-hidden">
      <motion.div
        className="absolute -left-24 top-8 h-64 w-64 rounded-full blur-3xl"
        style={{ background: "color-mix(in srgb, var(--primary) 24%, transparent)" }}
        animate={{ x: [0, 16, -10, 0], y: [0, 12, -8, 0], scale: [1, 1.08, 0.98, 1] }}
        transition={{ duration: 14, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute right-0 top-24 h-72 w-72 rounded-full blur-3xl"
        style={{ background: "color-mix(in srgb, var(--accent) 22%, transparent)" }}
        animate={{ x: [0, -18, 12, 0], y: [0, -16, 8, 0], scale: [1, 0.95, 1.06, 1] }}
        transition={{ duration: 18, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute bottom-0 left-1/3 h-56 w-56 rounded-full blur-3xl"
        style={{ background: "color-mix(in srgb, var(--info) 16%, transparent)" }}
        animate={{ x: [0, 10, -16, 0], y: [0, -14, 10, 0], scale: [1, 1.05, 0.97, 1] }}
        transition={{ duration: 16, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
      />
    </div>
  );
}

export function FloatingParticles() {
  return (
    <div aria-hidden className="absolute inset-0 overflow-hidden">
      {Array.from({ length: 12 }).map((_, index) => (
        <motion.span
          key={index}
          className="absolute block rounded-full"
          style={{
            width: 6 + (index % 3) * 2,
            height: 6 + (index % 3) * 2,
            left: `${8 + index * 7}%`,
            top: `${12 + (index % 4) * 18}%`,
            background:
              index % 2 === 0
                ? "color-mix(in srgb, var(--primary) 48%, transparent)"
                : "color-mix(in srgb, var(--accent) 45%, transparent)",
          }}
          animate={{ y: [0, -16, 0], opacity: [0.15, 0.45, 0.15] }}
          transition={{
            duration: 4 + (index % 4),
            delay: index * 0.16,
            repeat: Number.POSITIVE_INFINITY,
            ease: "easeInOut",
          }}
        />
      ))}
    </div>
  );
}
