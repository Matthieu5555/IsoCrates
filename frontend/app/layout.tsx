import type { Metadata } from "next";
import { ThemeProvider } from "next-themes";
import "./globals.css";

export const metadata: Metadata = {
  title: "IsoCrates - Technical Documentation",
  description: "AI-powered technical documentation platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem themes={['light', 'dark', 'custom']}>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
