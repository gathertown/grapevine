// Type declarations for external modules that don't have TypeScript types

declare module 'get-website-favicon' {
  interface FaviconResult {
    url: string;
    cached?: boolean;
  }
  function getFavicon(_url: string): Promise<FaviconResult | null>;
  export = getFavicon;
}
