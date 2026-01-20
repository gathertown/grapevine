import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgFilterDesc = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M3.75 5.75H18.25M3.75 12H11.25M3.75 18.25H9.25M18 10.75V18.5M14.75 15.75L18 19L21.25 15.75" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgFilterDesc);
export default Memo;