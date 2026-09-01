/**
 * UI 프리미티브.
 *
 * shadcn/ui 의 구조(Radix + cva + cn)는 그대로 쓰되 스타일은 전부 우리 토큰으로
 * 다시 썼다. 기본값과 다른 점: 높이 32px 고정, 라운딩 3px, 그림자 없음,
 * 포커스 링은 앰버. 앰버는 어떤 정적 크롬에도 쓰지 않는다.
 */
import * as SelectPrimitive from "@radix-ui/react-select";
import { cva, type VariantProps } from "class-variance-authority";
import { Check, ChevronDown } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ Legend */

const HANGUL = /[ᄀ-ᇿ㄰-㆏가-힯]/;

/**
 * 라벨. 라틴이면 실크스크린(대문자 · 넓은 자간), 한글이면 자간 없는 작은 라벨.
 * 0.14em 자간을 한글에 걸면 글자가 흩어져서 읽히지 않는다.
 */
export function Legend({ children, className }: { children: React.ReactNode; className?: string }) {
  const korean = typeof children === "string" && HANGUL.test(children);
  return <div className={cn(korean ? "t-label" : "t-legend", className)}>{children}</div>;
}

/** 라벨 + 값. 장비가 모든 컨트롤에 라벨을 새기는 것과 같다. */
export function Readout({
  label,
  value,
  className,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  className?: string;
  tone?: "signal" | "ready" | "clip";
}) {
  const color =
    tone === "signal" ? "text-lamp-signal"
    : tone === "ready" ? "text-lamp-ready"
    : tone === "clip" ? "text-lamp-clip"
    : "text-text-1";
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <Legend>{label}</Legend>
      <div className={cn("t-meter", color)}>{value}</div>
    </div>
  );
}

/* -------------------------------------------------------------------- Lamp */

export type LampTone = "off" | "signal" | "ready" | "clip";

export function Lamp({
  tone = "off",
  pulse = false,
  label,
}: {
  tone?: LampTone;
  pulse?: boolean;
  label?: string;
}) {
  const bg =
    tone === "signal" ? "bg-lamp-signal"
    : tone === "ready" ? "bg-lamp-ready"
    : tone === "clip" ? "bg-lamp-clip"
    : "bg-line";
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className={cn("size-[6px] shrink-0 rounded-full", bg, pulse && "lamp-pulse")}
        aria-hidden
      />
      {/* 색만으로 상태를 구분하지 않는다 */}
      {label ? <span className="t-legend">{label}</span> : null}
    </span>
  );
}

/* ------------------------------------------------------------------ Button */

const buttonVariants = cva(
  "inline-flex h-8 items-center justify-center gap-2 rounded-[--radius-1] border " +
    "px-3 t-ui whitespace-nowrap transition-colors duration-[120ms] ease-out " +
    "disabled:pointer-events-none disabled:opacity-40 no-drag",
  {
    variants: {
      variant: {
        // 주 동작도 앰버를 쓰지 않는다. 밝기 대비로 위계를 만든다.
        primary:
          "border-line bg-surface-3 text-text-1 hover:bg-line-soft hover:border-text-3 active:bg-surface-2",
        ghost:
          "border-transparent bg-transparent text-text-2 hover:bg-surface-2 hover:text-text-1",
        outline:
          "border-line bg-transparent text-text-2 hover:bg-surface-2 hover:text-text-1",
        danger:
          "border-lamp-clip/40 bg-transparent text-lamp-clip hover:bg-lamp-clip/10",
      },
      size: {
        default: "h-8 px-3",
        sm: "h-7 px-2 text-[12px]",
        icon: "h-8 w-8 px-0",
        iconSm: "h-7 w-7 px-0",
      },
    },
    defaultVariants: { variant: "primary", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  ),
);
Button.displayName = "Button";

/* ------------------------------------------------------------------- Input */

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-8 w-full rounded-[--radius-1] border border-line bg-surface-3 px-2.5 t-ui",
        "text-text-1 placeholder:text-text-3 outline-none no-drag",
        "transition-colors duration-[120ms] hover:border-text-3",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "w-full resize-none rounded-[--radius-1] border border-line bg-surface-3 px-2.5 py-2",
      "t-body text-text-1 placeholder:text-text-3 outline-none no-drag",
      "transition-colors duration-[120ms] hover:border-text-3",
      className,
    )}
    {...props}
  />
));
Textarea.displayName = "Textarea";

/* ------------------------------------------------------------------- Field */

export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("flex flex-col gap-1.5", className)}>
      <Legend>{label}</Legend>
      {children}
      {hint ? <span className="text-[11px] leading-4 text-text-3">{hint}</span> : null}
    </label>
  );
}

/* ------------------------------------------------------------------ Select */

export function Select<T extends string>({
  value,
  onValueChange,
  options,
  placeholder = "고르기",
  className,
  disabled,
}: {
  value: T | undefined;
  onValueChange: (v: T) => void;
  options: { value: T; label: string; hint?: string }[];
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}) {
  return (
    <SelectPrimitive.Root value={value} onValueChange={(v) => onValueChange(v as T)} disabled={disabled}>
      <SelectPrimitive.Trigger
        className={cn(
          "flex h-8 w-full items-center justify-between gap-2 rounded-[--radius-1]",
          "border border-line bg-surface-3 px-2.5 t-ui text-text-1 outline-none no-drag",
          "transition-colors duration-[120ms] hover:border-text-3",
          "disabled:opacity-40 data-[placeholder]:text-text-3",
          className,
        )}
      >
        <SelectPrimitive.Value placeholder={placeholder} />
        <SelectPrimitive.Icon>
          <ChevronDown className="size-3.5 text-text-3" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={4}
          className={cn(
            "z-50 max-h-72 min-w-[--radix-select-trigger-width] overflow-hidden",
            "rounded-[--radius-2] border border-line bg-surface-2 p-1",
          )}
        >
          <SelectPrimitive.Viewport>
            {options.map((o) => (
              <SelectPrimitive.Item
                key={o.value}
                value={o.value}
                className={cn(
                  "relative flex cursor-default select-none items-center justify-between gap-3",
                  "rounded-[--radius-1] px-2 py-1.5 t-ui text-text-2 outline-none",
                  "data-[highlighted]:bg-surface-3 data-[highlighted]:text-text-1",
                  "data-[state=checked]:text-text-1",
                )}
              >
                <span className="flex flex-col">
                  <SelectPrimitive.ItemText>{o.label}</SelectPrimitive.ItemText>
                  {o.hint ? <span className="text-[11px] text-text-3">{o.hint}</span> : null}
                </span>
                <SelectPrimitive.ItemIndicator>
                  <Check className="size-3.5 text-lamp-ready" />
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}

/* ------------------------------------------------------------------ 기타 */

export function Card({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  // 그림자 없음. 층위는 서피스 밝기와 1px 라인으로만.
  return (
    <div className={cn("rounded-[--radius-2] border border-line bg-surface-2", className)}>
      {children}
    </div>
  );
}

/** 오류 표시 — 사과하지 않고 원인과 다음 행동만 말한다. */
export function ErrorNote({
  message,
  action,
  className,
}: {
  message: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start justify-between gap-4 rounded-[--radius-2] border",
        "border-lamp-clip/35 bg-lamp-clip/[0.07] px-3 py-2.5",
        className,
      )}
    >
      <div className="flex items-start gap-2.5">
        <span className="mt-[7px] size-[6px] shrink-0 rounded-full bg-lamp-clip" aria-hidden />
        <span className="t-body text-text-1">{message}</span>
      </div>
      {action}
    </div>
  );
}

export function Empty({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center">
      <div className="t-body text-text-2">{title}</div>
      {children}
    </div>
  );
}
