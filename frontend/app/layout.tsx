import type { Metadata } from "next";
import { ThemeProvider } from "next-themes";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ToastContainer } from "@/components/notifications/ToastContainer";
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
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange themes={['light', 'dark', 'custom']}>
          <ErrorBoundary>
            {children}
          </ErrorBoundary>
          <ToastContainer />
        </ThemeProvider>
      </body>
    </html>
  );
}
