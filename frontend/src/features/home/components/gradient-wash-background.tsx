// Decorative, non-interactive wash for otherwise-empty background space on
// the landing page — soft blurred glows in the brand's primary / secondary
// / accent colors, anchored to corners at low opacity so the palette shows
// through as ambient texture without competing with content.
export function GradientWashBackground() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="bg-accent-400 absolute right-72 bottom-0 h-[420px] w-[420px] rounded-full opacity-[0.16] blur-3xl" />
      <div className="bg-secondary-500 absolute -right-24 -bottom-40 h-[620px] w-[620px] rounded-full opacity-[0.10] blur-3xl" />
      <div className="bg-ok-500 absolute right-24 bottom-10 h-[280px] w-[280px] rounded-full opacity-[0.06] blur-3xl" />
    </div>
  );
}
