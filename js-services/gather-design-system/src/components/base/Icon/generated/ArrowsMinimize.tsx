import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgArrowsMinimize = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M13.75 3.75V10.25M13.75 10.25H20.25M13.75 10.25L20.25 3.75M10.25 20.25V13.75M10.25 13.75H3.75M10.25 13.75L3.75 20.25" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgArrowsMinimize);
export default Memo;