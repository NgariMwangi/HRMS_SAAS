import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function icon(...paths: string[]) {
  return function Icon(props: IconProps) {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
        {paths.map((d) => <path key={d} d={d} />)}
      </svg>
    );
  };
}

export const IconHome = icon("M4 11.5 12 4l8 7.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z");
export const IconPeople = icon("M16 19v-1a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v1M12 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6m10 8v-1a3.5 3.5 0 0 0-2.5-3.35M16.5 5.15a3 3 0 0 1 0 5.7");
export const IconBuilding = icon("M4 21V5a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v16M9 21V9m-5 4h5m9-4h3v12h-8");
export const IconCalendar = icon("M7 4v3m10-3v3M5 9h14M6 5h12a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1");
export const IconPay = icon("M4 7h16v10H4zm0 4h16M8 15h2");
export const IconTarget = icon("M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18m0-4a5 5 0 1 0 0-10 5 5 0 0 0 0 10m0-4a1 1 0 1 0 0-2 1 1 0 0 0 0 2");
export const IconBriefcase = icon("M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M4 7h16v12H4z");
export const IconChart = icon("M4 19h16M7 16v-5m5 5V8m5 8v-3");
export const IconPlug = icon("M9 7V3m6 4V3M8 11h8v4a4 4 0 0 1-8 0zm4 8v2");
export const IconSettings = icon("M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9c.3.7.9 1.2 1.6 1.3H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1");
export const IconSearch = icon("m20 20-4.35-4.35M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15");
export const IconBell = icon("M6 8a6 6 0 1 1 12 0c0 7 3 7 3 9H3s3-2 3-9m4 12a2 2 0 0 0 4 0");
export const IconHelp = icon("M12 17h.01M9.1 9a3 3 0 1 1 4.4 2.65c-.7.4-1.5.95-1.5 1.85V14m0 7a9 9 0 1 1 0-18 9 9 0 0 1 0 18");
export const IconPlus = icon("M12 5v14M5 12h14");
export const IconDoc = icon("M7 3h7l5 5v13H7zM14 3v5h5");
export const IconClock = icon("M12 8v5l3 2m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0");
export const IconChevron = icon("m8 10 4 4 4-4");
export const IconCollapse = icon("M15 6 9 12l6 6");
export const IconCheck = icon("m5 12 5 5L20 7");
export const IconLogout = icon("M10 17H5V7h5m4 10 5-5-5-5m5 5H10");
export const IconDownload = icon("M12 3v12m0 0-4-4m4 4 4-4M5 21h14");
export const IconEye = icon("M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z", "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6");
export const IconPencil = icon("M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z");
export const IconTrash = icon("M4 7h16M9 7V5h6v2m-8 0 1 12h8l1-12");
export const IconFilter = icon("M4 5h16l-6 7v6l-4 2v-8z");
export const IconMore = icon("M12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2m0-7a1 1 0 1 0 0-2 1 1 0 0 0 0 2m0 14a1 1 0 1 0 0-2 1 1 0 0 0 0 2");
export const IconMoon = icon("M21 14.5A8.5 8.5 0 1 1 9.5 3 7 7 0 0 0 21 14.5z");
export const IconSun = icon("M12 3v2m0 14v2m9-9h-2M5 12H3m15.36-6.36-1.42 1.42M7.05 16.95l-1.41 1.41m12.72 0-1.41-1.41M7.05 7.05 5.64 5.64M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8z");
