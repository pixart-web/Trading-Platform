import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pocket Alpha | Mercados",
  description: "Exploração de dados históricos de mercado com qualidade verificável.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="pt-PT"><body>{children}</body></html>;
}
