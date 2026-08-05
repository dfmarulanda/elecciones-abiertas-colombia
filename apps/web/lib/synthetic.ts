/**
 * One definition of "this build is reading a synthetic fixture".
 *
 * It used to be inlined in page-primitives, which meant the shell and the page
 * could in principle disagree about whether to disclose. The disclosure is the
 * single most important thing on the page; it does not get two sources.
 */
export function isSyntheticFixture() {
  return (
    process.env.NEXT_PUBLIC_SYNTHETIC_FIXTURE === "true" ||
    !process.env.NEXT_PUBLIC_API_URL
  );
}
