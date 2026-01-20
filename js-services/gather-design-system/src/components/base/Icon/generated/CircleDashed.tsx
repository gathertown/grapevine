import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgCircleDashed = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M21.25 12C21.25 17.1086 17.1086 21.25 12 21.25C6.89137 21.25 2.75 17.1086 2.75 12C2.75 6.89137 6.89137 2.75 12 2.75C17.1086 2.75 21.25 6.89137 21.25 12Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" strokeDasharray="3 4" /></svg>;
const Memo = memo(SvgCircleDashed);
export default Memo;