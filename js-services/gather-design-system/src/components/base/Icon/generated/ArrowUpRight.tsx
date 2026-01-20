import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgArrowUpRight = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M18.25 15.25V5.75M18.25 5.75H8.75M18.25 5.75L6 18" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgArrowUpRight);
export default Memo;