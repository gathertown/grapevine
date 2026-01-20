import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgBold = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 25 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M7.5 12H13.375C15.0319 12 16.375 10.6569 16.375 9C16.375 7.34315 15.0319 6 13.375 6H7.5V12ZM7.5 12H14.5C16.1569 12 17.5 13.3431 17.5 15C17.5 16.6569 16.1569 18 14.5 18H7.5V12Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgBold);
export default Memo;