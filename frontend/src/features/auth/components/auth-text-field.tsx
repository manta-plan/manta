type AuthTextFieldProps = {
  label: string;
  name: string;
  type: "text" | "password";
  placeholder: string;
  autoComplete: string;
};

export function AuthTextField({
  label,
  name,
  type,
  placeholder,
  autoComplete,
}: AuthTextFieldProps) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] font-medium text-slate-500">{label}</span>
      <input
        name={name}
        type={type}
        autoComplete={autoComplete}
        required
        placeholder={placeholder}
        className="focus:border-secondary rounded border border-slate-300 bg-white px-2.5 py-2 text-[13px] text-slate-900 outline-none"
      />
    </label>
  );
}
