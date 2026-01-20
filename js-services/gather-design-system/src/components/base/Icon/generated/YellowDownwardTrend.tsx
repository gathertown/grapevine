import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgYellowDownwardTrend = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M9.18746 10.0625H12.3958V6.85417M12.096 9.75625L7.99577 5.66189C7.76792 5.43433 7.39878 5.43451 7.17111 5.66218L5.66244 7.17086C5.43463 7.39865 5.06529 7.39865 4.83748 7.17086L1.60413 3.9375" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /><defs><linearGradient id="paint0_linear_165_6900" x1={6.99996} y1={10.0625} x2={6.99988} y2={4.5} gradientUnits="userSpaceOnUse"><stop stopColor="currentColor" /><stop offset={1} stopColor="currentColor" /></linearGradient></defs></svg>;
const Memo = memo(SvgYellowDownwardTrend);
export default Memo;