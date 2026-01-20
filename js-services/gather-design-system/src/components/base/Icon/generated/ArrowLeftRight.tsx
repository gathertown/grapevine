import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgArrowLeftRight = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M5 12L8 9M5 12L8 15M5 12H19M19 12L16 9M19 12L16 15" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgArrowLeftRight);
export default Memo;