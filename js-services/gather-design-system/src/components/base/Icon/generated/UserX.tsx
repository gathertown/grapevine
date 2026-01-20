import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgUserX = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M4 20C4 17.515 6.015 15.5 8.5 15.5H11.083M15.73 19.77L19.27 16.23M15.73 16.23L19.27 19.77M16.25 8.25C16.25 10.5972 14.3472 12.5 12 12.5C9.65279 12.5 7.75 10.5972 7.75 8.25C7.75 5.90279 9.65279 4 12 4C14.3472 4 16.25 5.90279 16.25 8.25Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgUserX);
export default Memo;