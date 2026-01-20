import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgRecordStop = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M18.3639 5.63604C21.8787 9.15076 21.8787 14.8492 18.3639 18.3639C14.8492 21.8787 9.15074 21.8787 5.63604 18.3639C2.12132 14.8492 2.12132 9.15074 5.63604 5.63604C9.15076 2.12132 14.8492 2.12132 18.3639 5.63604Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /><path d="M10 10H14V14H10V10Z" stroke="currentColor" strokeWidth={4} /></svg>;
const Memo = memo(SvgRecordStop);
export default Memo;