import type { NodeApi } from "react-arborist";
import { LuChevronDown, LuChevronRight } from "react-icons/lu";

// STUB: replaced by the real port of baby-manta's components/TreeToggle.tsx.
export function TreeToggle<T>({ node }: { node: NodeApi<T> }) {
  return node.isOpen ? <LuChevronDown size={12} /> : <LuChevronRight size={12} />;
}
