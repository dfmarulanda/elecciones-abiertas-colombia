"use client";

import * as Dialog from "@radix-ui/react-dialog";
import dynamic from "next/dynamic";
import { ChevronRight, Map, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useMemo, useState } from "react";

import {
  DANE_DEPARTMENT_BOUNDARY,
  reviewedDepartmentRows,
  type DepartmentMapRow,
} from "@/lib/department-map";

const DepartmentMap = dynamic(
  () => import("./department-map").then((module) => module.DepartmentMap),
  { ssr: false },
);

export type ResultMapProps = {
  locale: "es" | "en";
  rows: DepartmentMapRow[];
  initiallyOpen?: boolean;
  hideTrigger?: boolean;
  onDismiss?: () => void;
};

export function ResultMap({
  locale,
  rows,
  initiallyOpen = false,
  hideTrigger = false,
  onDismiss,
}: ResultMapProps) {
  const [open, setOpen] = useState(initiallyOpen);
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const es = locale === "es";
  const departments = useMemo(() => reviewedDepartmentRows(rows), [rows]);
  const selected = departments.find((row) => row.daneCode === selectedCode);
  const select = useCallback((code: string) => setSelectedCode(code), []);
  const title = es ? "Mapa de departamentos" : "Department map";

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (!nextOpen) onDismiss?.();
      }}
    >
      {!hideTrigger ? (
        <Dialog.Trigger asChild>
          <button className="inline-flex min-h-11 items-center gap-2 border border-ink px-4 text-sm font-bold hover:bg-neon">
            <Map className="size-4" aria-hidden="true" />
            {es ? "Abrir mapa" : "Open map"}
          </button>
        </Dialog.Trigger>
      ) : null}
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink/70 opacity-0 transition-opacity duration-[380ms] ease-[cubic-bezier(0.2,0.7,0.1,1)] data-[state=open]:opacity-100 motion-reduce:transition-none" />
        <Dialog.Content className="fixed inset-x-0 bottom-0 top-4 z-50 translate-y-4 overflow-y-auto border border-ink bg-paper p-4 opacity-0 transition-[opacity,transform] duration-[380ms] ease-[cubic-bezier(0.2,0.7,0.1,1)] data-[state=open]:translate-y-0 data-[state=open]:opacity-100 motion-reduce:translate-y-0 motion-reduce:transition-none sm:inset-8 sm:p-8">
          <div className="mx-auto max-w-6xl">
            <div className="flex min-w-0 items-start justify-between gap-4 bg-ink p-4 text-paper sm:p-6">
              <div className="min-w-0 flex-1">
                <p className="inline-flex bg-neon px-2 py-1 font-mono text-xs font-bold tracking-[.14em] text-ink uppercase">
                  {es ? "Vista territorial" : "Territorial view"}
                </p>
                <Dialog.Title className="mt-3 min-w-0 max-w-full font-display text-2xl font-normal leading-tight sm:text-4xl">
                  {title}
                </Dialog.Title>
                <Dialog.Description className="mt-2 max-w-2xl text-sm leading-6 text-paper/70">
                  {departments.length
                    ? es
                      ? `Lectura visual de ${departments.length} departamento${departments.length === 1 ? "" : "s"} con datos y equivalencia explícita en tabla. El color muestra presencia territorial, no una candidatura ni una conclusión; la selección se hace en la tabla.`
                      : `A visual reading of ${departments.length} department${departments.length === 1 ? "" : "s"} with data and an explicit table equivalent. Color shows territorial presence, not a candidate or conclusion; selection happens in the table.`
                    : es
                      ? "Esta selección no contiene departamentos con una equivalencia revisada. No se dibuja una ubicación inferida; la tabla de resultados sigue siendo la fuente de lectura."
                      : "This selection has no departments with a reviewed equivalence. No inferred location is drawn; the results table remains the reading source."}
                </Dialog.Description>
              </div>
              <Dialog.Close
                className="grid size-11 shrink-0 place-items-center border border-paper/40 hover:bg-neon hover:text-ink"
                aria-label={es ? "Cerrar mapa" : "Close map"}
              >
                <X className="size-5" />
              </Dialog.Close>
            </div>

            <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(17rem,.7fr)]">
              <div className="min-w-0">
                {departments.length ? (
                  <DepartmentMap
                    locale={locale}
                    rows={departments}
                    selectedCode={selectedCode}
                  />
                ) : (
                  <div className="grid min-h-72 place-items-center border border-ink bg-paper p-6 text-center text-sm leading-6 text-muted">
                    {es
                      ? "Sin límite departamental publicado para esta selección."
                      : "No published department boundary for this selection."}
                  </div>
                )}
                <details className="mt-4 border border-ink bg-ink px-4 py-3 text-sm text-paper">
                  <summary className="min-h-11 cursor-pointer py-2 font-bold">
                    {es ? "Límite y procedencia" : "Boundary and provenance"}
                  </summary>
                  <dl className="grid gap-x-4 gap-y-2 border-t border-paper/20 pb-2 pt-3 text-xs leading-5 text-paper/75 sm:grid-cols-[auto_minmax(0,1fr)]">
                    <dt className="font-bold">
                      {es ? "Fuente oficial" : "Official source"}
                    </dt>
                    <dd>
                      <a
                        className="text-paper underline decoration-neon underline-offset-4"
                        href={DANE_DEPARTMENT_BOUNDARY.sourceUrl}
                        target="_blank"
                        rel="noreferrer"
                      >
                        DANE · {DANE_DEPARTMENT_BOUNDARY.version}
                      </a>
                    </dd>
                    <dt className="font-bold">
                      {es
                        ? "Hash de respuesta oficial"
                        : "Official response hash"}
                    </dt>
                    <dd className="break-all font-mono">
                      {DANE_DEPARTMENT_BOUNDARY.sourceResponseSha256}
                    </dd>
                    <dt className="font-bold">
                      {es
                        ? "Derivado local revisado"
                        : "Reviewed local derivative"}
                    </dt>
                    <dd className="break-all">
                      {DANE_DEPARTMENT_BOUNDARY.derivativePath}
                    </dd>
                    <dt className="font-bold">
                      {es ? "Hash del derivado" : "Derivative hash"}
                    </dt>
                    <dd className="break-all font-mono">
                      {DANE_DEPARTMENT_BOUNDARY.derivativeSha256}
                    </dd>
                    <dt className="font-bold">
                      {es ? "Transformación" : "Transform"}
                    </dt>
                    <dd>
                      {DANE_DEPARTMENT_BOUNDARY.derivativeTransformVersion}
                    </dd>
                    <dt className="font-bold">
                      {es ? "Recuperado" : "Retrieved"}
                    </dt>
                    <dd>{DANE_DEPARTMENT_BOUNDARY.retrievedAt}</dd>
                    <dt className="font-bold">
                      {es ? "Atribución" : "Attribution"}
                    </dt>
                    <dd>{DANE_DEPARTMENT_BOUNDARY.attribution}</dd>
                  </dl>
                </details>
              </div>
              <aside className="min-w-0">
                <h2 className="font-mono text-xs font-bold tracking-[.1em] text-ink uppercase">
                  {es ? "Equivalente del mapa" : "Map equivalent"}
                </h2>
                <p className="mt-2 text-sm leading-6 text-muted">
                  {selected
                    ? es
                      ? `${selected.daneName} está seleccionado. ${selected.value}.`
                      : `${selected.daneName} is selected. ${selected.value}.`
                    : es
                      ? "Use esta lista para seleccionar o abrir un departamento."
                      : "Use this list to select or open a department."}
                </p>
                <div className="mt-3 max-w-full overflow-x-auto border border-ink">
                  <table className="w-full min-w-64 text-left text-sm sm:min-w-72">
                    <caption className="sr-only">
                      {es
                        ? "Equivalente tabular del mapa"
                        : "Map table equivalent"}
                    </caption>
                    <thead className="bg-ink font-mono text-xs text-paper uppercase">
                      <tr>
                        <th className="px-3 py-3">
                          {es ? "Departamento" : "Department"}
                        </th>
                        <th className="px-3 py-3">{es ? "Valor" : "Value"}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {departments.map((row) => (
                        <tr
                          className={
                            selectedCode === row.daneCode
                              ? "border-t border-ink bg-neon text-ink"
                              : "border-t border-ink"
                          }
                          key={row.daneCode}
                        >
                          <th className="px-3 py-2 font-semibold" scope="row">
                            <button
                              className="min-h-11 text-left underline decoration-ink underline-offset-4"
                              onClick={() => select(row.daneCode)}
                              aria-pressed={selectedCode === row.daneCode}
                            >
                              {row.daneName}
                            </button>
                          </th>
                          <td className="px-3 py-2">
                            {row.href ? (
                              <Link
                                className="inline-flex min-h-11 items-center gap-1 underline decoration-ink underline-offset-4"
                                href={row.href}
                              >
                                {row.value}
                                <ChevronRight
                                  className="size-4"
                                  aria-hidden="true"
                                />
                              </Link>
                            ) : (
                              row.value
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </aside>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
