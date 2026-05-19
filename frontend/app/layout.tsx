import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CloudDash Intelligence",
  description: "Multi-agent AI customer support for CloudDash cloud monitoring",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body
        className="h-full overflow-hidden"
        suppressHydrationWarning
        style={{
          background: "var(--bg-root)",
          color: "var(--text-primary)",
          fontFamily: "'Inter', ui-sans-serif, system-ui, sans-serif",
        }}
      >
        {children}
      </body>
    </html>
  );
}
