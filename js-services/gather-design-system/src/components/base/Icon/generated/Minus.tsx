import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgMinus = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M3.75 12H20.25" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" /></svg>;
const Memo = memo(SvgMinus);
export default Memo;