import type { Metadata } from "next";
import { ApplicationShell } from "@/components/application-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pocket Alpha | Market Intelligence",
  description: "Market intelligence and quantitative research with verifiable evidence.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><ApplicationShell>{children}</ApplicationShell></body></html>;
}
