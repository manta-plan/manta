import { create } from "zustand";
import type { FeedbackCategory } from "./send-feedback";
import type { FeedbackImage } from "./feedback-image";

interface FeedbackDraft {
  category: FeedbackCategory;
  message: string;
  includePage: boolean;
  image: FeedbackImage | null;
  update: (patch: Partial<Pick<FeedbackDraft, "category" | "message" | "includePage">>) => void;
  setImage: (image: FeedbackImage | null) => void;
  clear: () => void;
}

// Lives outside the dialog so closing it (or navigating between pages, which
// mount separate dialogs) keeps what the user typed until it's sent.
export const useFeedbackDraft = create<FeedbackDraft>((set, get) => ({
  category: "bug_report",
  message: "",
  includePage: true,
  image: null,
  update: (patch) => set(patch),
  setImage: (image) => {
    const previous = get().image;
    if (previous) URL.revokeObjectURL(previous.previewUrl);
    set({ image });
  },
  clear: () => {
    get().setImage(null);
    set({ category: "bug_report", message: "", includePage: true });
  },
}));
