import "./globals.css";

export const metadata = {
  title: "BuildPipeline | Automated SDR",
  description: "AI-assisted outbound pipeline for Lion Elite Clinical and growth-focused businesses."
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
