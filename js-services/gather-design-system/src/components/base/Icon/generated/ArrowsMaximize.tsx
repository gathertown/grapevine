import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgArrowsMaximize = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M13.75 3.75H20.25V10.25M13.75 10.25L19.4766 4.52344M10.25 13.75L4.52344 19.4766M3.75 13.75V20.25H10.25" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgArrowsMaximize);
export default Memo;