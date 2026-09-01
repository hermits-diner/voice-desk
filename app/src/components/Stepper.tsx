import { cn } from "@/lib/utils";

const STEPS = ["주제", "대본", "렌더"] as const;

export function Stepper({
  step,
  maxReached,
  onGo,
}: {
  step: 1 | 2 | 3;
  maxReached: 1 | 2 | 3;
  onGo: (s: 1 | 2 | 3) => void;
}) {
  return (
    <nav aria-label="진행 단계" className="flex items-center gap-1">
      {STEPS.map((label, i) => {
        const n = (i + 1) as 1 | 2 | 3;
        const active = n === step;
        const reachable = n <= maxReached;
        return (
          <div key={label} className="flex items-center">
            <button
              type="button"
              disabled={!reachable}
              aria-current={active ? "step" : undefined}
              onClick={() => reachable && onGo(n)}
              className={cn(
                "flex h-8 items-center gap-2 rounded-[--radius-1] px-2.5 t-ui",
                "transition-colors duration-[120ms] disabled:cursor-default",
                active ? "text-text-1" : reachable ? "text-text-2 hover:bg-surface-2" : "text-text-3",
              )}
            >
              <span
                className={cn(
                  "size-[6px] rounded-full",
                  active ? "bg-lamp-signal" : reachable ? "bg-text-3" : "bg-line",
                )}
                aria-hidden
              />
              <span className="t-legend">{`0${n}`}</span>
              <span>{label}</span>
            </button>
            {i < STEPS.length - 1 ? (
              <span className="mx-1 h-px w-6 bg-line" aria-hidden />
            ) : null}
          </div>
        );
      })}
    </nav>
  );
}
