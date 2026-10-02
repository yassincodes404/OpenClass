import type { Metadata } from "next";
import "./globals.css";
import { PortalNavigation } from "./components/navigation";
export const metadata: Metadata = {
  title: "OpenClass · Genesis",
  description: "The open-world classification engine.",
};
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <PortalNavigation />
        {children}
      </body>
    </html>
  );
}
