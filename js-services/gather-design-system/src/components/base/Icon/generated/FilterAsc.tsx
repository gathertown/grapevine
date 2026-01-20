import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgFilterAsc = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M3.75 18.25H18.25M3.75 12H11.25M3.75 5.75H9.25M18 13.25V5.25M14.75 8L18 4.75L21.25 8" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgFilterAsc);
export default Memo;