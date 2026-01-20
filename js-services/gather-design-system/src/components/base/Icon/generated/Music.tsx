import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgMusic = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M8.49999 17.781V7.96403C8.49999 7.54903 8.75599 7.17703 9.14399 7.03003L17.644 3.79203C18.299 3.54203 19 4.02603 19 4.72603V15.775M18.2678 14.0072C19.2441 14.9835 19.2441 16.5664 18.2678 17.5428C17.2915 18.5191 15.7086 18.5191 14.7323 17.5428C13.756 16.5664 13.756 14.9835 14.7323 14.0072C15.7086 13.0309 17.2915 13.0309 18.2678 14.0072ZM7.76776 16.0072C8.74407 16.9835 8.74407 18.5664 7.76776 19.5428C6.79145 20.5191 5.20854 20.5191 4.23223 19.5428C3.25592 18.5664 3.25592 16.9835 4.23223 16.0072C5.20854 15.0309 6.79145 15.0309 7.76776 16.0072Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgMusic);
export default Memo;