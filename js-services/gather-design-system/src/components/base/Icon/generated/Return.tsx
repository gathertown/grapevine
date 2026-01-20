import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgReturn = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M20 5V12C20 13.6569 18.6569 15 17 15H5M8 11L4 15L8 19" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgReturn);
export default Memo;