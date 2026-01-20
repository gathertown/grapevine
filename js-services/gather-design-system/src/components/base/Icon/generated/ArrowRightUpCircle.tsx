import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgArrowRightUpCircle = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M8.75 15.25L14.5694 9.43056M15.25 14.25V8.75H9.75M21.25 12C21.25 6.89137 17.1086 2.75 12 2.75C6.89137 2.75 2.75 6.89137 2.75 12C2.75 17.1086 6.89137 21.25 12 21.25C17.1086 21.25 21.25 17.1086 21.25 12Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgArrowRightUpCircle);
export default Memo;