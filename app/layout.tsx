import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Variant Viewer",
  description: "Diagnostic variant review and classification",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-6">
          <a href="/" className="text-blue-700 font-semibold text-lg tracking-tight">
            Variant Viewer
          </a>
          <a href="/" className="text-sm text-gray-600 hover:text-gray-900">
            Cases
          </a>
          <a href="/upload" className="text-sm text-gray-600 hover:text-gray-900">
            Upload VCF
          </a>
        </nav>
        <main className="px-6 py-6 max-w-screen-2xl mx-auto">{children}</main>
      </body>
    </html>
  );
}
