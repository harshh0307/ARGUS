import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/providers/theme-provider";
import { Toaster } from "sonner";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Argus - API Breaking-Change Detection",
  description: "Automated, agentic API breaking-change detection and self-healing PR platform",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased dark`}
      suppressHydrationWarning
    >
      <body className="min-h-full flex flex-col bg-[var(--background)] text-[var(--foreground)]">
        <ThemeProvider>
          {children}
          <Toaster
            position="bottom-right"
            theme="dark"
            richColors
            closeButton
            duration={4000}
            toastOptions={{
              className: "text-xs font-medium",
            }}
          />
        </ThemeProvider>
      </body>
    </html>
  );
}
