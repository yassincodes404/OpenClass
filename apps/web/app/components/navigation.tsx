"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Workspace" },
  { href: "/projects", label: "Projects" },
] as const;

/** Global portal navigation. Project-specific destinations remain in ProjectShell. */
export function PortalNavigation() {
  const pathname = usePathname();
  return (
    <header className="portal-header">
      <Link href="/" className="brand" aria-label="OpenClass workspace home">
        <span className="mark" aria-hidden="true">
          O<span>↗</span>
        </span>
        OPENCLASS
      </Link>
      <nav className="portal-nav" aria-label="Portal navigation">
        {links.map((link) => {
          const active = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
          return (
            <Link key={link.href} href={link.href} className={active ? "portal-link active" : "portal-link"}>
              {link.label}
            </Link>
          );
        })}
      </nav>
      <span className="badge">GENESIS / 0.0.1</span>
    </header>
  );
}
