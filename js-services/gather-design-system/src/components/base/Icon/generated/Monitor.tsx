import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgMonitor = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M4.98492 21C8.85892 19.667 15.1409 19.667 19.0159 21M19.6319 16.833H4.36792C3.26292 16.833 2.36792 15.938 2.36792 14.833V5.06201C2.36792 3.95701 3.26292 3.06201 4.36792 3.06201H19.6309C20.7359 3.06201 21.6309 3.95701 21.6309 5.06201V14.834C21.6319 15.938 20.7359 16.833 19.6319 16.833Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgMonitor);
export default Memo;