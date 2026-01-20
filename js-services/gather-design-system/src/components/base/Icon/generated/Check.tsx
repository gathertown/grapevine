import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgCheck = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M20 6.5L9 17.5L4 12.5" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgCheck);
export default Memo;