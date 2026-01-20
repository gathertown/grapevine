import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgRotateAlt = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M13 16H12C7.029 16 3 13.985 3 11.5C3 9.015 7.029 7 12 7C16.971 7 21 9.015 21 11.5C21 13.06 19.411 14.434 17 15.241M13 16L10.5 18.5M13 16L10.5 13.5" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgRotateAlt);
export default Memo;