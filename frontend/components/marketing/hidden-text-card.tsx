"use client";

import { motion } from "framer-motion";
import { LockKeyhole, Sparkles } from "lucide-react";

type HiddenTextCardProps = {
  eyebrow: string;
  title: string;
  preview: string;
  reveal: string;
};

export function HiddenTextCard({
  eyebrow,
  title,
  preview,
  reveal,
}: HiddenTextCardProps) {
  return (
    <motion.div
      whileHover="hover"
      initial="rest"
      animate="rest"
      className="group relative overflow-hidden rounded-[1.75rem] border border-border-subtle bg-surface-elevated p-6"
      style={{
        boxShadow: "0 24px 80px color-mix(in srgb, var(--background) 65%, transparent)",
      }}
    >
      <motion.div
        variants={{
          rest: { opacity: 0.9, scale: 1 },
          hover: { opacity: 1, scale: 1.04 },
        }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        className="absolute inset-x-6 top-0 h-40 rounded-full blur-3xl"
        style={{ background: "color-mix(in srgb, var(--accent) 22%, transparent)" }}
      />

      <div className="relative z-10 flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-text-muted">
            {eyebrow}
          </p>
          <h3 className="mt-3 text-2xl font-semibold text-text-primary">{title}</h3>
        </div>
        <div
          className="rounded-full border border-border-default p-3 text-primary"
          style={{
            background: "color-mix(in srgb, var(--background-secondary) 80%, transparent)",
          }}
        >
          <LockKeyhole className="size-5" />
        </div>
      </div>

      <div className="relative z-10 mt-8 grid gap-4">
        <motion.div
          variants={{
            rest: { opacity: 1, y: 0, filter: "blur(0px)" },
            hover: { opacity: 0.16, y: -8, filter: "blur(4px)" },
          }}
          transition={{ duration: 0.28, ease: "easeOut" }}
          className="rounded-2xl border border-border-subtle p-5"
          style={{ background: "color-mix(in srgb, var(--surface-muted) 90%, transparent)" }}
        >
          <p className="text-sm leading-7 text-text-secondary">{preview}</p>
        </motion.div>

        <motion.div
          variants={{
            rest: { opacity: 0, y: 12, filter: "blur(8px)" },
            hover: { opacity: 1, y: -8, filter: "blur(0px)" },
          }}
          transition={{ duration: 0.3, ease: "easeOut" }}
          className="absolute inset-x-0 bottom-0 rounded-[1.4rem] border border-border-default p-5"
          style={{
            background: "var(--surface)",
            boxShadow: "0 18px 40px color-mix(in srgb, var(--background) 58%, transparent)",
          }}
        >
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-primary">
            <Sparkles className="size-4" />
            Reveal
          </div>
          <p className="text-sm leading-7 text-text-primary">{reveal}</p>
        </motion.div>
      </div>
    </motion.div>
  );
}
