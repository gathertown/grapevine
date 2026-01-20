// Google Tag Manager dataLayer type declaration
interface DataLayerEvent {
  event: string;
  [key: string]: unknown;
}

declare global {
  interface Window {
    dataLayer: DataLayerEvent[];
  }
}

export {};
