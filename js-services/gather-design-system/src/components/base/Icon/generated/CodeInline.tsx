import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgCodeInline = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 25 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M14.28 4L10.72 20M18.5 8L22.5 12L18.5 16M6.5 16L2.5 12L6.5 8" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgCodeInline);
export default Memo;