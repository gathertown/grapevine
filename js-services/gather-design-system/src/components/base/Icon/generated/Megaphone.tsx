import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgMegaphone = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M11.5 13.762L12.194 17.928C12.419 19.281 11.376 20.512 10.005 20.512C8.92 20.512 7.994 19.728 7.816 18.657L7 13.762M13.75 13.76V7.00999M13.75 13.762H5.875C4.011 13.762 2.5 12.251 2.5 10.387C2.5 8.52299 4.011 7.01199 5.875 7.01199H13.75L18.751 3.67799C19.499 3.17999 20.5 3.71599 20.5 4.61499V16.16C20.5 17.059 19.499 17.594 18.751 17.096L13.75 13.762Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgMegaphone);
export default Memo;