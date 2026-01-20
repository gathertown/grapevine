import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgHashtag = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M8.75 3.75L6.75 20.25M17.25 3.75L15.25 20.25M3.75 7.75H20.25M20.25 16.25H3.75" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgHashtag);
export default Memo;