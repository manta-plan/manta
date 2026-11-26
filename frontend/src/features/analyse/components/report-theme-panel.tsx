import { useRef, useState, type ReactNode } from "react";
import clsx from "clsx";
import { RiResetLeftLine } from "react-icons/ri";
import { LuImage, LuTrash2 } from "react-icons/lu";
import {
  BACKDROP_LABELS,
  CARD_SHADOWS,
  FONT_STACKS,
  LOGO_POSITION_LABELS,
  REPORT_THEME_PRESETS,
  presetTheme,
  type Backdrop,
  type CardShadow,
  type FontKey,
  type HeaderStyle,
  type LogoPosition,
  type ReportDecoration,
  type ReportTheme,
} from "../data/report-themes";
import { prepareReportImage, REPORT_IMAGE_TYPES, ReportImageError } from "../lib/report-image";
import { FormSelect } from "../../../components/form-select";

const BACKDROP_OPTIONS = (Object.keys(BACKDROP_LABELS) as Backdrop[]).map((value) => ({
  value,
  label: BACKDROP_LABELS[value],
}));
const FONT_OPTIONS = (Object.keys(FONT_STACKS) as FontKey[]).map((key) => ({
  value: key,
  label: FONT_STACKS[key].label,
}));

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="text-surface-400 mb-1.5 text-[11px] font-medium">{title}</h3>
      <div className="flex flex-col gap-2">{children}</div>
    </section>
  );
}

function ColorField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="text-surface-200 flex items-center gap-2 text-[12px]">
      <input
        type="color"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-label={label}
        className="border-surface-600 h-6 w-8 shrink-0 cursor-pointer rounded border bg-transparent p-0"
      />
      <span className="min-w-0 flex-1 truncate">{label}</span>
      <span className="text-surface-500 font-mono text-[11px]">{value}</span>
    </label>
  );
}

function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="grid gap-1.5"
      style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={option.value === value}
          onClick={() => onChange(option.value)}
          className={clsx(
            "h-8 rounded border text-[12px] font-medium outline-none",
            option.value === value
              ? "border-accent-500 bg-accent-600/15 text-surface-50"
              : "border-surface-600 bg-surface-900 text-surface-300 hover:border-surface-500 hover:text-surface-100",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function CheckField({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="text-surface-200 flex items-center gap-2 text-[12px]">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="accent-accent-600"
      />
      {label}
    </label>
  );
}

/** A preset as a small swatch strip: page, accent and the first palette colours. */
function PresetSwatch({
  preset,
  isCurrent,
  onPick,
}: {
  preset: ReportTheme;
  isCurrent: boolean;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={isCurrent}
      onClick={onPick}
      className={clsx(
        "flex flex-col gap-1.5 rounded border p-1.5 text-left outline-none",
        isCurrent
          ? "border-accent-500 bg-accent-600/10"
          : "border-surface-600 bg-surface-900 hover:border-surface-500",
      )}
    >
      <span
        className="border-surface-600 flex h-7 overflow-hidden rounded-sm border"
        style={{ background: preset.background }}
      >
        <span className="w-2 shrink-0" style={{ background: preset.accent }} />
        <span className="flex flex-1 items-center gap-0.5 px-1">
          {preset.palette.slice(0, 5).map((color) => (
            <span
              key={color}
              className="h-3.5 flex-1 rounded-[1px]"
              style={{ background: color }}
            />
          ))}
        </span>
      </span>
      <span className="text-surface-100 truncate text-[12px] font-medium">{preset.name}</span>
    </button>
  );
}

/**
 * The report's look: pick a preset, then adjust anything. The theme lives in
 * the report, so edits stay with it; "Reset" goes back to the preset it began as.
 */
export function ReportThemePanel({
  theme,
  onChange,
}: {
  theme: ReportTheme;
  onChange: (theme: ReportTheme) => void;
}) {
  const logoInput = useRef<HTMLInputElement>(null);
  const [logoError, setLogoError] = useState<string | null>(null);
  const decoration = theme.decoration;
  const setDecoration = (changes: Partial<ReportDecoration>) =>
    onChange({ ...theme, decoration: { ...decoration, ...changes } });
  // The logo belongs to the report, not the preset: picking or resetting a preset keeps it.
  const withPreset = (id: string): ReportTheme => {
    const preset = presetTheme(id);
    return { ...preset, decoration: { ...preset.decoration, logo: decoration.logo } };
  };
  const addLogo = async (file: File) => {
    try {
      const { src, name } = await prepareReportImage(file);
      setLogoError(null);
      setDecoration({
        logo: { src, alt: name, position: decoration.logo?.position ?? "header-right" },
      });
    } catch (error) {
      setLogoError(error instanceof ReportImageError ? error.message : "Couldn't use that image.");
    }
  };
  const patch = (changes: Partial<ReportTheme>) => onChange({ ...theme, ...changes });
  const setCard = (changes: Partial<ReportTheme["card"]>) =>
    onChange({ ...theme, card: { ...theme.card, ...changes } });
  const original = REPORT_THEME_PRESETS.find((preset) => preset.id === theme.id);
  const isEdited =
    original !== undefined && JSON.stringify(withPreset(original.id)) !== JSON.stringify(theme);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-3">
      <Section title="Presets">
        <div className="grid grid-cols-2 gap-1.5">
          {REPORT_THEME_PRESETS.map((preset) => (
            <PresetSwatch
              key={preset.id}
              preset={preset}
              isCurrent={preset.id === theme.id}
              onPick={() => onChange(withPreset(preset.id))}
            />
          ))}
        </div>
        {isEdited && (
          <button
            type="button"
            onClick={() => onChange(withPreset(theme.id))}
            className="border-surface-600 text-surface-300 hover:border-surface-500 hover:text-surface-50 flex h-7 items-center justify-center gap-1.5 rounded border text-[12px] outline-none"
          >
            <RiResetLeftLine size={13} />
            Reset to {original.name}
          </button>
        )}
      </Section>

      <Section title="Base">
        <Segmented
          label="Base"
          value={theme.scheme}
          options={[
            { value: "light", label: "Light" },
            { value: "dark", label: "Dark" },
          ]}
          onChange={(scheme) => patch({ scheme })}
        />
      </Section>

      <Section title="Colors">
        <ColorField
          label="Page"
          value={theme.background}
          onChange={(background) => patch({ background })}
        />
        <ColorField label="Text" value={theme.text} onChange={(text) => patch({ text })} />
        <ColorField
          label="Muted text"
          value={theme.mutedText}
          onChange={(mutedText) => patch({ mutedText })}
        />
        <ColorField label="Accent" value={theme.accent} onChange={(accent) => patch({ accent })} />
      </Section>

      <Section title="Chart palette">
        <div className="grid grid-cols-8 gap-1">
          {theme.palette.map((color, index) => (
            <input
              key={index}
              type="color"
              value={color}
              onChange={(event) =>
                patch({
                  palette: theme.palette.map((item, at) =>
                    at === index ? event.target.value : item,
                  ),
                })
              }
              aria-label={`Palette color ${index + 1}`}
              className="border-surface-600 h-6 w-full cursor-pointer rounded border bg-transparent p-0"
            />
          ))}
        </div>
        <p className="text-surface-500 text-[11px] leading-4">
          Used for charts whose series have no color of their own. Colors that carry meaning, like a
          carrier's, stay.
        </p>
      </Section>

      <Section title="Cards">
        <ColorField
          label="Card"
          value={theme.card.background}
          onChange={(background) => setCard({ background })}
        />
        <ColorField
          label="Border"
          value={theme.card.border}
          onChange={(border) => setCard({ border })}
        />
        <label className="text-surface-200 flex items-center gap-2 text-[12px]">
          <span className="w-14 shrink-0">Corners</span>
          <input
            type="range"
            min={0}
            max={16}
            step={1}
            value={theme.card.radius}
            onChange={(event) => setCard({ radius: Number(event.target.value) })}
            aria-label="Card corner radius"
            className="accent-accent-500 min-w-0 flex-1"
          />
          <span className="text-surface-500 w-8 text-right font-mono text-[11px]">
            {theme.card.radius}px
          </span>
        </label>
        <Segmented
          label="Shadow"
          value={theme.card.shadow}
          options={(Object.keys(CARD_SHADOWS) as CardShadow[]).map((value) => ({
            value,
            label: value === "none" ? "None" : value === "soft" ? "Soft" : "Strong",
          }))}
          onChange={(shadow) => setCard({ shadow })}
        />
      </Section>

      <Section title="Fonts">
        <label className="flex flex-col gap-1">
          <span className="text-surface-400 text-[11px]">Headings</span>
          <FormSelect
            value={theme.fonts.heading}
            onValueChange={(heading) =>
              patch({ fonts: { ...theme.fonts, heading: heading as FontKey } })
            }
            options={FONT_OPTIONS}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-surface-400 text-[11px]">Body</span>
          <FormSelect
            value={theme.fonts.body}
            onValueChange={(body) => patch({ fonts: { ...theme.fonts, body: body as FontKey } })}
            options={FONT_OPTIONS}
          />
        </label>
      </Section>

      <Section title="Header">
        <Segmented
          label="Header style"
          value={decoration.header.style}
          options={[
            { value: "none" as HeaderStyle, label: "None" },
            { value: "band" as HeaderStyle, label: "Band" },
            { value: "rule" as HeaderStyle, label: "Rule" },
          ]}
          onChange={(style) => setDecoration({ header: { ...decoration.header, style } })}
        />
        <CheckField
          label="Report name in the header"
          checked={decoration.header.showTitle}
          onChange={(showTitle) => setDecoration({ header: { ...decoration.header, showTitle } })}
        />
      </Section>

      <Section title="Footer">
        <CheckField
          label="Page numbers"
          checked={decoration.footer.pageNumbers}
          onChange={(pageNumbers) =>
            setDecoration({ footer: { ...decoration.footer, pageNumbers } })
          }
        />
        <CheckField
          label="Line above the footer"
          checked={decoration.footer.rule}
          onChange={(rule) => setDecoration({ footer: { ...decoration.footer, rule } })}
        />
        <input
          value={decoration.footer.text}
          onChange={(event) =>
            setDecoration({ footer: { ...decoration.footer, text: event.target.value } })
          }
          placeholder="Footer text, e.g. Confidential"
          aria-label="Footer text"
          className="border-surface-600 bg-surface-900 text-surface-50 placeholder:text-surface-500 focus:border-accent-500 h-8 w-full rounded border px-2 text-[12px] outline-none"
        />
      </Section>

      <Section title="Backdrop">
        <FormSelect
          value={decoration.backdrop}
          onValueChange={(backdrop) => setDecoration({ backdrop: backdrop as Backdrop })}
          options={BACKDROP_OPTIONS}
          ariaLabel="Backdrop"
        />
      </Section>

      <Section title="Logo">
        <input
          ref={logoInput}
          type="file"
          accept={REPORT_IMAGE_TYPES.join(",")}
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void addLogo(file);
          }}
        />
        {decoration.logo ? (
          <>
            <div className="flex items-center gap-2">
              <img
                src={decoration.logo.src}
                alt={decoration.logo.alt}
                className="border-surface-600 h-9 w-20 shrink-0 rounded border bg-white object-contain p-1"
              />
              <button
                type="button"
                onClick={() => logoInput.current?.click()}
                className="border-surface-600 bg-surface-900 text-surface-200 hover:border-surface-500 hover:text-surface-50 flex h-8 flex-1 items-center justify-center gap-1.5 rounded border text-[12px] outline-none"
              >
                <LuImage size={13} />
                Replace
              </button>
              <button
                type="button"
                aria-label="Remove logo"
                title="Remove logo"
                onClick={() => setDecoration({ logo: null })}
                className="border-surface-600 bg-surface-900 text-surface-300 hover:border-surface-500 hover:text-danger-400 flex h-8 w-8 items-center justify-center rounded border outline-none"
              >
                <LuTrash2 size={13} />
              </button>
            </div>
            <FormSelect
              value={decoration.logo.position}
              onValueChange={(position) =>
                decoration.logo &&
                setDecoration({ logo: { ...decoration.logo, position: position as LogoPosition } })
              }
              options={(Object.keys(LOGO_POSITION_LABELS) as LogoPosition[]).map((value) => ({
                value,
                label: LOGO_POSITION_LABELS[value],
              }))}
              ariaLabel="Logo position"
            />
          </>
        ) : (
          <button
            type="button"
            onClick={() => logoInput.current?.click()}
            className="border-surface-500 text-surface-300 hover:border-accent-500 hover:text-surface-50 flex h-8 items-center justify-center gap-1.5 rounded border border-dashed text-[12px] font-medium outline-none"
          >
            <LuImage size={13} />
            Add logo
          </button>
        )}
        {logoError && (
          <p role="alert" className="text-danger-400 text-[11px]">
            {logoError}
          </p>
        )}
      </Section>
    </div>
  );
}
