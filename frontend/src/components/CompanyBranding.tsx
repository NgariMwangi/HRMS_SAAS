import { CSSProperties, useEffect } from "react";

export type Brand = { name?: string; company_name?: string; theme_color?: string; logo_data_url?: string | null };
export function contrast(color: string): string {
  const rgb = [1, 3, 5].map(index => parseInt(color.slice(index, index + 2), 16) / 255)
    .map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
  return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722 < .179 ? "#ffffff" : "#111111";
}

export function brandVariables(color = "#4F46E5"): CSSProperties {
  if (!/^#[0-9a-f]{6}$/i.test(color)) color = "#4F46E5";
  const foreground = contrast(color);
  const dark = "#" + [1, 3, 5].map(index => { const value = parseInt(color.slice(index, index + 2), 16); return Math.round(foreground === "#ffffff" ? value * .85 : value + (255 - value) * .15).toString(16).padStart(2, "0"); }).join("");
  return { "--accent": color, "--accent-dark": dark, "--accent-text": foreground, "--accent-soft": `${color}18`, "--focus": `${color}30` } as CSSProperties;
}

export function CompanyTheme({ company }: { company: Brand | null }) {
  useEffect(() => {
    if (!company) return;
    const root = document.documentElement;
    const values = brandVariables(company.theme_color);
    const old = Object.fromEntries(Object.keys(values).map(key => [key, root.style.getPropertyValue(key)]));
    Object.entries(values).forEach(([key, value]) => root.style.setProperty(key, String(value)));
    const title = document.title;
    document.title = `${company.name ?? company.company_name ?? "Company"} | HRMS`;
    let icon = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    const createdIcon = !icon && Boolean(company.logo_data_url);
    if (createdIcon) { icon = document.createElement("link"); icon.rel = "icon"; document.head.appendChild(icon); }
    const oldIcon = icon?.getAttribute("href");
    const oldType = icon?.type;
    const themeMeta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
    const oldThemeColor = themeMeta?.content;
    if (themeMeta) themeMeta.content = company.theme_color ?? "#4F46E5";
    if (icon && company.logo_data_url) { icon.href = company.logo_data_url; icon.type = company.logo_data_url.split(";")[0].slice(5); }
    return () => {
      Object.entries(old).forEach(([key, value]) => value ? root.style.setProperty(key, value) : root.style.removeProperty(key));
      document.title = title;
      if (createdIcon) icon?.remove();
      else if (icon && oldIcon) { icon.setAttribute("href", oldIcon); icon.type = oldType ?? ""; }
      if (themeMeta && oldThemeColor) themeMeta.content = oldThemeColor;
    };
  }, [company?.theme_color, company?.logo_data_url, company?.name, company?.company_name]);
  return null;
}

export function CompanyLogo({ company }: { company: Brand | null }) {
  return company?.logo_data_url ? <img className="company-logo" src={company.logo_data_url} alt={`${company.name ?? company.company_name ?? "Company"} logo`} /> : <span className="mark">{(company?.name ?? company?.company_name ?? "H").slice(0, 1)}</span>;
}
