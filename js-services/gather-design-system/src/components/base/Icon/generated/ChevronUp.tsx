import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgChevronUp = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M20 16L12 8L4 16" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgChevronUp);
export default Memo;