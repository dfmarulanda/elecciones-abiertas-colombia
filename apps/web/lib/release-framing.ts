import { isSyntheticFixture } from "@/lib/synthetic";

/**
 * How the current build's data must be framed to the reader. This is the single
 * source of truth for the disclosure the site shows — it must never claim more
 * certainty than the data has.
 *
 * - `preliminary`: real Registraduria pre-count (preconteo). Non-binding
 *   per-table figures. The certified OUTCOME is a matter of public record and
 *   is stated as such, but the tallies here are not the final scrutiny.
 * - `synthetic`: development fixture; not real results.
 * - `certified`: a real published/certified release served by the live API.
 */
export type ReleaseFraming = "preliminary" | "synthetic" | "certified";

export function releaseFraming(): ReleaseFraming {
  if (process.env.NEXT_PUBLIC_PRELIMINARY_RELEASE === "true") return "preliminary";
  if (isSyntheticFixture()) return "synthetic";
  return "certified";
}

export function isPreliminary() {
  return releaseFraming() === "preliminary";
}
