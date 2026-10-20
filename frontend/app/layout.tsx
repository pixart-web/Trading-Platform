import type { Metadata } from "next";
import { ApplicationShell } from "@/components/application-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pocket Alpha | Market Intelligence",
  description: "Inteligência de mercado e investigação quantitativa com evidência verificável.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="pt-PT"><body><ApplicationShell>{children}</ApplicationShell></body></html>;
}
