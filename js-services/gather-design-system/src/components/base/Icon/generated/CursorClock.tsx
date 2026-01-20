import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgCursorClock = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M16.667 4.79502V7.33307H18.7738M22.0042 6.99793C22.0042 9.76051 19.7647 12 17.0021 12C14.2395 12 12 9.76051 12 6.99793C12 4.23536 14.2395 1.99585 17.0021 1.99585C19.7647 1.99585 22.0042 4.23536 22.0042 6.99793ZM8.57269 17.9015H12.9984C13.4042 17.9015 13.7698 17.6563 13.9239 17.2809C14.078 16.9055 13.9901 16.4742 13.7013 16.1891L5.69995 8.28956C5.41284 8.0061 4.98356 7.92285 4.6113 8.07843C4.23904 8.23402 3.99667 8.59799 3.99667 9.00146V20.0013C3.99667 20.404 4.2381 20.7675 4.6093 20.9236C4.98051 21.0796 5.40911 20.998 5.69688 20.7163L8.57269 17.9015Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgCursorClock);
export default Memo;