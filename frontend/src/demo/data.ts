/**
 * Placeholder module. Customer HR screens must not import sample staff,
 * payroll, or branches from here — that mixed Nairobi/Kampala/Kigali/Dar
 * into every signed-in workspace.
 *
 * Keep this file empty of records until a real people/payroll API exists.
 */

export function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}
