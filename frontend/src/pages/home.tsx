import { Button } from "@base-ui/react/button";
import { FiActivity, FiArrowRight, FiFeather } from "react-icons/fi";

export function HomePage() {
  return (
    <main className="bg-background text-text min-h-svh px-6 py-12 sm:py-16">
      <section className="mx-auto grid min-h-[calc(100svh-6rem)] w-full max-w-5xl items-center gap-10 md:grid-cols-[1.15fr_0.85fr]">
        <div>
          <div className="border-border bg-surface text-text-secondary mb-8 inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm font-medium">
            <span className="bg-accent size-2 rounded-full" aria-hidden="true" />
            Energy system modeling
          </div>

          <div className="text-primary-foreground shadow-primary/20 mb-6 flex size-16 items-center justify-center rounded-lg bg-[image:var(--gradient-logo)] shadow-lg">
            <FiFeather className="size-7" aria-hidden="true" />
          </div>

          <p className="text-secondary mb-3 text-sm font-semibold uppercase">
            Base UI + React Icons
          </p>
          <h1 className="max-w-2xl text-5xl font-semibold tracking-normal sm:text-6xl">
            Hello world
          </h1>
          <p className="text-text-secondary mt-5 max-w-xl text-base leading-7">
            MANTA brand tokens are now available through Tailwind utilities, with ocean blue, aurora
            teal, and energy lime mapped to reusable semantic colors.
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            <Button className="bg-primary text-primary-foreground shadow-primary/25 hover:bg-primary-hover active:bg-primary-active focus-visible:outline-secondary inline-flex items-center gap-2 rounded-md px-4 py-2.5 text-sm font-semibold shadow-lg transition focus-visible:outline-2 focus-visible:outline-offset-2">
              Explore setup
              <FiArrowRight className="size-4" aria-hidden="true" />
            </Button>
            <Button className="border-border bg-surface text-primary hover:bg-surface-alt focus-visible:outline-secondary inline-flex items-center gap-2 rounded-md border px-4 py-2.5 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2">
              <FiActivity className="size-4" aria-hidden="true" />
              View tokens
            </Button>
          </div>
        </div>

        <aside className="border-border bg-surface shadow-primary/10 rounded-lg border p-5 shadow-xl">
          <div className="mb-5 h-32 rounded-md bg-[image:var(--gradient-hero)]" />
          <dl className="grid gap-3 text-sm">
            {[
              ["Primary", "bg-primary"],
              ["Secondary", "bg-secondary"],
              ["Accent", "bg-accent"],
            ].map(([label, utility]) => (
              <div
                className="bg-surface-alt flex items-center justify-between rounded-md px-3 py-2"
                key={label}
              >
                <dt className="text-text font-medium">{label}</dt>
                <dd className="text-text-secondary flex items-center gap-2">
                  <span className={`size-4 rounded-full ${utility}`} aria-hidden="true" />
                  {utility}
                </dd>
              </div>
            ))}
          </dl>
        </aside>
      </section>
    </main>
  );
}
