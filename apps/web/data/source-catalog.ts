import { readFile } from "node:fs/promises";
import path from "node:path";

export type PublicSourceCatalog = {
  catalog_version: string;
  verified_at: string;
  publication_state:
    "awaiting_verified_final_declaration" | "ready_for_candidate_release";
  official_hub: string;
  sources: Array<{
    id: string;
    role: string;
    legal_status: string;
    status?: string;
    notes?: string;
    entrypoints: Record<string, string>;
  }>;
  contextual_sources: Array<{
    id: string;
    role: "context_only";
    url: string;
  }>;
};

export async function loadSourceCatalog(): Promise<PublicSourceCatalog> {
  const catalogPath = path.resolve(
    process.cwd(),
    "../../config/sources/presidencia-2026-segunda-vuelta.json",
  );
  return JSON.parse(await readFile(catalogPath, "utf8")) as PublicSourceCatalog;
}
