import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgChatLines = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M15.5972 14.5694H8.40278M8.40278 10.4583H15.5972M3.93297 16.5181C3.18269 15.182 2.75 13.6424 2.75 12C2.75 6.89092 6.89092 2.75 12 2.75C17.1091 2.75 21.25 6.89092 21.25 12C21.25 17.1091 17.1091 21.25 12 21.25C10.3576 21.25 8.818 20.8173 7.48189 20.067L2.75 21.25L3.93297 16.5181Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgChatLines);
export default Memo;