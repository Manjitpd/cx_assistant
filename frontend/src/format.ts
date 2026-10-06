export function formatWhen(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatMoney(cents: number, currency: string): string {
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(cents / 100);
}

export function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean).slice(0, 2);
  const letters = parts.map((part) => part.charAt(0).toUpperCase()).join("");
  return letters || "?";
}

const STATUS_BADGE: Record<string, string> = {
  open: "badge badge-open",
  resolved: "badge badge-resolved",
  pending: "badge badge-pending",
  paid: "badge badge-paid",
  shipped: "badge badge-shipped",
  delivered: "badge badge-delivered",
  cancelled: "badge badge-cancelled",
};

export function statusBadgeClass(status: string): string {
  return STATUS_BADGE[status] ?? "badge";
}
