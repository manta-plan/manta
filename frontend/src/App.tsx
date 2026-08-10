import { Button } from "@base-ui/react/button";
import { FiArrowRight, FiFeather } from "react-icons/fi";

function App() {
  return (
    <main className="flex min-h-svh items-center justify-center bg-slate-950 px-6 text-white">
      <section className="w-full max-w-xl text-center">
        <div className="mx-auto mb-6 flex size-14 items-center justify-center rounded-full border border-cyan-300/30 bg-cyan-300/10 text-cyan-200">
          <FiFeather className="size-6" aria-hidden="true" />
        </div>

        <p className="mb-3 text-sm font-medium tracking-[0.2em] text-cyan-300 uppercase">
          Base UI + React Icons
        </p>
        <h1 className="text-5xl font-semibold tracking-normal sm:text-6xl">Hello world</h1>
        <p className="mx-auto mt-5 max-w-md text-base leading-7 text-slate-300">
          This page uses an unstyled Base UI button styled with Tailwind, plus icons from React
          Icons.
        </p>

        <Button className="mt-8 inline-flex items-center gap-2 rounded-md bg-cyan-300 px-4 py-2.5 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-950/30 transition hover:bg-cyan-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-200">
          Explore setup
          <FiArrowRight className="size-4" aria-hidden="true" />
        </Button>
      </section>
    </main>
  );
}

export default App;
