import { setRequestLocale } from "next-intl/server";
import { Page, Section } from "@/components/page-primitives";
export default async function AccessibilityPage({
  params,
}: {
  params: Promise<{ locale: "es" | "en" }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const es = locale === "es";
  return (
    <Page
      locale={locale}
      eyebrow="WCAG 2.2 AA"
      title={es ? "Accesibilidad" : "Accessibility"}
    >
      <Section title={es ? "Compromisos de interfaz" : "Interface commitments"}>
        <ul className="list-disc pl-5">
          <li>
            {es
              ? "Enlace para saltar al contenido principal en cada página."
              : "Skip link to main content on every page."}
          </li>
          <li>
            {es
              ? "Navegación de teclado, foco visible y controles de al menos 44 px."
              : "Keyboard navigation, visible focus, and controls at least 44px."}
          </li>
          <li>
            {es
              ? "Alternativa tabular para información cartográfica y resúmenes textuales para gráficos."
              : "Table equivalent for map information and text summaries for charts."}
          </li>
          <li>
            {es
              ? "Reflujo desde 320 px y al 200 %, con reducción de movimiento respetada."
              : "Reflow from 320px and at 200%, with reduced motion respected."}
          </li>
        </ul>
      </Section>
      <Section title={es ? "Ayuda y límites" : "Help and limits"}>
        <p>
          {es
            ? "Si encuentra una barrera, describa la página, tarea, tecnología de apoyo y navegador. Los enlaces externos y documentos fuente pueden tener accesibilidad propia fuera de este visor."
            : "If you find a barrier, report the page, task, assistive technology, and browser. External links and source documents may have their own accessibility outside this viewer."}
        </p>
      </Section>
    </Page>
  );
}
