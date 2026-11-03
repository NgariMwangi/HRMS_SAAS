import { useState } from "react";

const KEY = "hrms_sidebar_min";

export function useSidebarMin() {
  const [minimized, setMinimized] = useState(() => localStorage.getItem(KEY) === "1");

  function toggle() {
    setMinimized((current) => {
      const next = !current;
      localStorage.setItem(KEY, next ? "1" : "0");
      return next;
    });
  }

  return { minimized, toggle };
}
