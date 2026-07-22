import "./globals.css";
import type { Metadata, Viewport } from "next";
import { ThemeProvider } from "@/lib/theme";
import { PRODUCT_NAME, PRODUCT_TAGLINE } from "@/lib/config";

export const metadata: Metadata = {
  title: `${PRODUCT_NAME}`,
  description: PRODUCT_TAGLINE,
  applicationName: PRODUCT_NAME,
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#09090b" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Avoid the dark-mode flash on first paint */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem('atlas.theme')||'system';var d=t==='dark'||(t==='system'&&matchMedia('(prefers-color-scheme:dark)').matches);if(d)document.documentElement.classList.add('dark');}catch(_){}`,
          }}
        />
      </head>
      <body className="h-screen overflow-hidden antialiased">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
