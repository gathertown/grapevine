import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgZoomIn = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M20 20L16.8033 16.8033M11.5 9.5V13.5M9.5 11.5H13.5M4 11.5C4 15.6421 7.35786 19 11.5 19C15.6421 19 19 15.6421 19 11.5C19 7.35786 15.6421 4 11.5 4C7.35799 4.00031 4.00031 7.35799 4 11.5Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgZoomIn);
export default Memo;