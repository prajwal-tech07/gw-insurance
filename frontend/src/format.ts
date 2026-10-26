const inrFormat = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export const inr = (n: number | null | undefined): string => (n == null ? "-" : `₹${inrFormat.format(Math.round(n))}`);

export const pct = (n: number | null | undefined, digits = 0): string => (n == null ? "-" : `${(n * 100).toFixed(digits)}%`);

export const today = (): string => new Date().toISOString().slice(0, 10);

export const niceDate = (iso: string | null | undefined): string => {
  if (!iso) return "-";
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
};

export const categoryLabel: Record<string, string> = {
  room_rent: "Room rent", icu: "ICU", nursing: "Nursing", professional_fees: "Doctor / surgeon fees",
  ot_charges: "OT / procedure", pharmacy: "Medicines", consumables: "Consumables", implants: "Implants",
  diagnostics: "Tests / imaging", ambulance: "Ambulance", other: "Other",
};

export const num = (v: string): number => {
  const n = Number(v.replace(/,/g, ""));
  return Number.isFinite(n) ? n : 0;
};

export const numOrNull = (v: string): number | null => (v.trim() === "" ? null : num(v));
