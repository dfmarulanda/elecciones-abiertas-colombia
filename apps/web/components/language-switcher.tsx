"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, Languages } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const locales = [
  { code: "es", label: "Español" },
  { code: "en", label: "English" },
] as const;

export function LanguageSwitcher({
  locale,
  label,
}: {
  locale: "es" | "en";
  label: string;
}) {
  const pathname = usePathname();
  const [search, setSearch] = useState("");
  useEffect(() => setSearch(window.location.search), []);
  const switchTo = (nextLocale: string) =>
    `${pathname.replace(/^\/(es|en)(?=\/|$)/, `/${nextLocale}`)}${search}`;

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        className="inline-flex min-h-11 items-center gap-2 border border-ink bg-paper px-3 text-sm font-semibold text-ink hover:bg-neon"
        aria-label={label}
      >
        <Languages className="size-4" aria-hidden="true" />
        <span>{locales.find((item) => item.code === locale)?.label}</span>
        <ChevronDown className="size-4" aria-hidden="true" />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className="z-50 mt-2 min-w-36 border border-ink bg-paper p-1"
          align="end"
        >
          {locales.map((item) => (
            <DropdownMenu.Item
              key={item.code}
              className="flex min-h-11 cursor-pointer items-center px-3 text-sm font-semibold outline-none hover:bg-neon focus:bg-neon"
              onSelect={() => {
                window.location.assign(switchTo(item.code));
              }}
            >
              <span
                aria-hidden="true"
                className={`mr-2 inline-block size-2 border border-ink ${
                  item.code === locale ? "bg-neon" : "bg-paper"
                }`}
              />
              {item.label}
              {item.code === locale ? (
                <span className="ml-auto text-xs text-muted">✓</span>
              ) : null}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
