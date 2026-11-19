import React from "react";

const P = {
  shield: ["M12 3l7 3v5c0 4.5-3 8.2-7 10-4-1.8-7-5.5-7-10V6z"],
  check: ["M5 12.5l4.5 4.5L19 7.5"],
  x: ["M6 6l12 12M18 6L6 18"],
  edit: ["M4 20h4L19 9l-4-4L4 16z", "M13.5 6.5l4 4"],
  sparkle: ["M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z", "M19 16l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"],
  upload: ["M12 16V4", "M7 9l5-5 5 5", "M4 16v4h16v-4"],
  search: ["M11 4a7 7 0 100 14 7 7 0 000-14z", "M20 20l-4-4"],
  alert: ["M12 4l9 16H3z", "M12 10v4", "M12 17.5v.01"],
  file: ["M7 3h7l4 4v14H7z", "M14 3v4h4", "M9.5 12h5M9.5 16h5"],
  image: ["M4 5h16v14H4z", "M4 16l5-5 4 4 3-3 4 4", "M9 9.5v.01"],
  chart: ["M4 20V4", "M4 20h16", "M8 16v-5", "M12 16V8", "M16 16v-8"],
  users: ["M9 11a3.5 3.5 0 100-7 3.5 3.5 0 000 7z", "M2.5 20c.5-3.5 3-5.5 6.5-5.5s6 2 6.5 5.5", "M16 4.5a3.2 3.2 0 010 6", "M18 14.8c2 .6 3.3 2.2 3.5 5.2"],
  link: ["M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1", "M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1"],
  eye: ["M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z", "M12 9.5a2.5 2.5 0 100 5 2.5 2.5 0 000-5z"],
  clock: ["M12 3a9 9 0 100 18 9 9 0 000-18z", "M12 7v5l3 2"],
  arrow: ["M5 12h14", "M13 6l6 6-6 6"],
  plus: ["M12 5v14M5 12h14"],
  trash: ["M4 7h16", "M9 7V4h6v3", "M6 7l1 13h10l1-13"],
  chat: ["M4 5h16v11H9l-5 4z"],
  refresh: ["M20 11a8 8 0 00-14-4L4 9", "M4 4v5h5", "M4 13a8 8 0 0014 4l2-2", "M20 20v-5h-5"],
  lock: ["M6 11h12v9H6z", "M8 11V8a4 4 0 018 0v3"],
  target: ["M12 3a9 9 0 100 18 9 9 0 000-18z", "M12 8a4 4 0 100 8 4 4 0 000-8z"],
  layers: ["M12 3l9 5-9 5-9-5z", "M3 13l9 5 9-5"],
  star: ["M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.5 2.9 1-6.1L3.2 9.5l6.1-.9z"],
  monitor: ["M3 4h18v12H3z", "M8 20h8", "M12 16v4"],
  phone: ["M8 3h8v18H8z", "M11 18h2"],
  book: ["M5 4h12a2 2 0 012 2v14H7a2 2 0 01-2-2z", "M5 18a2 2 0 012-2h12"],
  palette: ["M12 3a9 9 0 100 18c1.2 0 2-.8 2-1.8 0-1.4-1.2-1.5-1.2-2.6 0-.9.8-1.6 1.8-1.6H17a4 4 0 004-4c0-4-4-8-9-8z", "M7.5 11v.01M10 7.5v.01M14.5 7.5v.01"],
  bell: ["M6 9a6 6 0 0112 0c0 6 2 7 2 7H4s2-1 2-7z", "M10 20a2 2 0 004 0"],
};

export default function Icon({ name, size = 18, className = "", style }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {(P[name] || []).map((d, i) => <path key={i} d={d} />)}
    </svg>
  );
}
