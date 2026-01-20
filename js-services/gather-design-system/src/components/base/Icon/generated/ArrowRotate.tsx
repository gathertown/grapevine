import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgArrowRotate = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M19.488 4.63904V8.17504H15.953M19.027 8.175C17.67 5.688 15.032 4 12 4C7.582 4 4 7.582 4 12C4 16.418 7.582 20 12 20C16.418 20 20 16.418 20 12" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgArrowRotate);
export default Memo;