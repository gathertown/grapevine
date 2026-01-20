import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgArrowLeft = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M5 12H19M5 12L10 7M5 12L10 17" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgArrowLeft);
export default Memo;