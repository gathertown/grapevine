import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgEyeClosed = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M9.49599 18.505C10.315 18.822 11.158 19 12 19C15.495 19 18.99 15.967 20.882 12.468C21.039 12.177 21.039 11.824 20.882 11.533C20.384 10.612 19.77 9.73 19.079 8.921M4.99999 19L19 5M9.77299 14.227C8.54299 12.997 8.54299 11.002 9.77299 9.772C11.003 8.542 12.998 8.542 14.228 9.772M17.044 6.956C15.497 5.759 13.748 5 12 5C8.50499 5 5.00999 8.033 3.11799 11.533C2.96099 11.824 2.96099 12.177 3.11799 12.468C4.06399 14.217 5.40999 15.849 6.95599 17.045" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgEyeClosed);
export default Memo;