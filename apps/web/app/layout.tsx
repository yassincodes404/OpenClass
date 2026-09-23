import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "OpenClass · Genesis",
  description: "The open-world classification engine.",
};
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
