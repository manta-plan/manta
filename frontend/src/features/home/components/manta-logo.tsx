import mantaMark from "../../../assets/manta-logo.svg";
import mantaWordmark from "../../../assets/manta-word.png";

interface MantaLogoProps {
  /**
   * `auto` follows the app theme (wordmark inverted on dark surfaces);
   * `light` pins the dark wordmark for fixed light backdrops like the auth card.
   */
  tone?: "auto" | "light";
  /** `vertical` stacks the mark above the wordmark (auth card); `horizontal` sits them side by side. */
  layout?: "horizontal" | "vertical";
  /** Pixel height of the lockup. The wordmark PNG is a 2x asset (29px tall), so keep this ≤15 to stay sharp on retina. */
  height?: number;
  /** Pixel height of the mark alone; it's vector, so it can scale past `height` without blurring. */
  markHeight?: number;
  /** Hide the wordmark for tight spots like the workspace header. */
  wordmark?: boolean;
  className?: string;
}

export function MantaLogo({
  tone = "auto",
  layout = "horizontal",
  height = 15,
  markHeight = height,
  wordmark = true,
  className = "",
}: MantaLogoProps) {
  return (
    <span
      role="img"
      aria-label="Manta"
      className={`inline-flex items-center ${layout === "vertical" ? "flex-col gap-3" : "gap-2"} ${className}`}
    >
      <img src={mantaMark} alt="" style={{ height: markHeight }} />
      {wordmark && (
        <img
          src={mantaWordmark}
          alt=""
          style={{ height }}
          className={tone === "auto" ? "manta-wordmark" : undefined}
        />
      )}
    </span>
  );
}
