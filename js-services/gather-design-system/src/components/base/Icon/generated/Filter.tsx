import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgFilter = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M2.75 4.75H21.25M8.75 19.25H15.25M5.75 12H18.25" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" /></svg>;
const Memo = memo(SvgFilter);
export default Memo;