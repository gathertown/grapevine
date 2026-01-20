import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgStrikethrough = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M8 18H14C15.6569 18 17 16.6569 17 15M19 12H5M16 6H11C9.34315 6 8 7.34315 8 9" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgStrikethrough);
export default Memo;