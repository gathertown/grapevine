import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgThumbUp = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M13.4537 3.05672L13 3C12.0354 5.30881 10.5941 7.30339 8.89323 9.09755C8.33481 9.68662 8 10.4581 8 11.2698V17.7251C8 18.5028 8.44707 19.2214 9.17776 19.4875C11.6573 20.3904 14.2511 20.5836 16.8732 20.3564C18.4745 20.2176 19.7293 18.981 20.0821 17.413L20.9268 13.6585C21.3488 11.7829 19.9225 9.99996 18 9.99996H15L15.949 6.91581C16.4974 5.13352 15.3041 3.28801 13.4537 3.05672Z" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" /><path d="M3 12C3 10.8954 3.89543 10 5 10C6.65685 10 8 11.3431 8 13V17C8 18.6569 6.65685 20 5 20C3.89543 20 3 19.1046 3 18V12Z" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" /></svg>;
const Memo = memo(SvgThumbUp);
export default Memo;