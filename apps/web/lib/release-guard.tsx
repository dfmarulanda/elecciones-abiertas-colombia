import { getTranslations } from "next-intl/server";
import { ReleaseUnavailable } from "@/components/release-unavailable";
import type { ReactElement } from "react";

/**
 * Load a release, or render the explicit unavailable state.
 *
 * The API refuses to serve a context-only historical release through the
 * legacy release contract rather than invent completion metadata. Every page
 * that needs a standard release must therefore treat "no release" as a normal,
 * representable state instead of crashing on the refusal -- the same
 * discipline the data layer applies to unknown, unavailable and zero.
 */
export async function loadReleaseOrUnavailable<T>(
  locale: "es" | "en",
  load: () => Promise<T>,
): Promise<{ release: T; fallback: null } | { release: null; fallback: ReactElement }> {
  try {
    return { release: await load(), fallback: null };
  } catch {
    const t = await getTranslations();
    return {
      release: null,
      fallback: (
        <ReleaseUnavailable
          locale={locale}
          title={t("releaseUnavailable.title")}
          body={t("releaseUnavailable.body")}
          methodology={t("releaseUnavailable.methodology")}
          sources={t("releaseUnavailable.sources")}
        />
      ),
    };
  }
}
