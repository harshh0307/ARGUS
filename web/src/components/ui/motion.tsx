"use client";

import { motion, type MotionProps, type Variants } from "motion/react";

function usePrefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

type Direction = "left" | "right" | "top" | "bottom";

const slideVariants: Record<Direction, Variants> = {
  left: { hidden: { x: -20, opacity: 0 }, visible: { x: 0, opacity: 1 } },
  right: { hidden: { x: 20, opacity: 0 }, visible: { x: 0, opacity: 1 } },
  top: { hidden: { y: -20, opacity: 0 }, visible: { y: 0, opacity: 1 } },
  bottom: { hidden: { y: 20, opacity: 0 }, visible: { y: 0, opacity: 1 } },
};

export function FadeIn({
  children,
  delay = 0,
  className,
  ...props
}: MotionProps & { children: React.ReactNode; delay?: number; className?: string }) {
  const reduced = usePrefersReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: [0.25, 0.46, 0.45, 0.94] }}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
}

export function StaggerContainer({
  children,
  className,
  staggerDelay = 0.06,
  ...props
}: MotionProps & { children: React.ReactNode; className?: string; staggerDelay?: number }) {
  const reduced = usePrefersReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;
  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: staggerDelay } },
      }}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
}

export function StaggerItem({
  children,
  className,
  ...props
}: MotionProps & { children: React.ReactNode; className?: string }) {
  const reduced = usePrefersReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;
  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: 16 },
        visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: "easeOut" } },
      }}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
}

export function ScaleOnHover({
  children,
  className,
  ...props
}: MotionProps & { children: React.ReactNode; className?: string }) {
  const reduced = usePrefersReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;
  return (
    <motion.div
      whileHover={{ scale: 0.98 }}
      whileTap={{ scale: 0.96 }}
      transition={{ type: "spring", stiffness: 400, damping: 25 }}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
}

export function SlideIn({
  children,
  direction = "bottom",
  delay = 0,
  className,
  ...props
}: MotionProps & {
  children: React.ReactNode;
  direction?: Direction;
  delay?: number;
  className?: string;
}) {
  const reduced = usePrefersReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;
  return (
    <motion.div
      variants={slideVariants[direction]}
      initial="hidden"
      animate="visible"
      transition={{ duration: 0.35, delay, ease: "easeOut" }}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
}

export function PulseOnComplete({
  children,
  trigger,
  className,
  ...props
}: MotionProps & {
  children: React.ReactNode;
  trigger: boolean;
  className?: string;
}) {
  const reduced = usePrefersReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;
  return (
    <motion.div
      animate={trigger ? { scale: [1, 1.05, 1] } : {}}
      transition={{ duration: 0.3, ease: "easeInOut" }}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
}

export { motion };
