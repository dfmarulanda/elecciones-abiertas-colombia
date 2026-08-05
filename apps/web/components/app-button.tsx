import { cva, type VariantProps } from "class-variance-authority";
import Link from "next/link";
import React, { type ComponentProps, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * AppButton — the DondoDesignSystem control the design imports for every call
 * to action ("Ver la documentación", "Abrir el acta oficial", "Descargar los
 * datos", "Ver los nombres técnicos"). Two variants, two sizes, square
 * corners, one hairline border, no elevation — the same rules as the rest of
 * the token layer in globals.css.
 *
 * `primary` is a fixed neon fill: --neon is only safe as a background behind
 * --ink text (see globals.css), never as text on its own, so the ink label
 * holds regardless of which surface the button sits on.
 *
 * `outline` deliberately sets no text colour: it inherits `currentColor` from
 * whatever surface renders it, so the same className works unchanged inside
 * a light section or an `.ec-field-dark` one -- the ink ramp flips there and
 * the button flips with it.
 */
const appButtonVariants = cva(
  "inline-flex min-h-11 items-center justify-center gap-2 whitespace-nowrap border font-medium leading-none no-underline transition-colors",
  {
    variants: {
      variant: {
        primary: "border-ink bg-neon text-ink hover:brightness-95",
        outline: "border-current bg-transparent hover:bg-current/10",
      },
      size: {
        default: "h-10 px-4 text-[14px]",
        sm: "h-8 px-3 text-[13px]",
      },
    },
    defaultVariants: { variant: "outline", size: "default" },
  },
);

type Variants = VariantProps<typeof appButtonVariants>;

type AppButtonProps = Variants & {
  children: ReactNode;
  className?: string;
} & (
    | ({ href: string } & Omit<
        ComponentProps<typeof Link>,
        "href" | "className" | "children"
      >)
    | ({ href?: undefined } & Omit<
        ComponentProps<"button">,
        "className" | "children"
      >)
  );

export function AppButton({
  variant,
  size,
  className,
  children,
  ...rest
}: AppButtonProps) {
  const classes = cn(appButtonVariants({ variant, size }), className);
  if (rest.href !== undefined) {
    const { href, ...linkProps } = rest as { href: string } & Omit<
      ComponentProps<typeof Link>,
      "href" | "className" | "children"
    >;
    return (
      <Link href={href} className={classes} {...linkProps}>
        {children}
      </Link>
    );
  }
  const buttonProps = rest as Omit<
    ComponentProps<"button">,
    "className" | "children"
  >;
  return (
    <button type="button" className={classes} {...buttonProps}>
      {children}
    </button>
  );
}
