import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgGreenUpwardTrend = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M9.18746 3.9375H12.3958V7.14583M12.096 4.24375L7.99577 8.33811C7.76792 8.56567 7.39878 8.56549 7.17111 8.33782L5.66244 6.82914C5.43463 6.60135 5.06529 6.60135 4.83748 6.82914L1.60413 10.0625" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /><defs><linearGradient id="paint0_linear_165_6873" x1={6.99996} y1={3.9375} x2={6.99996} y2={8} gradientUnits="userSpaceOnUse"><stop stopColor="currentColor" /><stop offset={1} stopColor="currentColor" /></linearGradient></defs></svg>;
const Memo = memo(SvgGreenUpwardTrend);
export default Memo;