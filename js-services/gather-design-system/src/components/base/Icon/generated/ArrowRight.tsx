import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgArrowRight = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M19 12H5M19 12L14 17M19 12L14 7" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgArrowRight);
export default Memo;