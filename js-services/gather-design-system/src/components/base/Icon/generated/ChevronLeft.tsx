import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgChevronLeft = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M15 4L7 12L15 20" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgChevronLeft);
export default Memo;