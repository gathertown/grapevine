import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgClose = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M17.6569 6.34314L6.34315 17.6568M17.6569 17.6568L6.34315 6.34314" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgClose);
export default Memo;