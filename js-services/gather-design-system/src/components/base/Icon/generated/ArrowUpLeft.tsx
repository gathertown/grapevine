import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgArrowUpLeft = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M5.75 15.25V5.75H15.25M18 18L6.39983 6.39983" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgArrowUpLeft);
export default Memo;