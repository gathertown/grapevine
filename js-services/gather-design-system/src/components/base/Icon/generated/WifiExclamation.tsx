import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgWifiExclamation = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M11.999 19.5C11.861 19.5 11.749 19.612 11.75 19.75C11.75 19.888 11.862 20 12 20C12.138 20 12.25 19.888 12.25 19.75C12.25 19.612 12.138 19.5 11.999 19.5" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /><path d="M1.59399 7.804C7.34099 2.732 16.659 2.732 22.406 7.804M12 16V9.19M19.409 12C18.136 10.832 16.612 10.05 15 9.608M8.99999 9.608C7.38799 10.05 5.86399 10.832 4.59099 12M15 14.777C15.508 15.052 15.99 15.393 16.42 15.821M8.99999 14.777C8.49199 15.052 8.00999 15.393 7.57899 15.821" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgWifiExclamation);
export default Memo;