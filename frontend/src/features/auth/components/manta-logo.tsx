import mantaMark from "../../../assets/manta-logo.svg";
import mantaWordmark from "../../../assets/manta-word.png";

type MantaLogoProps = {
  /** Pixel height of the wordmark. The PNG is a 2x asset (29px tall), so keep this <= 15 to stay sharp. */
  height?: number;
  /** Pixel height of the mark alone; it is vector, so it can scale past `height` without blurring. */
  markHeight?: number;
  className?: string;
};

// Stacks the mark above the wordmark. The wordmark ships dark-on-transparent,
// so it needs a light backdrop.
export function MantaLogo({ height = 15, markHeight = height, className = "" }: MantaLogoProps) {
  return (
    <span
      role="img"
      aria-label="Manta"
      className={`inline-flex flex-col items-center gap-3 ${className}`}
    >
      <img src={mantaMark} alt="" style={{ height: markHeight }} />
      <img src={mantaWordmark} alt="" style={{ height }} />
    </span>
  );
}
