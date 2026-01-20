import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgChevronDown = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M4 8L12 16L20 8" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgChevronDown);
export default Memo;